# FAISS HNSW Generated Dataset Benchmark Results - 2026-08-03

## Scope

This report records a FAISS `IndexHNSWFlat` benchmark run against generated
local `.npy` files. The datasets were created first as `base.npy` and
`queries.npy`, then passed to `benchmark_faiss_hnsw.py` through `--base` and
`--queries`.

This is the main 1,000,000-vector quick baseline profile. The optional
10,000,000-vector large profile was not run because the local machine has
15 GiB RAM and the larger run would be likely to exceed practical memory or time
limits.

## Dataset Generation

Generated files:

- `/tmp/faiss-hnsw-datasets-2026-08-03/base.npy`
- `/tmp/faiss-hnsw-datasets-2026-08-03/queries.npy`
- `/tmp/faiss-hnsw-datasets-2026-08-03/metadata.json`

Generation command:

```sh
.venv/bin/python -c "from pathlib import Path; import json, numpy as np; out=Path('/tmp/faiss-hnsw-datasets-2026-08-03'); out.mkdir(parents=True, exist_ok=True); seed=1337; dim=128; nbase=1000000; nqueries=10000; chunk=100000; rng=np.random.default_rng(seed); base=np.lib.format.open_memmap(out/'base.npy', mode='w+', dtype=np.float32, shape=(nbase, dim)); written=0
while written < nbase:
    end=min(written+chunk, nbase); base[written:end]=rng.standard_normal((end-written, dim), dtype=np.float32); written=end
base.flush(); queries=np.lib.format.open_memmap(out/'queries.npy', mode='w+', dtype=np.float32, shape=(nqueries, dim)); queries[:]=rng.standard_normal((nqueries, dim), dtype=np.float32); queries.flush(); meta={'seed':seed,'base_vectors':nbase,'query_vectors':nqueries,'dimension':dim,'dtype':'float32','base_path':str(out/'base.npy'),'queries_path':str(out/'queries.npy')}; (out/'metadata.json').write_text(json.dumps(meta, indent=2, sort_keys=True)+'\n', encoding='utf-8'); print(json.dumps(meta, sort_keys=True))"
```

Dataset validation:

| Field | Value |
| --- | --- |
| Base shape | `(1000000, 128)` |
| Query shape | `(10000, 128)` |
| Base dtype | `float32` |
| Query dtype | `float32` |
| Base finite values | true |
| Query finite values | true |
| Base file size | 512,000,128 bytes |
| Query file size | 5,120,128 bytes |
| Random seed | 1337 |

## Benchmark Command

```sh
.venv/bin/python benchmark_faiss_hnsw.py \
  --base /tmp/faiss-hnsw-datasets-2026-08-03/base.npy \
  --queries /tmp/faiss-hnsw-datasets-2026-08-03/queries.npy \
  --dataset-name generated-1m-128d-seed1337 \
  --metric cosine \
  --k 10 \
  --m 32 \
  --ef-construction 200 \
  --ef-search 16 32 64 128 256 \
  --threads 1 \
  --query-batch-size 100 \
  --latency-repetitions 3 \
  --warmup-batches 2 \
  --ground-truth-batch-size 100 \
  --mode both \
  --output-dir /tmp/faiss-hnsw-generated-results-2026-08-03
```

## Environment

| Field | Value |
| --- | --- |
| Dataset name | `generated-1m-128d-seed1337` |
| Base vectors | 1,000,000 |
| Query vectors | 10,000 warm; 100 cold-load first-batch timing |
| Dimension | 128 |
| Metric | cosine, normalized vectors with inner product |
| k | 10 |
| M | 32 |
| efConstruction | 200 |
| Threads | 1 |
| Query batch size | 100 |
| Latency repetitions | 3 warm; 1 cold-load first batch |
| Warm-up batches | 2 |
| Ground-truth batch size | 100 |
| FAISS version | 1.14.3 |
| Python version | 3.12.3 |
| OS | Linux-6.17.0-23-generic-x86_64-with-glibc2.39 |
| CPU | 12th Gen Intel(R) Core(TM) i7-12700 |
| First result timestamp | 2026-08-03T08:59:51.775703+00:00 |

## Methodology

The benchmark loaded `base.npy` and `queries.npy`, validated shape, dtype,
dimension compatibility, finite values, and `k <= base_vectors`, then copied and
normalized vectors for cosine similarity.

Ground truth was computed with exact FAISS `IndexFlatIP` in batches of 100
queries. The HNSW index was built once with `M=32` and `efConstruction=200`,
serialized to disk, and reused for every `efSearch` value.

