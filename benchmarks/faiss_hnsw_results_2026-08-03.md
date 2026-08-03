# FAISS HNSW Benchmark Results - 2026-08-03

## Scope

This run uses the FAISS `IndexHNSWFlat` benchmark added in
`benchmark_faiss_hnsw.py`. No `base.npy` or `queries.npy` files were present in
the repository, so the run used deterministic synthetic data.

The results are suitable as a smoke-scale reproducibility check and methodology
validation. They are not a replacement for the intended 1,000,000-vector or
10,000,000-vector production baseline.

## Command

```sh
.venv/bin/python benchmark_faiss_hnsw.py \
  --synthetic \
  --synthetic-base-size 10000 \
  --synthetic-query-size 1000 \
  --dimension 64 \
  --metric cosine \
  --k 10 \
  --m 16 32 \
  --ef-construction 100 \
  --ef-search 16 32 64 128 \
  --threads 1 \
  --query-batch-size 100 \
  --latency-repetitions 3 \
  --warmup-batches 2 \
  --ground-truth-batch-size 100 \
  --mode both \
  --output-dir /tmp/faiss-hnsw-results-2026-08-03
```

## Dataset And Environment

| Field | Value |
| --- | --- |
| Dataset | `synthetic-10000x64` |
| Base vectors | 10,000 |
| Query vectors | 1,000 warm; 100 cold-load first-batch timing |
| Dimension | 64 |
| Metric | cosine, normalized vectors with inner product |
| k | 10 |
| Random seed | 1337 |
| Threads | 1 |
| Query batch size | 100 |
| Latency repetitions | 3 warm; 1 cold-load first batch |
| Warm-up batches | 2 |
| Ground-truth batch size | 100 |
| FAISS version | 1.14.3 |
| Python version | 3.12.3 |
| OS | Linux-6.17.0-23-generic-x86_64-with-glibc2.39 |
| CPU | 12th Gen Intel(R) Core(TM) i7-12700 |
| First result timestamp | 2026-08-03T08:21:56.821575+00:00 |

## Methodology

Ground truth was computed with exact FAISS `IndexFlatIP` in batches after
normalizing base and query vectors for cosine similarity. Each HNSW index was
built once for each `M` value with `efConstruction=100`, serialized to disk, and
then reused for all `efSearch` values.

Warm rows exclude index construction, index loading, and warm-up batches from
timed latency. Cold-load rows measure serialized index loading separately, then
time the first query batch; these rows are labeled `cold-load` and should not be
treated as pure warm ANN latency.

Latency values are per-query milliseconds derived from timed query batches, not
from a single bulk-search duration.

## Results

