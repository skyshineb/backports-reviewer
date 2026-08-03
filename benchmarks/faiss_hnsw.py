from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
import threading
import time
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


METRICS = {"l2", "cosine", "inner_product"}
CSV_FIELDS = [
    "dataset_name",
    "base_vectors",
    "query_vectors",
    "dimension",
    "similarity_metric",
    "k",
    "M",
    "efConstruction",
    "requested_efSearch",
    "efSearch",
    "thread_count",
    "random_seed",
    "recall_at_k",
    "qps",
    "avg_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "total_build_time_seconds",
    "vector_insertion_throughput",
    "serialized_index_size_bytes",
    "rss_before_build_bytes",
    "peak_rss_during_build_bytes",
    "rss_after_build_bytes",
    "benchmark_mode",
    "index_load_time_seconds",
    "query_batch_size",
    "latency_repetitions",
    "warmup_batches",
    "ground_truth_batch_size",
    "faiss_version",
    "python_version",
    "operating_system",
    "cpu_model",
    "execution_timestamp",
    "index_path",
]


class BenchmarkError(RuntimeError):
    """Raised for benchmark configuration or data errors."""


@dataclass(frozen=True)
class BenchmarkOptions:
    base: Path | None
    queries: Path | None
    synthetic: bool
    synthetic_base_size: int
    synthetic_query_size: int
    dimension: int
    dataset_name: str | None
    metric: str
    k: tuple[int, ...]
    m: tuple[int, ...]
    ef_construction: tuple[int, ...]
    ef_search: tuple[int, ...]
    threads: tuple[int, ...]
    build_threads: int | None
    output_dir: Path
    seed: int
    query_batch_size: int
    latency_repetitions: int
    warmup_batches: int
    ground_truth_batch_size: int
    limit_base_vectors: int | None
    limit_queries: int | None
    mode: str
    rebuild: bool


@dataclass(frozen=True)
class BuildStats:
    total_build_time_seconds: float
    vector_insertion_throughput: float
    serialized_index_size_bytes: int
    rss_before_build_bytes: int | None
    peak_rss_during_build_bytes: int | None
    rss_after_build_bytes: int | None
    index_path: str


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_args(argv)
        run_benchmark(options)
    except BenchmarkError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


def parse_args(argv: list[str] | None = None) -> BenchmarkOptions:
    parser = argparse.ArgumentParser(description="Benchmark FAISS IndexHNSWFlat.")
    parser.add_argument("--config", type=Path, help="Optional YAML or JSON config file.")
    parser.add_argument("--base", type=Path, help="Path to base.npy.")
    parser.add_argument("--queries", type=Path, help="Path to queries.npy.")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic vectors.")
    parser.add_argument("--synthetic-base-size", type=int)
    parser.add_argument("--synthetic-query-size", type=int)
    parser.add_argument("--dimension", type=int)
    parser.add_argument("--dataset-name")
    parser.add_argument("--metric", choices=sorted(METRICS))
    parser.add_argument("--k", type=int, nargs="+")
    parser.add_argument("--m", type=int, nargs="+")
    parser.add_argument("--ef-construction", type=int, nargs="+")
    parser.add_argument("--ef-search", type=int, nargs="+")
    parser.add_argument("--threads", type=int, nargs="+")
    parser.add_argument("--build-threads", type=int)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--query-batch-size", type=int)
    parser.add_argument("--latency-repetitions", type=int)
    parser.add_argument("--warmup-batches", type=int)
    parser.add_argument("--ground-truth-batch-size", type=int)
    parser.add_argument("--limit-base-vectors", type=int)
    parser.add_argument("--limit-queries", type=int)
    parser.add_argument("--mode", choices=["warm", "cold", "both"])
    parser.add_argument("--rebuild", action="store_true")
    namespace = parser.parse_args(argv)

    config = _load_config(namespace.config) if namespace.config else {}
    values = {
        "base": namespace.base if namespace.base is not None else _optional_path(config.get("base")),
        "queries": namespace.queries if namespace.queries is not None else _optional_path(config.get("queries")),
        "synthetic": namespace.synthetic or bool(config.get("synthetic", False)),
        "synthetic_base_size": _choose(namespace.synthetic_base_size, config, "synthetic_base_size", 1_000_000),
        "synthetic_query_size": _choose(namespace.synthetic_query_size, config, "synthetic_query_size", 10_000),
        "dimension": _choose(namespace.dimension, config, "dimension", 128),
        "dataset_name": _choose(namespace.dataset_name, config, "dataset_name", None),
        "metric": _choose(namespace.metric, config, "metric", "cosine"),
        "k": _tuple(_choose(namespace.k, config, "k", [10])),
        "m": _tuple(_choose(namespace.m, config, "m", [32])),
        "ef_construction": _tuple(_choose(namespace.ef_construction, config, "ef_construction", [200])),
        "ef_search": _tuple(_choose(namespace.ef_search, config, "ef_search", [16, 32, 64, 128, 256])),
        "threads": _tuple(_choose(namespace.threads, config, "threads", [1])),
        "build_threads": _choose(namespace.build_threads, config, "build_threads", None),
        "output_dir": namespace.output_dir or _optional_path(config.get("output_dir")) or Path("benchmark-results"),
        "seed": _choose(namespace.seed, config, "seed", 1337),
        "query_batch_size": _choose(namespace.query_batch_size, config, "query_batch_size", 100),
        "latency_repetitions": _choose(namespace.latency_repetitions, config, "latency_repetitions", 5),
        "warmup_batches": _choose(namespace.warmup_batches, config, "warmup_batches", 3),
        "ground_truth_batch_size": _choose(namespace.ground_truth_batch_size, config, "ground_truth_batch_size", 100),
        "limit_base_vectors": _choose(namespace.limit_base_vectors, config, "limit_base_vectors", None),
        "limit_queries": _choose(namespace.limit_queries, config, "limit_queries", None),
        "mode": _choose(namespace.mode, config, "mode", "warm"),
        "rebuild": namespace.rebuild or bool(config.get("rebuild", False)),
    }
    options = BenchmarkOptions(**values)
    validate_options(options)
    return options


