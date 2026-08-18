# SIGNAL — Hostile Judge Attack Report

Review date: 2026-08-17. “Verified” means executed behavior; “contract-tested” means a real adapter was exercised with deterministic fake transport because credentials were unavailable.

| # | Hostile question | Defensible answer and proof | Outcome |
|---:|---|---|---|
| 1 | Is this really voice-enabled? | Browser MediaRecorder, validated audio routes, ElevenLabs Scribe adapter, voice NDJSON route and STT telemetry exist. | Contract-tested; live key unavailable |
| 2 | Is voice connected to RAG? | Voice transcript is converted to `QueryRequest(input_mode="voice")` and passed to the same `SignalOrchestrator.run()`. One request ID spans STT and RAG streaming stages. | Verified by semantic API test |
| 3 | Is this RAG or just LLM output? | Generation cannot run until Qdrant/BM25 candidates pass evidence thresholds and context is built. Credentialless mode returns verbatim extractive evidence. | Verified |
| 4 | Where is the dataset? | Active manifest/chunks/Qdrant are under `data/index`; source is a 12-record MSMARCO-XI-schema development fixture. | Verified and visibly labelled |
| 5 | What chunkers exist? | Sentence, sliding-window, semantic, metadata-aware, adaptive hybrid. | Verified |
| 6 | Are they actually different? | One 412-token document produces counts 3/3/6/3/3 with different boundaries/overlap/prefixes. | Verified artifact |
| 7 | Why Qdrant? | Persistent cosine vector retrieval with payload metadata and filtering; dimensions are checked against runtime. | Verified local embedded mode |
| 8 | Why BM25? | Exact-term recall complements vectors and remains a real fallback on vector failure. | Verified |
| 9 | Why hybrid? | Component pools are unioned; semantic, lexical and legitimate query-derived metadata scores remain individually inspectable. | Verified |
| 10 | What does reranking do? | It reorders candidates using hybrid score, material query coverage and phrase match. | Verified with before/after ranks |
| 11 | Is the reranker ML? | No. It is the deterministic feature-based SIGNAL Lightweight Relevance Reranker. | Honest label enforced |
| 12 | What happens when retrieval fails? | Vector exception is recorded; BM25-only retrieval runs with fallback status. | Verified test |
| 13 | What happens when the model hallucinates? | Sentence claims, IDs and exact quotes are checked; one strict regeneration is allowed, then refusal. | Verified test |
| 14 | What happens outside the dataset? | Score and material-query coverage guardrails produce a no/low-evidence refusal. | Verified demo B |
| 15 | What about prompt injection? | Direct injection rejects before retrieval; suspicious retrieved instructions are removed. | Verified demo C and tests |
| 16 | Where are citations? | Structured answer includes document ID, chunk ID and verbatim quote. | Verified |
| 17 | Can I inspect evidence? | Evidence Inspector shows source, IDs, strategy, vector/BM25/metadata/hybrid/rerank scores, rank change, and exact cited support. | Verified frontend build/API |
| 18 | What does latency include? | Every artifact states profile and exact measurement scope. | Verified |
| 19 | How many benchmark requests? | Latest final run is regenerated after this red-team pass; artifact records count, warmups and unique query count. | Artifact-backed |
| 20 | Are numbers real? | Timed with `perf_counter`; per-query rows retained; response cache bypassed. | Verified |
| 21 | Is ~2 ms production latency? | No. It is only local in-process development text RAG. Production/voice profiles remain separate and unavailable. | Explicit UI/docs disclosure |
| 22 | Can I see the full pipeline? | Home real-time rail, Evidence Inspector, Pipeline page and 13-node Architecture page. | Verified |
| 23 | What if LLM JSON is malformed? | Provider envelope is typed; Pydantic validates output; bounded strict retry then safe refusal. | Verified tests |
| 24 | What if ElevenLabs is unavailable? | Health says `OFFLINE — ELEVENLABS_API_KEY REQUIRED`; text remains operational; voice returns typed 503/error event. | Verified |
| 25 | What if Qdrant is unavailable? | Startup/index checks prevent false online health; runtime vector exception can recover to BM25. | Verified contract/test |
| 26 | Can another engineer reproduce it? | Exact environment, ingestion, evaluation, benchmark, test, local, Docker and packaging commands are documented. | Verified where environment permits |
| 27 | What did you build? | Typed orchestration, ingestion/chunking, hybrid retrieval, deterministic reranking, provider adapters, grounding, guardrails, evaluation/benchmarking and judge UI. | Repository traceable |
| 28 | What is fallback? | Hashing embeddings and extractive generation are labelled development fallbacks; STT is offline without key. | Health/UI verified |
| 29 | What is production? | Multilingual E5/OpenAI-compatible embeddings, OpenAI-compatible JSON generation and ElevenLabs Scribe adapters. | Contract-tested, not live |
| 30 | Why shortlist it? | SIGNAL combines voice readiness with evidence-first retrieval, inspectable decisions, measured restraint, reproducibility and honest scope. | Judge decision |

## Red-team weakness found and fixed in this pass

The hostile audit discovered that `passages.is_selected`—the evaluation relevance label—was contributing a metadata bonus in hybrid retrieval and reranking. That is evaluation leakage and could make quality metrics indefensible. It was removed from all online ranking features. Metadata scoring now uses only explicit request filters or query/chunk language match. A regression test proves toggling `is_selected` cannot change rerank score. Evaluation and benchmark artifacts were regenerated after this fix; old immutable runs remain historical and must not be presented as latest.

## Remaining attack surface

- Live voice cannot be proved without a real ElevenLabs credential and audio recording.
- Production E5/LLM behavior is adapter-contract-tested, not vendor-live-tested.
- The active corpus is a small development fixture, not the official subset.
- Lexical grounding is inspectable but not a full multilingual NLI model.
- Embedded Qdrant and in-memory rate limiting are single-process deployment choices.
- Browser/assistive-technology and Docker automation are unavailable in this workspace.
