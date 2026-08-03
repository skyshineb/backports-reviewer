# FAISS HNSW Benchmark

This benchmark measures FAISS `IndexHNSWFlat` as an in-memory ANN baseline for
later Lance comparison. It reports recall, QPS, query latency percentiles,
build time, insertion throughput, serialized index size, process RSS, runtime
metadata, and output files suitable for machine comparison.

Install optional dependencies:

```sh
.venv/bin/python -m pip install -r benchmarks/requirements-faiss-hnsw.txt
```

Smoke test with deterministic synthetic data:

```sh
.venv/bin/python benchmark_faiss_hnsw.py \
  --synthetic \
  --synthetic-base-size 1000 \
  --synthetic-query-size 100 \
  --dimension 32 \
  --metric cosine \
  --k 10 \
  --m 16 \
  --ef-construction 40 \
  --ef-search 16 32 \
  --threads 1 \
  --query-batch-size 25 \
  --latency-repetitions 2 \
  --warmup-batches 1 \
  --ground-truth-batch-size 25 \
  --output-dir benchmark-results-smoke
```

Quick default profile against local `.npy` files:

```sh
.venv/bin/python benchmark_faiss_hnsw.py \
  --base base.npy \
  --queries queries.npy \
  --metric cosine \
  --output-dir benchmark-results
```

Full baseline matrix:

```sh
.venv/bin/python benchmark_faiss_hnsw.py \
  --base base.npy \
  --queries queries.npy \
  --metric cosine \
  --k 10 100 \
  --m 16 32 64 \
  --ef-construction 100 200 400 \
  --ef-search 16 32 64 128 256 \
  --threads 1 8 \
  --query-batch-size 100 \
  --latency-repetitions 5 \
  --warmup-batches 3 \
  --ground-truth-batch-size 100 \
  --output-dir benchmark-results
```

Large runs can use `--limit-base-vectors 10000000` with a dataset containing at
least that many rows. Smaller limits are supported for smoke tests.

Outputs are written incrementally:

- `faiss_hnsw_results.csv`
- `faiss_hnsw_results.json`
- `faiss_hnsw_summary.md`
- serialized indexes under `indexes/`

Cosine mode copies and normalizes vectors before indexing, preserving input
arrays. L2 uses `IndexFlatL2` for exact ground truth. Cosine and inner product
use `IndexFlatIP`. Ground truth is searched in batches to avoid large temporary
distance/id arrays.

Latency is measured with the same configurable query batch size and repetition
count for every configuration. Warm mode performs warm-up batches before timing
and excludes warm-up from reported latency. Cold-load mode loads the serialized
index, records load time separately, and times the first query batch; it should
not be interpreted as pure warm ANN search latency.

FAISS HNSW is primarily an in-memory ANN baseline. Lance comparisons should use
the same dataset, queries, metric, `k`, thread count, query batch size, and
latency method for pure warm ANN comparison. Lance-specific persistent storage,
segments, dataset versions, deletions, and scalar filtering are separate costs
and should be measured separately rather than mixed into this warm FAISS
baseline.
