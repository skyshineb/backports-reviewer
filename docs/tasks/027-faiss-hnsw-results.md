# FAISS HNSW Benchmark Results

## Goal

Run the FAISS HNSW benchmark and create a standalone Markdown report with the
observed results.

## Implementation Scope

- Run the existing `benchmark_faiss_hnsw.py` benchmark.
- Use local `.npy` datasets if available.
- Use deterministic synthetic data if `base.npy` and `queries.npy` are not
  available in the repository.
- Create a Markdown results file that records commands, environment,
  configuration, measured results, validation checks, and limitations.

## Expected Behavior

- The benchmark produces CSV, JSON, Markdown summary, and serialized FAISS index
  outputs.
- The results report clearly identifies whether the run used real `.npy`
  datasets or synthetic vectors.
- The report includes recall, QPS, latency percentiles, build time, index size,
  memory statistics, and validation observations.

## Affected Modules or Commands

- `benchmark_faiss_hnsw.py`
- `benchm/faiss_hnsw_results_2026-08-03.md`

## Test Plan

- Run the benchmark command.
- Validate that Recall@k is within `[0, 1]`.
- Validate that recall does not decrease across increasing `efSearch` for the
  tested configuration beyond minor measurement or tie-related variation.
- Validate that CSV and JSON result files contain the same configurations.
- Validate that the saved FAISS indexes can be loaded.

## Assumptions and Explicit Non-goals

- This task does not change benchmark implementation code.
- This task does not run the full 1M or 10M vector baseline unless the necessary
  datasets and machine resources are available.
- This task does not add Lance benchmark results.
