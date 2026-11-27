"""Read-only stdio MCP adapter for one dashboard job's Git snapshot."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backport_harness.dashboard.codex import MAX_TOOL_CALLS, TOOLS, Snapshot

PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}


def serve_snapshot(snapshot: Snapshot) -> None:
    tools = [
        {
            "name": tool["name"], "description": tool["description"],
            "inputSchema": tool["parameters"], "annotations": {"readOnlyHint": True},
        }
        for tool in TOOLS
    ]
    calls = 0
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue
        method = message.get("method")
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        if method == "initialize":
            version = params.get("protocolVersion")
            if not isinstance(version, str) or version not in PROTOCOL_VERSIONS:
                version = "2025-06-18"
            reply["result"] = {
                "protocolVersion": version,
                "serverInfo": {"name": "backport-snapshot", "version": "1"},
                "capabilities": {"tools": {}},
            }
        elif method == "ping":
            reply["result"] = {}
        elif method == "tools/list":
            reply["result"] = {"tools": tools}
        elif method == "tools/call":
            calls += 1
            if calls <= MAX_TOOL_CALLS:
                result = snapshot.call(params.get("name", ""), json.dumps(params.get("arguments", {})))
            else:
                result = {"error": "The static snapshot read limit has been reached."}
            reply["result"] = {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "isError": "error" in result,
            }
        else:
            reply["error"] = {"code": -32601, "message": "Method not available."}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    serve_snapshot(Snapshot(Path(sys.argv[1]), sys.argv[2]))