def run_benchmark(options: BenchmarkOptions) -> None:
    np, faiss = _require_runtime_dependencies()
    output_dir = options.output_dir
    index_dir = output_dir / "indexes"
    output_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    base, queries, dataset_name = load_vectors(np, options)
    base, queries = prepare_metric_vectors(np, faiss, base, queries, options.metric)
    validate_vectors(np, base, queries, max(options.k))
    ground_truth = exact_ground_truth(
        faiss,
        base,
        queries,
        options.metric,
        max(options.k),
        options.ground_truth_batch_size,
    )

    env = environment_metadata(faiss)
    writer = ResultWriter(output_dir)
    built: dict[tuple[str, int, int], tuple[Any, BuildStats]] = {}

    try:
        for m_value in options.m:
            for ef_construction in options.ef_construction:
                key = (options.metric, m_value, ef_construction)
                if key not in built:
                    index_path = index_dir / index_filename(
                        dataset_name, options.metric, len(base), base.shape[1], m_value, ef_construction, options.seed
                    )
                    index, stats = build_or_load_index(
                        faiss,
                        base,
                        options.metric,
                        m_value,
                        ef_construction,
                        index_path,
                        options.rebuild,
                        options.build_threads or max(options.threads),
                    )
                    verify_index_ids(faiss, index, queries[: min(len(queries), max(options.k))], max(options.k))
                    built[key] = (index, stats)

                index, stats = built[key]
                for requested_ef_search in options.ef_search:
                    for k_value in options.k:
                        effective_ef_search = max(requested_ef_search, k_value)
                        for thread_count in options.threads:
                            if options.mode in {"warm", "both"}:
                                row = measure_warm(
                                    faiss,
                                    index,
                                    queries,
                                    ground_truth,
                                    dataset_name,
                                    options,
                                    stats,
                                    env,
                                    len(base),
                                    k_value,
                                    m_value,
                                    ef_construction,
                                    requested_ef_search,
                                    effective_ef_search,
                                    thread_count,
                                )
                                writer.write(row)
                            if options.mode in {"cold", "both"}:
                                row = measure_cold(
                                    faiss,
                                    stats.index_path,
                                    queries,
                                    ground_truth,
                                    dataset_name,
                                    options,
                                    stats,
                                    env,
                                    len(base),
                                    k_value,
                                    m_value,
                                    ef_construction,
                                    requested_ef_search,
                                    effective_ef_search,
                                    thread_count,
                                )
                                writer.write(row)
    except KeyboardInterrupt as error:
        raise BenchmarkError(f"interrupted; partial results preserved in {output_dir}") from error


