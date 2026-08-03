# FAISS HNSW Benchmark

## Goal

Create a reproducible FAISS `IndexHNSWFlat` benchmark that can serve as an
in-memory ANN baseline for later comparison with Lance.

## Implementation Scope

- Add a standalone FAISS HNSW benchmark CLI that accepts `base.npy` and
  `queries.npy`.
- Add an optional deterministic synthetic dataset mode for smoke tests and
  environments without benchmark data.
- Support L2, cosine similarity via normalized vectors and inner product, and
  raw inner product.
- Build exact FAISS ground truth in batches.
- Build each HNSW index once per dataset, metric, `M`, and `efConstruction`
  combination, save it, and reuse it across `efSearch`, `k`, and thread
  configurations.
- Emit CSV, JSON, and Markdown summary outputs after each completed
  configuration.
- Add automated tests for validation, recall calculation, configuration
  handling, and machine-readable output behavior.

## Expected Behavior

- Invalid arrays fail with clear errors: non-2D arrays, dimension mismatch,
  non-`float32` dtype, non-finite values, or too few base vectors for `k`.
- Warm benchmarks exclude index build, load, and warm-up work from measured ANN
  search latency.
- Cold-load benchmarks measure serialized index loading separately and label the
  first timed query batch as `cold-load`.
- Latency percentiles are calculated from repeated query-batch timings, not from
  one bulk-search duration.
- `efSearch` is applied as at least `k`; the output records both requested and
  effective values.
- Partial results remain on disk if a long run is interrupted.

## Affected Modules or Commands

- `benchmark_faiss_hnsw.py`
- `benchmarks/faiss_hnsw.py`
- `benchmarks/README_FAISS_HNSW.md`
- `benchmarks/faiss_hnsw_quick.yaml`
- `benchmarks/requirements-faiss-hnsw.txt`
- `tests/test_faiss_hnsw_benchmark.py`

## Test Plan

- Run focused tests for the benchmark module.
- Run a small end-to-end synthetic benchmark when FAISS and NumPy are available.
- Confirm CSV and JSON outputs contain the same configurations.
- Confirm Recall@k values are between 0 and 1.
- Confirm saved indexes are loadable and return valid IDs.

## Assumptions and Explicit Non-goals

- This task does not integrate the benchmark into the `backport-harness` CLI.
- This task does not add or benchmark a Lance implementation.
- This task does not attempt to drop operating-system page cache.
- FAISS HNSW is documented as an in-memory baseline; persistent storage,
  versions, deletions, and scalar filtering are Lance-specific costs that should
  not be mixed into pure warm ANN comparisons.
