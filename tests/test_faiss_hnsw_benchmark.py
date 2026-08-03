from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path

import pytest

from benchmarks.faiss_hnsw import (
    BenchmarkError,
    BenchmarkOptions,
    BuildStats,
    ResultWriter,
    build_result_row,
    index_filename,
    parse_args,
    recall_at_k,
    validate_options,
    validate_vectors,
)


np = importlib.import_module("numpy") if importlib.util.find_spec("numpy") else None


def options(**overrides: object) -> BenchmarkOptions:
    values = {
        "base": None,
        "queries": None,
        "synthetic": True,
        "synthetic_base_size": 1000,
        "synthetic_query_size": 100,
        "dimension": 16,
        "dataset_name": None,
        "metric": "cosine",
        "k": (10,),
        "m": (32,),
        "ef_construction": (200,),
        "ef_search": (16, 32),
        "threads": (1,),
        "build_threads": None,
        "output_dir": Path("benchmark-results"),
        "seed": 1337,
        "query_batch_size": 25,
        "latency_repetitions": 2,
        "warmup_batches": 1,
        "ground_truth_batch_size": 25,
        "limit_base_vectors": None,
        "limit_queries": None,
        "mode": "warm",
        "rebuild": False,
    }
    values.update(overrides)
    return BenchmarkOptions(**values)


def test_parse_args_uses_quick_defaults() -> None:
    parsed = parse_args(["--synthetic"])

    assert parsed.metric == "cosine"
    assert parsed.k == (10,)
    assert parsed.m == (32,)
    assert parsed.ef_construction == (200,)
    assert parsed.ef_search == (16, 32, 64, 128, 256)
    assert parsed.synthetic_base_size == 1_000_000
    assert parsed.synthetic_query_size == 10_000


def test_parse_args_loads_yaml_config(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """
synthetic: true
metric: l2
k: [5]
m: [16]
ef_construction: [40]
ef_search: [8]
threads: [2]
output_dir: custom-results
""".lstrip(),
        encoding="utf-8",
    )

    parsed = parse_args(["--config", str(config), "--threads", "1"])

    assert parsed.metric == "l2"
    assert parsed.k == (5,)
    assert parsed.threads == (1,)
    assert parsed.output_dir == Path("custom-results")


def test_validate_options_requires_data_source() -> None:
    with pytest.raises(BenchmarkError, match="provide --base and --queries"):
        validate_options(options(synthetic=False))


def test_validate_vectors_rejects_dimension_mismatch() -> None:
    if np is None:
        pytest.skip("NumPy is required for array validation tests")
    base = np.ones((10, 4), dtype=np.float32)
    queries = np.ones((2, 5), dtype=np.float32)

    with pytest.raises(BenchmarkError, match="does not match"):
        validate_vectors(np, base, queries, 3)


def test_validate_vectors_rejects_non_finite_values() -> None:
    if np is None:
        pytest.skip("NumPy is required for array validation tests")
    base = np.ones((10, 4), dtype=np.float32)
    queries = np.ones((2, 4), dtype=np.float32)
    queries[0, 0] = np.nan

    with pytest.raises(BenchmarkError, match="queries array contains"):
        validate_vectors(np, base, queries, 3)


def test_recall_at_k_averages_intersections() -> None:
    predicted = [[1, 2, 3], [4, 5, 6]]
    truth = [[1, 9, 3], [7, 8, 9]]

    assert recall_at_k(predicted, truth, 3) == pytest.approx(1 / 3)


def test_index_filename_is_portable() -> None:
    name = index_filename("my data/v1", "cosine", 100, 32, 16, 200, 7)

    assert "/" not in name
    assert name.endswith(".faiss")


def test_result_writer_keeps_csv_and_json_configs_in_sync(tmp_path: Path) -> None:
    if np is None:
        pytest.skip("NumPy is required for result-row tests")
    stats = BuildStats(
        total_build_time_seconds=2.0,
        vector_insertion_throughput=50.0,
        serialized_index_size_bytes=1234,
        rss_before_build_bytes=100,
        peak_rss_during_build_bytes=200,
        rss_after_build_bytes=150,
        index_path=str(tmp_path / "index.faiss"),
    )
    row = build_result_row(
        "synthetic",
        np.ones((2, 4), dtype=np.float32),
        np.array([[1, 2], [3, 4]], dtype=np.int64),
        np.array([[1, 9], [3, 4]], dtype=np.int64),
        options(k=(2,)),
        stats,
        {
            "faiss_version": "test",
            "python_version": "3.test",
            "operating_system": "test-os",
            "cpu_model": "test-cpu",
        },
        2,
        16,
        40,
        1,
        2,
        1,
        "warm",
        None,
        [0.001, 0.002],
        0.006,
        100,
    )

    writer = ResultWriter(tmp_path)
    writer.write(row)

    with (tmp_path / "faiss_hnsw_results.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    json_rows = json.loads((tmp_path / "faiss_hnsw_results.json").read_text(encoding="utf-8"))

    assert len(csv_rows) == 1
    assert len(json_rows) == 1
    assert csv_rows[0]["dataset_name"] == json_rows[0]["dataset_name"]
    assert json_rows[0]["recall_at_k"] == pytest.approx(0.75)