def validate_options(options: BenchmarkOptions) -> None:
    if options.metric not in METRICS:
        raise BenchmarkError(f"unsupported metric {options.metric!r}")
    if options.synthetic:
        if options.base or options.queries:
            raise BenchmarkError("--synthetic cannot be combined with --base or --queries")
    elif not options.base or not options.queries:
        raise BenchmarkError("provide --base and --queries, or use --synthetic")
    for name in ("synthetic_base_size", "synthetic_query_size", "dimension", "query_batch_size", "latency_repetitions", "ground_truth_batch_size"):
        if getattr(options, name) <= 0:
            raise BenchmarkError(f"{name.replace('_', '-')} must be positive")
    for name in ("k", "m", "ef_construction", "ef_search", "threads"):
        values = getattr(options, name)
        if not values or any(value <= 0 for value in values):
            raise BenchmarkError(f"{name.replace('_', '-')} values must be positive")
    if options.limit_base_vectors is not None and options.limit_base_vectors <= 0:
        raise BenchmarkError("--limit-base-vectors must be positive")
    if options.limit_queries is not None and options.limit_queries <= 0:
        raise BenchmarkError("--limit-queries must be positive")
    if options.build_threads is not None and options.build_threads <= 0:
        raise BenchmarkError("--build-threads must be positive")


def load_vectors(np: Any, options: BenchmarkOptions) -> tuple[Any, Any, str]:
    if options.synthetic:
        rng = np.random.default_rng(options.seed)
        base = rng.standard_normal((options.synthetic_base_size, options.dimension), dtype=np.float32)
        queries = rng.standard_normal((options.synthetic_query_size, options.dimension), dtype=np.float32)
        dataset_name = options.dataset_name or f"synthetic-{options.synthetic_base_size}x{options.dimension}"
    else:
        base = np.load(options.base, mmap_mode="r")
        queries = np.load(options.queries, mmap_mode="r")
        dataset_name = options.dataset_name or options.base.stem

    if options.limit_base_vectors is not None:
        base = base[: options.limit_base_vectors]
    if options.limit_queries is not None:
        queries = queries[: options.limit_queries]
    return base, queries, dataset_name


def validate_vectors(np: Any, base: Any, queries: Any, max_k: int) -> None:
    if base.ndim != 2:
        raise BenchmarkError(f"base array must be two-dimensional, got shape {base.shape}")
    if queries.ndim != 2:
        raise BenchmarkError(f"queries array must be two-dimensional, got shape {queries.shape}")
    if base.shape[1] != queries.shape[1]:
        raise BenchmarkError(f"base dimension {base.shape[1]} does not match query dimension {queries.shape[1]}")
    if base.dtype != np.float32:
        raise BenchmarkError(f"base array must have dtype float32, got {base.dtype}")
    if queries.dtype != np.float32:
        raise BenchmarkError(f"queries array must have dtype float32, got {queries.dtype}")
    if len(base) < max_k:
        raise BenchmarkError(f"base vectors ({len(base)}) must be at least requested k ({max_k})")
    if not np.isfinite(base).all():
        raise BenchmarkError("base array contains NaN or infinite values")
    if not np.isfinite(queries).all():
        raise BenchmarkError("queries array contains NaN or infinite values")


def prepare_metric_vectors(np: Any, faiss: Any, base: Any, queries: Any, metric: str) -> tuple[Any, Any]:
    base = np.asarray(base, dtype=np.float32)
    queries = np.asarray(queries, dtype=np.float32)
    if metric != "cosine":
        return base.copy(), queries.copy()
    base_copy = base.copy()
    query_copy = queries.copy()
    faiss.normalize_L2(base_copy)
    faiss.normalize_L2(query_copy)
    return base_copy, query_copy


