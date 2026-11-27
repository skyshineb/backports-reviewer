import threading

import requests

from backport_harness.dashboard.git import resolve_commit
from backport_harness.dashboard.web import DashboardHTTP
from test_dashboard_worker import candidate, service
from test_dashboard_git import repositories


def test_dashboard_routes_and_adaptation_confirmation(service):
    worker, fork, _ = service
    token = "synthetic-dashboard-session-token"
    with DashboardHTTP(0, worker, token) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with requests.Session() as client:
                base = server.origin
                root = client.get(base, timeout=5)
                assert root.ok and "Журнал фиксов" in root.text
                assert "frame-ancestors 'none'" in root.headers["Content-Security-Policy"]
                assert client.get(base + "/assets/drafting.webp", timeout=5).content.startswith(b"RIFF")
                assert client.get(base + "/api/overview", timeout=5).status_code == 401
                client.headers.update({"Authorization": "Bearer " + token, "Origin": base})
                response = client.post(base + "/api/pause", json={"paused": True},
                                       headers={"Origin": "https://example.test"}, timeout=5)
                assert response.status_code == 403
                assert client.get(base + "/api/overview", headers={"Host": "example.test"}, timeout=5).status_code == 403
                overview = client.get(base + "/api/overview?q=conflicting", timeout=5).json()
                assert overview["total"] == 1
                row = overview["commits"][0]
                assert row["applicability"] == "conflict"
                start = resolve_commit(fork, "refs/heads/target")
                url = f"{base}/api/commits/{row['id']}"
                assert client.post(url + "/skip", json={}, timeout=5).ok
                assert client.get(url, timeout=5).json()["commit"]["decision"] == "skipped"
                assert client.post(url + "/unskip", json={}, timeout=5).ok

                response = client.post(url + "/adapt", json={"prompt": "keep private behavior"}, timeout=5)
                assert response.status_code == 202
                job_id = response.json()["job_id"]
                assert worker.run_next("codex")
                job_url = f"{base}/api/jobs/{job_id}"
                job = client.get(job_url, timeout=5).json()
                assert job["status"] == "awaiting_confirmation"
                assert job["prompt"] == "keep private behavior"
                assert "+private behavior with the fix" in job["diff"]
                assert resolve_commit(fork, "refs/heads/target") == start
                assert client.post(job_url + "/confirm", json={"prepared_sha": "wrong"}, timeout=5).status_code == 400
                confirmed = client.post(job_url + "/confirm", json={"prepared_sha": job["prepared_sha"]}, timeout=5)
                assert confirmed.status_code == 202
                assert worker.run_next("git")
                assert client.get(job_url, timeout=5).json()["status"] == "succeeded"
                assert resolve_commit(fork, "refs/heads/target") == job["prepared_sha"]
                assert client.get(base + "/api/queue", timeout=5).json()["total"] >= 5
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_profile_and_controls(service):
    worker, _, settings = service
    with DashboardHTTP(0, worker, "local-api-token") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            headers = {"Authorization": "Bearer local-api-token", "Origin": server.origin}
            base = server.origin + "/api/"

            def post(path, data):
                return requests.post(base + path, headers=headers, json=data, timeout=5)

            config = settings.model_dump(mode="json")
            assert post("profile", config | {"upstream": "https://example.test"}).status_code == 400
            assert post("profile", config | {"interval_minutes": 15}).ok
            assert worker.store.active_profile()["interval_minutes"] == 15
            assert post("pause", {"paused": True}).ok
            assert worker.store.active_profile()["paused"]
            job = post("scans", {"rescan": True}).json()["job_id"]
            assert post(f"jobs/{job}/cancel", {}).ok
            retry = post(f"jobs/{job}/retry", {}).json()["job_id"]
            assert retry != job
            assert worker.run_next("scan")
            assert candidate(worker, "conflict")["decision"] is None
        finally:
            server.shutdown()
            thread.join(timeout=5)
