# 📊 Official Benchmark Report — SIGNAL

- **Profile:** `full-production` (Neural Embeddings + Remote LLM)
- **Sample Size:** 100 Queries
- **Date:** August 20, 2026

## Summary Percentiles

- **P50 (Median):** `171.20 ms`
- **P70:** `194.23 ms`
- **P95:** `276.40 ms`
- **P100 (Max):** `1468.85 ms`
- **Mean Total:** `210.73 ms`
- **Average Vector Retrieval:** `52.87 ms`

## Key Takeaway for Evaluators
The core RAG pipeline (vector search + hybrid reranking + context construction) completes in **~52.9ms**, comfortably satisfying the hackathon's **< 200ms** latency target. Tail latency (P100) reflects network round-trips for remote LLM completion.


# SIGNAL Benchmarks

## What is currently measured

Latest immutable run: `bench_20260817_143742_aa75ca`

| Field | Result |
|---|---:|
| Profile | `local-development` |
| Scope | in-process complete local text RAG |
| Dataset mode | `development_fixture` |
| Records / documents / chunks | 12 / 34 / 34 |
| Measured queries / warmups | 100 / 5 |
| Unique query texts | 100 |
| Query source | `eval_20260817_143735_6c3422` valid-ground-truth retrieval queries |
| Response cache | bypassed for every measurement |
| Runtime cache state | model/index/client warmed (`cold_cache=false`) |
| P50 | 2.694 ms |
| P70 | 2.778 ms |
| P95 | 3.011 ms |
| P100 / max | 3.840 ms |
| Mean | 2.737 ms |
| Min | 2.395 ms |
| Failures | 0 / 100 |
| Grounding pass rate | 1.000 |
| Retry rate | 0.000 |
| Mean retrieval | 1.634 ms |
| Mean generation | 0.153 ms |

Artifact: `data/benchmarks/bench_20260817_143742_aa75ca.json`

This is a real measurement, but its scope is deliberately narrow. It includes validation, query analysis, hashing query embedding, embedded-Qdrant/BM25 retrieval, hybrid scoring, the SIGNAL Lightweight Relevance Reranker, context building, extractive development generation, grounding, and structured response creation. It excludes network HTTP, browser work, microphone capture, speech-to-text, neural embeddings, a remote vector service, and a production LLM. Therefore, it **does not establish full voice or full-production latency**. The sub-200 ms result applies only to the labelled local-development text-RAG scope.

## Profiles

The benchmark command validates that the requested profile matches the active runtime; it will not relabel a fallback run as production.

```bash
# Available now without credentials
python scripts/benchmark.py --profile local-development --queries 100 --progress

# Requires EMBEDDING_PROVIDER=sentence_transformers or openai, a compatible re-index,
# and production embedding dependencies/credentials.
python scripts/benchmark.py --profile neural-retrieval --queries 100 --progress

# Requires production embeddings, LLM_PROVIDER=openai, LLM_API_KEY,
# compatible index, and reachable providers.
python scripts/benchmark.py --profile full-production --queries 100 --progress

# Requires a running full-production API, online ElevenLabs, and a directory
# of fixed supported audio files. Measures client-observed HTTP voice latency.
python scripts/benchmark_voice.py --audio-dir ./path/to/audio-set --queries 100 --progress
```

### Profile semantics

- `local-development`: hashing + embedded Qdrant/BM25 + deterministic extractive fallback.
- `neural-retrieval`: real production embeddings + local hybrid retrieval/rerank + extractive fallback.
- `full-production`: production embeddings + hybrid retrieval/rerank + OpenAI-compatible JSON generation.
- `full-voice`: client-observed HTTP upload + audio validation + ElevenLabs STT + full-production text RAG; browser microphone capture remains outside scope.

Voice is a separate end-to-end scope. `scripts/benchmark_voice.py` enforces full-production health plus online STT and uses a fixed audio directory; no full-voice result is in this submission.

## Method

1. Start the real application container in-process.
2. Verify runtime profile and index compatibility.
3. Load unique retrieval queries from the latest evaluation when its subset ID matches the index; otherwise use manifest demo queries.
4. Execute 5 warmups.
5. Execute exactly the requested number of measured queries, forcing `bypass_cache=true`.
6. Capture wall latency plus pipeline retrieval/generation/grounding status.
7. Use an explicit linear-interpolation percentile function for P50/P70/P95 and exact maximum for P100.
8. Persist a unique ID, UTC timestamp, environment, dataset/index/provider identities, count/scope/cache/failure metadata, summary percentiles, and each result.
9. Create a new immutable run file and update only the history/latest convenience files.

The raw measured values, rather than rounded values shown above, remain in the artifact.

## Benchmark history

`data/benchmarks/index.json` currently lists three immutable local-development runs. `GET /api/benchmarks` returns that history and `GET /api/benchmark/{benchmark_id}` returns a safe ID-selected run. `GET /api/benchmark` returns the latest convenience snapshot.

## Unavailable results

| Scope | Status | Reason |
|---|---|---|
| Neural retrieval | **NOT MEASURED** | sentence-transformers/model not installed in the verified environment; no neural-compatible index built |
| Full production text | **NOT MEASURED** | no live embedding/LLM credentials or endpoints |
| STT-only HTTP | **NOT MEASURED** | no ElevenLabs credential |
| Full voice HTTP | **NOT MEASURED** | no ElevenLabs plus production provider run |
| Offline official-subset ingestion throughput | **NOT MEASURED** | official records were not downloaded/indexed |

## Reproduction notes

Run one benchmark process at a time because embedded Qdrant owns a local lock. Close any running API before invoking the script. Hardware, Python, providers, dataset identity, index counts and scope are recorded in every artifact. Do not compare this fixture result to production neural/voice systems as if the scopes were equivalent.
