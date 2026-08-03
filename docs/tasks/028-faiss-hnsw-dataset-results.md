# FAISS HNSW Generated Dataset Results

## Goal

Create reproducible local `.npy` benchmark datasets, run the FAISS HNSW
benchmark against those files, and record the benchmark results in a standalone
Markdown report.

## Implementation Scope

- Generate deterministic `base.npy` and `queries.npy` files for the main
  smoke-sized production baseline shape that fits the local environment.
- Run `benchmark_faiss_hnsw.py` using those `.npy` files rather than synthetic
  in-memory mode.
- Record commands, dataset properties, benchmark configuration, environment,
  measured results, validation checks, and limitations in Markdown.
- Keep large generated arrays, serialized FAISS indexes, CSV, and JSON output
  outside the git worktree.

## Expected Behavior

- Generated arrays are two-dimensional `float32` arrays with finite values and
  matching dimensions.
- Benchmark results include recall, QPS, latency percentiles, build time,
  insertion throughput, index size, RSS measurements, warm/cold-load mode, and
  runtime metadata.
- The Markdown report clearly distinguishes generated local datasets from
  externally supplied production datasets.

## Affected Modules or Commands

- `benchmark_faiss_hnsw.py`
- `benchm/faiss_hnsw_generated_dataset_results_2026-08-03.md`

## Test Plan

- Generate deterministic `.npy` datasets.
- Run the benchmark against `base.npy` and `queries.npy`.
- Validate that Recall@k is within `[0, 1]`.
- Validate that warm recall does not decrease across increasing `efSearch` for
  the tested configuration.
- Validate that CSV and JSON output contain the same configurations.
- Validate that the saved FAISS index can be loaded and returns the expected
  vector count.

## Assumptions and Explicit Non-goals

- This task does not modify benchmark implementation code.
- This task does not commit large generated datasets or benchmark artifacts.
- This task does not run the optional 10,000,000-vector large benchmark because
  it is not appropriate for the available memory.
- This task does not add Lance benchmark results.
