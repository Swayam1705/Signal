# SIGNAL Architecture

## System boundary

SIGNAL is one RAG engine with two ingress paths. Text enters `POST /api/query` or `/api/query/stream`. Voice enters `POST /api/query/voice`: the backend validates the upload, transcribes it through ElevenLabs Scribe, then passes the transcript to the **same** `SignalOrchestrator.run()` used by text. The browser never calls embedding, LLM, or speech providers directly and receives no provider credentials.

```text
Browser (voice or text)
  └─ FastAPI validation / rate control
      ├─ ElevenLabs Scribe (voice only)
      └─ Query intelligence + input guardrail
          └─ Query embedding
              ├─ Qdrant cosine candidates
              └─ BM25 lexical candidates / vector-failure fallback
                  └─ Hybrid score (semantic + lexical + metadata)
                      └─ SIGNAL Lightweight Relevance Reranker
                          └─ Evidence threshold + material-query coverage
                              └─ Bounded context with untrusted-evidence tags
                                  └─ Structured generation (or labelled extractive development fallback)
                                      └─ Claim, citation, and exact-quote grounding
                                          ├─ one strict regeneration attempt
                                          └─ grounded answer or safe refusal
```

## Measured orchestration stages

| # | Stage | Implementation | Observable output |
|---:|---|---|---|
| 1 | Ingress | FastAPI + Pydantic + audio signature checks | request/input mode; stable errors |
| 2 | Speech | ElevenLabs Scribe adapter | transcript, language, confidence, STT time |
| 3 | Query analysis | deterministic normalization, language/intent/mode selection | safety/query/retrieval plans |
| 4 | Input guardrail | injection, unsafe, empty/length validation | pass/refusal flags |
| 5 | Embedding | multilingual E5 query prefix in production; hashing only in development | provider/model/mode/dimension |
| 6 | Vector retrieval | Qdrant cosine | semantic candidates/scores |
| 7 | Lexical retrieval | BM25 | lexical candidates/scores |
| 8 | Hybrid merge | mode-sensitive weighted score | effective weights/ranks |
| 9 | Reranking | **SIGNAL Lightweight Relevance Reranker**, deterministic feature-based | before/after ranks and score |
| 10 | Evidence guardrail | score plus material-term coverage | evidence decision/refusal reason |
| 11 | Context build | bounded XML-like evidence records | exact context sent to generator |
| 12 | Generation | OpenAI-compatible structured JSON or labelled extractive fallback | attempts/model output/recovery |
| 13 | Grounding | per-claim support, citation IDs, exact quotes | grounding score, claims, final status |

Every stage is timed with `perf_counter`. The trace carries request ID, UTC timestamp, input mode, transcript (voice), plans, candidates, scores, selected evidence, context, model output, grounding, guardrails, tool executions, retry count, recovery actions, and cache state. NDJSON streaming events are emitted by the actual measured callbacks rather than a browser timer.

## Retrieval and failure recovery

Qdrant and BM25 are queried as a hybrid path. Semantic, lexical, and legitimate query-derived metadata scores are retained independently. MSMARCO `is_selected` relevance labels are persisted for evaluation but explicitly excluded from online retrieval and reranking. Retrieval mode controls the effective weights. If vector retrieval raises, the orchestrator performs one explicit lexical-only recovery and records `VECTOR_RETRIEVAL_FAILED → BM25_FALLBACK`. Generation uses bounded attempts (`MAX_RETRIES`, default 1). Timeout/provider/malformed-output and grounding failure are traced; after the retry budget, SIGNAL refuses rather than returning unsupported text.

## Embedding modes and compatibility

- `sentence_transformers`: `intfloat/multilingual-e5-small` by default; `query: ` and `passage: ` semantics; normalized vectors; batch encode; CPU by default (`EMBEDDING_DEVICE=cpu`). Startup fails if dependencies/model are unavailable.
- `openai`: OpenAI-compatible `/embeddings`, bounded HTTP timeout, required API key, configured dimension validation.
- `hashing`: `signal-hashing-v1`, a deterministic 384-dimensional **development fallback**, never presented as neural E5.

The index manifest persists provider/model/dimension. Startup rejects mismatches (`INDEX_EMBEDDING_MISMATCH`, `INDEX_DIMENSION_MISMATCH`, or vector-store dimension mismatch); it does not silently swap embedding models.

## Five actual chunkers

`sentence`, `sliding_window`, `semantic`, `metadata_aware`, and `adaptive_hybrid` all create concrete `Chunk` records with strategy, chunk index, token/character counts, overlap, stable chunk/embedding IDs, source, document/record IDs, language and selected-passage metadata. Adaptive hybrid executes a deterministic document-feature policy and records its concrete selected strategy. `reports/chunking_comparison.json` applies all five to the same 412-token document and stores the real boundaries.

## Runtime profiles

| Profile | Embedding | Generation | Intended measurement |
|---|---|---|---|
| `local-development` | hashing fallback | extractive fallback | offline text-RAG correctness and local latency |
| `neural-retrieval` | multilingual E5 or configured OpenAI embeddings | extractive fallback | neural retrieval latency/quality |
| `full-production` | production embeddings | OpenAI-compatible LLM | credentialed production text-RAG; voice adds ElevenLabs STT |

The benchmark script refuses a profile that does not match the active runtime. Provider and dataset modes surface through `/api/health` and the UI.

## Persistence and artifact flow

- Source/fixture: `data/source/`
- Canonical chunks: `data/index/chunks.jsonl`
- Qdrant embedded collection: `data/index/qdrant/`
- Index identity: `data/index/manifest.json`
- Immutable benchmark runs: `data/benchmarks/bench_<timestamp>_<id>.json`
- Benchmark history/latest pointers: `data/benchmarks/index.json`, `latest.json`
- Immutable evaluations: `reports/evaluations/eval_<timestamp>_<id>.json`
- Evaluation convenience snapshot: `reports/evaluation.json`
- Five-strategy comparison: `reports/chunking_comparison.json`

## Frontend

React + TypeScript consumes relative `/api` endpoints. Home shows actual stream events and result traces. Evidence Inspector exposes score components, ranks, context, tools, retries, grounding and guardrails. Performance and Judge Mode load backend artifacts; they do not embed benchmark/evaluation constants. Architecture nodes are keyboard-focusable buttons. Styling includes visible focus, labels, 320 px responsive rules, and reduced-motion handling.