| Mode | M | efConstruction | efSearch | Recall@10 | QPS | Avg ms | p50 ms | p95 ms | p99 ms | Build s | Index bytes | Load s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| warm | 16 | 100 | 16 | 0.496800 | 97,908.52 | 0.010214 | 0.009254 | 0.015559 | 0.019948 | 0.662494 | 4,000,442 | 0.000000 |
| cold-load | 16 | 100 | 16 | 0.478000 | 108,062.43 | 0.009254 | 0.009254 | 0.009254 | 0.009254 | 0.662494 | 4,000,442 | 0.001617 |
| warm | 16 | 100 | 32 | 0.685000 | 61,913.49 | 0.016152 | 0.016204 | 0.016889 | 0.017225 | 0.662494 | 4,000,442 | 0.000000 |
| cold-load | 16 | 100 | 32 | 0.689000 | 61,080.64 | 0.016372 | 0.016372 | 0.016372 | 0.016372 | 0.662494 | 4,000,442 | 0.000720 |
| warm | 16 | 100 | 64 | 0.856300 | 33,487.27 | 0.029862 | 0.029633 | 0.031232 | 0.031456 | 0.662494 | 4,000,442 | 0.000000 |
| cold-load | 16 | 100 | 64 | 0.857000 | 34,349.03 | 0.029113 | 0.029113 | 0.029113 | 0.029113 | 0.662494 | 4,000,442 | 0.000727 |
| warm | 16 | 100 | 128 | 0.963700 | 15,927.03 | 0.062786 | 0.062906 | 0.064659 | 0.065675 | 0.662494 | 4,000,442 | 0.000000 |
| cold-load | 16 | 100 | 128 | 0.961000 | 16,664.29 | 0.060009 | 0.060009 | 0.060009 | 0.060009 | 0.662494 | 4,000,442 | 0.000793 |
| warm | 32 | 100 | 16 | 0.656900 | 94,722.60 | 0.010557 | 0.010515 | 0.010948 | 0.011182 | 0.684099 | 5,277,858 | 0.000000 |
| cold-load | 32 | 100 | 16 | 0.641000 | 81,235.82 | 0.012310 | 0.012310 | 0.012310 | 0.012310 | 0.684099 | 5,277,858 | 0.001795 |
| warm | 32 | 100 | 32 | 0.830700 | 52,651.86 | 0.018993 | 0.019006 | 0.019371 | 0.019627 | 0.684099 | 5,277,858 | 0.000000 |
| cold-load | 32 | 100 | 32 | 0.826000 | 44,194.24 | 0.022627 | 0.022627 | 0.022627 | 0.022627 | 0.684099 | 5,277,858 | 0.001267 |
| warm | 32 | 100 | 64 | 0.954300 | 26,486.21 | 0.037755 | 0.037787 | 0.040314 | 0.041105 | 0.684099 | 5,277,858 | 0.000000 |
| cold-load | 32 | 100 | 64 | 0.957000 | 24,545.95 | 0.040740 | 0.040740 | 0.040740 | 0.040740 | 0.684099 | 5,277,858 | 0.001979 |
| warm | 32 | 100 | 128 | 0.995600 | 12,598.10 | 0.079377 | 0.079372 | 0.081752 | 0.083850 | 0.684099 | 5,277,858 | 0.000000 |
| cold-load | 32 | 100 | 128 | 0.994000 | 12,146.66 | 0.082327 | 0.082327 | 0.082327 | 0.082327 | 0.684099 | 5,277,858 | 0.001954 |

## Memory And Index Artifacts

| M | efConstruction | RSS before build | Peak RSS during build | RSS after build | Serialized index |
| ---: | ---: | ---: | ---: | ---: | --- |
| 16 | 100 | 58,036,224 bytes | 60,506,112 bytes | 60,633,088 bytes | `synthetic-10000x64_cosine_n10000_d64_M16_efC100_seed1337.faiss` |
| 32 | 100 | 67,153,920 bytes | 69,758,976 bytes | 69,754,880 bytes | `synthetic-10000x64_cosine_n10000_d64_M32_efC100_seed1337.faiss` |

## Validation

- CSV rows: 16.
- JSON rows: 16.
- CSV and JSON contain the same configurations.
- All expected result columns are populated.
- Recall@10 is within `[0, 1]` for every row.
- Warm recall is monotonic for `M=16`: 0.496800, 0.685000,
  0.856300, 0.963700.
- Warm recall is monotonic for `M=32`: 0.656900, 0.830700,
  0.954300, 0.995600.
- Saved FAISS indexes were loaded successfully and each reported
  `ntotal=10000`.

## Observations

- Increasing `efSearch` improves recall and reduces QPS, as expected.
- `M=32` gives higher recall than `M=16` at the same `efSearch`, with a larger
  serialized index.
- On this small synthetic dataset, build times for `M=16` and `M=32` are close:
  0.662494 seconds and 0.684099 seconds.
- Cold-load rows include index load timing and only time the first query batch,
  so their QPS and latency are not directly comparable to warm full-query-set
  rows.

## Limitations

- No production `.npy` dataset was available in the repository.
- The 1,000,000-vector baseline and optional 10,000,000-vector large test were
  not executed.
- The run used a single thread only.
- The run used only `k=10`, cosine similarity, and `efConstruction=100`.
- OS page cache was not dropped and no claim is made that cold-load results
  represent a cold filesystem cache.
- Lance-specific persistent storage, segments, dataset versions, deletions, and
  scalar filtering were not measured here and should remain separate from pure
  warm ANN comparison.