def exact_ground_truth(
    faiss: Any,
    base: Any,
    queries: Any,
    metric: str,
    max_k: int,
    batch_size: int,
) -> Any:
    index = faiss.IndexFlatL2(base.shape[1]) if metric == "l2" else faiss.IndexFlatIP(base.shape[1])
    index.add(base)
    batches = []
    for start in range(0, len(queries), batch_size):
        _, ids = index.search(queries[start : start + batch_size], max_k)
        _ensure_valid_ids(ids)
        batches.append(ids)
    np = _numpy()
    return np.vstack(batches)


def build_or_load_index(
    faiss: Any,
    base: Any,
    metric: str,
    m_value: int,
    ef_construction: int,
    index_path: Path,
    rebuild: bool,
    build_threads: int,
) -> tuple[Any, BuildStats]:
    meta_path = index_path.with_suffix(index_path.suffix + ".json")
    if index_path.exists() and meta_path.exists() and not rebuild:
        index = faiss.read_index(str(index_path))
        return index, BuildStats(**json.loads(meta_path.read_text(encoding="utf-8")))

    faiss.omp_set_num_threads(build_threads)
    metric_type = faiss.METRIC_L2 if metric == "l2" else faiss.METRIC_INNER_PRODUCT
    rss_before = current_rss_bytes()
    sampler = RssSampler()
    sampler.start()
    started = time.perf_counter()
    index = faiss.IndexHNSWFlat(base.shape[1], m_value, metric_type)
    index.hnsw.efConstruction = ef_construction
    index.add(base)
    total = time.perf_counter() - started
    sampler.stop()
    rss_after = current_rss_bytes()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    stats = BuildStats(
        total_build_time_seconds=total,
        vector_insertion_throughput=len(base) / total if total > 0 else 0.0,
        serialized_index_size_bytes=index_path.stat().st_size,
        rss_before_build_bytes=rss_before,
        peak_rss_during_build_bytes=sampler.peak_rss_bytes,
        rss_after_build_bytes=rss_after,
        index_path=str(index_path),
    )
    meta_path.write_text(json.dumps(_dataclass_dict(stats), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index, stats


def measure_warm(
    faiss: Any,
    index: Any,
    queries: Any,
    ground_truth: Any,
    dataset_name: str,
    options: BenchmarkOptions,
    stats: BuildStats,
    env: dict[str, Any],
    base_vectors: int,
    k_value: int,
    m_value: int,
    ef_construction: int,
    requested_ef_search: int,
    effective_ef_search: int,
    thread_count: int,
) -> dict[str, Any]:
    faiss.omp_set_num_threads(thread_count)
    index.hnsw.efSearch = effective_ef_search
    for batch in _query_batches(queries, options.query_batch_size, options.warmup_batches):
        index.search(batch, k_value)
    predictions, latencies, total_search_seconds = _timed_search(
        index, queries, k_value, options.query_batch_size, options.latency_repetitions
    )
    _ensure_valid_ids(predictions)
    return build_result_row(
        dataset_name,
        queries,
        ground_truth,
        predictions,
        options,
        stats,
        env,
        k_value,
        m_value,
        ef_construction,
        requested_ef_search,
        effective_ef_search,
        thread_count,
        "warm",
        0.0,
        latencies,
        total_search_seconds,
        base_vectors,
    )


def measure_cold(
    faiss: Any,
    index_path: str,
    queries: Any,
    ground_truth: Any,
    dataset_name: str,
    options: BenchmarkOptions,
    stats: BuildStats,
    env: dict[str, Any],
    base_vectors: int,
    k_value: int,
    m_value: int,
    ef_construction: int,
    requested_ef_search: int,
    effective_ef_search: int,
    thread_count: int,
) -> dict[str, Any]:
    faiss.omp_set_num_threads(thread_count)
    started = time.perf_counter()
    index = faiss.read_index(index_path)
    load_time = time.perf_counter() - started
    index.hnsw.efSearch = effective_ef_search
    first_batch = queries[: options.query_batch_size]
    started = time.perf_counter()
    _, predictions = index.search(first_batch, k_value)
    elapsed = time.perf_counter() - started
    _ensure_valid_ids(predictions)
    return build_result_row(
        dataset_name,
        first_batch,
        ground_truth[: len(first_batch)],
        predictions,
        options,
        stats,
        env,
        k_value,
        m_value,
        ef_construction,
        requested_ef_search,
        effective_ef_search,
        thread_count,
        "cold-load",
        load_time,
        [elapsed / len(first_batch)],
        elapsed,
        base_vectors,
    )


def build_result_row(
    dataset_name: str,
    measured_queries: Any,
    ground_truth: Any,
    predictions: Any,
    options: BenchmarkOptions,
    stats: BuildStats,
    env: dict[str, Any],
    k_value: int,
    m_value: int,
    ef_construction: int,
    requested_ef_search: int,
    effective_ef_search: int,
    thread_count: int,
    mode: str,
    load_time: float | None,
    per_query_latencies: list[float],
    total_search_seconds: float,
    base_vectors: int,
) -> dict[str, Any]:
    np = _numpy()
    lat = np.asarray(per_query_latencies, dtype=np.float64) * 1000.0
    total_queries = len(measured_queries) * (options.latency_repetitions if mode == "warm" else 1)
    return {
        "dataset_name": dataset_name,
        "base_vectors": int(base_vectors),
        "query_vectors": int(len(measured_queries)),
        "dimension": int(measured_queries.shape[1]),
        "similarity_metric": options.metric,
        "k": k_value,
        "M": m_value,
        "efConstruction": ef_construction,
        "requested_efSearch": requested_ef_search,
        "efSearch": effective_ef_search,
        "thread_count": thread_count,
        "random_seed": options.seed,
        "recall_at_k": recall_at_k(predictions[:, :k_value], ground_truth[:, :k_value], k_value),
        "qps": total_queries / total_search_seconds if total_search_seconds > 0 else 0.0,
        "avg_latency_ms": float(np.mean(lat)),
        "p50_latency_ms": float(np.percentile(lat, 50)),
        "p95_latency_ms": float(np.percentile(lat, 95)),
        "p99_latency_ms": float(np.percentile(lat, 99)),
        "total_build_time_seconds": stats.total_build_time_seconds,
        "vector_insertion_throughput": stats.vector_insertion_throughput,
        "serialized_index_size_bytes": stats.serialized_index_size_bytes,
        "rss_before_build_bytes": stats.rss_before_build_bytes,
        "peak_rss_during_build_bytes": stats.peak_rss_during_build_bytes,
        "rss_after_build_bytes": stats.rss_after_build_bytes,
        "benchmark_mode": mode,
        "index_load_time_seconds": load_time,
        "query_batch_size": options.query_batch_size,
        "latency_repetitions": options.latency_repetitions if mode == "warm" else 1,
        "warmup_batches": options.warmup_batches if mode == "warm" else 0,
        "ground_truth_batch_size": options.ground_truth_batch_size,
        "faiss_version": env["faiss_version"],
        "python_version": env["python_version"],
        "operating_system": env["operating_system"],
        "cpu_model": env["cpu_model"],
        "execution_timestamp": datetime.now(timezone.utc).isoformat(),
        "index_path": stats.index_path,
    }


def recall_at_k(predicted_ids: Any, ground_truth_ids: Any, k_value: int) -> float:
    if len(predicted_ids) == 0:
        return 0.0
    total = 0.0
    for predicted, truth in zip(predicted_ids, ground_truth_ids, strict=True):
        total += len(set(map(int, predicted[:k_value])).intersection(map(int, truth[:k_value]))) / k_value
    return total / len(predicted_ids)


class ResultWriter:
    def __init__(self, output_dir: Path) -> None:
        self.csv_path = output_dir / "faiss_hnsw_results.csv"
        self.json_path = output_dir / "faiss_hnsw_results.json"
        self.summary_path = output_dir / "faiss_hnsw_summary.md"
        self.rows: list[dict[str, Any]] = []
        if self.json_path.exists():
            self.rows = json.loads(self.json_path.read_text(encoding="utf-8"))

    def write(self, row: dict[str, Any]) -> None:
        write_header = not self.csv_path.exists()
        with self.csv_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})
            handle.flush()
            os.fsync(handle.fileno())
        self.rows.append(row)
        tmp = self.json_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.json_path)
        self._write_summary()

    def _write_summary(self) -> None:
        lines = [
            "# FAISS HNSW Benchmark Summary",
            "",
            f"Generated rows: {len(self.rows)}",
            "",
            "| dataset | metric | mode | k | M | efConstruction | efSearch | threads | recall | qps | avg ms |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in self.rows:
            lines.append(
                "| {dataset_name} | {similarity_metric} | {benchmark_mode} | {k} | {M} | "
                "{efConstruction} | {efSearch} | {thread_count} | {recall_at_k:.6f} | "
                "{qps:.3f} | {avg_latency_ms:.3f} |".format(**row)
            )
        self.summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RssSampler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.peak_rss_bytes = current_rss_bytes()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            rss = current_rss_bytes()
            if rss is not None:
                self.peak_rss_bytes = max(self.peak_rss_bytes or 0, rss)
            time.sleep(0.05)


def current_rss_bytes() -> int | None:
    try:
        import psutil  # type: ignore

        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


def environment_metadata(faiss: Any) -> dict[str, str]:
    return {
        "faiss_version": getattr(faiss, "__version__", "unknown"),
        "python_version": platform.python_version(),
        "operating_system": platform.platform(),
        "cpu_model": cpu_model(),
    }


def cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def verify_index_ids(faiss: Any, index: Any, queries: Any, k_value: int) -> None:
    _, ids = index.search(queries, k_value)
    _ensure_valid_ids(ids)


def _timed_search(index: Any, queries: Any, k_value: int, batch_size: int, repetitions: int) -> tuple[Any, list[float], float]:
    predictions = None
    latencies = []
    total_search_seconds = 0.0
    np = _numpy()
    for repetition in range(repetitions):
        batch_predictions = []
        for batch in _query_batches(queries, batch_size):
            started = time.perf_counter()
            _, ids = index.search(batch, k_value)
            elapsed = time.perf_counter() - started
            total_search_seconds += elapsed
            latencies.append(elapsed / len(batch))
            batch_predictions.append(ids)
        if repetition == 0:
            predictions = np.vstack(batch_predictions)
    return predictions, latencies, total_search_seconds


def _query_batches(queries: Any, batch_size: int, limit: int | None = None) -> Iterable[Any]:
    yielded = 0
    for start in range(0, len(queries), batch_size):
        if limit is not None and yielded >= limit:
            return
        yielded += 1
        yield queries[start : start + batch_size]


def _ensure_valid_ids(ids: Any) -> None:
    if (ids < 0).any():
        raise BenchmarkError("FAISS returned invalid result IDs")


def index_filename(dataset: str, metric: str, base_count: int, dimension: int, m_value: int, ef_construction: int, seed: int) -> str:
    safe_dataset = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in dataset)
    return f"{safe_dataset}_{metric}_n{base_count}_d{dimension}_M{m_value}_efC{ef_construction}_seed{seed}.faiss"


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BenchmarkError(f"config file does not exist: {path}")
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(raw)
    try:
        import yaml
    except ImportError as error:
        raise BenchmarkError("YAML config requires pyyaml; use JSON or install pyyaml") from error
    payload = yaml.safe_load(raw) or {}
    if not isinstance(payload, dict):
        raise BenchmarkError("config file must contain a mapping")
    return payload