Warm rows exclude index construction, index loading, and warm-up batches from
search latency. Cold-load rows measure serialized index loading separately and
time only the first query batch; they are labeled `cold-load` and should not be
treated as pure warm ANN latency.

Latency percentiles are per-query milliseconds from timed query batches, not a
single bulk-search duration.

## Results

| Mode | efSearch | Recall@10 | QPS | Avg ms | p50 ms | p95 ms | p99 ms | Build s | Insert vectors/s | Index bytes | Load s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| warm | 16 | 0.042350 | 6,341.54 | 0.157690 | 0.157343 | 0.168563 | 0.174279 | 1,436.697432 | 696.04 | 784,129,506 | 0.000000 |
| cold-load | 16 | 0.049000 | 5,958.45 | 0.167829 | 0.167829 | 0.167829 | 0.167829 | 1,436.697432 | 696.04 | 784,129,506 | 0.308859 |
| warm | 32 | 0.076680 | 3,423.01 | 0.292140 | 0.289951 | 0.307292 | 0.314334 | 1,436.697432 | 696.04 | 784,129,506 | 0.000000 |
| cold-load | 32 | 0.082000 | 3,356.69 | 0.297912 | 0.297912 | 0.297912 | 0.297912 | 1,436.697432 | 696.04 | 784,129,506 | 0.306985 |
| warm | 64 | 0.136420 | 1,851.56 | 0.540084 | 0.537824 | 0.559627 | 0.568961 | 1,436.697432 | 696.04 | 784,129,506 | 0.000000 |
| cold-load | 64 | 0.128000 | 1,841.87 | 0.542927 | 0.542927 | 0.542927 | 0.542927 | 1,436.697432 | 696.04 | 784,129,506 | 0.305683 |
| warm | 128 | 0.235020 | 984.01 | 1.016245 | 1.014302 | 1.041248 | 1.061074 | 1,436.697432 | 696.04 | 784,129,506 | 0.000000 |
| cold-load | 128 | 0.220000 | 996.76 | 1.003255 | 1.003255 | 1.003255 | 1.003255 | 1,436.697432 | 696.04 | 784,129,506 | 0.304203 |
| warm | 256 | 0.383290 | 522.85 | 1.912609 | 1.912628 | 1.930418 | 1.945305 | 1,436.697432 | 696.04 | 784,129,506 | 0.000000 |
| cold-load | 256 | 0.375000 | 525.24 | 1.903889 | 1.903889 | 1.903889 | 1.903889 | 1,436.697432 | 696.04 | 784,129,506 | 0.303779 |

## Memory And Index Artifact

| Field | Value |
| --- | --- |
| RSS before build | 564,596,736 bytes |
| Peak RSS during build | 1,357,627,392 bytes |
| RSS after build | 1,357,754,368 bytes |
| Serialized index path | `/tmp/faiss-hnsw-generated-results-2026-08-03/indexes/generated-1m-128d-seed1337_cosine_n1000000_d128_M32_efC200_seed1337.faiss` |
| Serialized index size | 784,129,506 bytes |
| Loaded index `ntotal` | 1,000,000 |

## Validation

- CSV rows: 10.
- JSON rows: 10.
- CSV and JSON contain the same configurations.
- All expected result columns are populated.
- Recall@10 is within `[0, 1]` for every row.
- Warm recall is monotonic across increasing `efSearch`: 0.042350,
  0.076680, 0.136420, 0.235020, 0.383290.
- The saved FAISS index loaded successfully and reported `ntotal=1000000`.

## Observations

- Increasing `efSearch` improved warm Recall@10 and reduced QPS, as expected.
- Recall remains low at this setting on random 128-dimensional Gaussian vectors:
  `M=32`, `efConstruction=200`, and `efSearch=256` reached Recall@10 of
  0.383290.
- Build time was 1,436.697432 seconds, with insertion throughput of roughly
  696 vectors per second.
- The serialized HNSW index is about 748 MiB for 1,000,000 vectors at
  `dimension=128`, `M=32`.
- Cold-load rows include index load time and only measure the first query batch,
  so they should be interpreted separately from warm full-query-set rows.

## Limitations

- The generated dataset is deterministic and file-backed, but it is not a real
  production embedding dataset.
- Only the quick profile was run: cosine, `k=10`, `M=32`,
  `efConstruction=200`, `efSearch=16..256`, and one thread.
- The optional 10,000,000-vector benchmark was not run due local memory and time
  constraints.
- OS page cache was not dropped; no claim is made that cold-load results reflect
  a cold filesystem cache.
- Lance-specific persistent storage, segments, dataset versions, deletions, and
  scalar filtering were not measured and should remain separate from pure warm
  ANN comparison.