def _require_runtime_dependencies() -> tuple[Any, Any]:
    try:
        import numpy as np  # type: ignore
    except ImportError as error:
        raise BenchmarkError("missing dependency: install numpy or benchmarks/requirements-faiss-hnsw.txt") from error
    try:
        import faiss  # type: ignore
    except ImportError as error:
        raise BenchmarkError("missing dependency: install faiss-cpu or benchmarks/requirements-faiss-hnsw.txt") from error
    return np, faiss


def _numpy() -> Any:
    import numpy as np  # type: ignore

    return np


def _choose(value: Any, config: dict[str, Any], key: str, default: Any) -> Any:
    return value if value is not None else config.get(key, default)


def _tuple(value: Any) -> tuple[int, ...]:
    if isinstance(value, int):
        return (value,)
    return tuple(int(item) for item in value)


def _optional_path(value: Any) -> Path | None:
    return Path(value) if value else None


def _dataclass_dict(value: Any) -> dict[str, Any]:
    return {field.name: getattr(value, field.name) for field in fields(value)}


__all__ = [
    "BenchmarkError",
    "BenchmarkOptions",
    "ResultWriter",
    "build_result_row",
    "index_filename",
    "main",
    "parse_args",
    "recall_at_k",
    "validate_options",
    "validate_vectors",
]
