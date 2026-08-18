# SIGNAL Requirement Traceability

Status vocabulary: **Verified** means behavior was executed in this workspace; **Contract-tested** means the adapter behavior was exercised with deterministic fakes but no live credentialed provider; **Implemented / unavailable to execute** is not counted as a live verification.

| Requirement | Implementation | Behavioral evidence | Status / gap |
|---|---|---|---|
| Voice-enabled RAG | `/api/query/voice`, ElevenLabs adapter, common orchestrator | audio/error API tests; STT success/failure contract tests | Contract-tested; live credential unavailable |
| Text RAG | `/api/query`, `/api/query/stream` | live Vite-proxied query and NDJSON smoke; API tests | Verified |
| Same voice/text engine | voice route transcribes then creates `QueryRequest` for `SignalOrchestrator` | route tests/source path | Verified structurally; live STT unavailable |
| Official MSMARCO-XI workflow | deterministic `scripts/ingest.py` streaming workflow | Hindi validation `hinval.parquet` dry-run | Verified dry-run; no official records indexed |
| Fixture/subset/full identity | manifest/health/runtime labels | final manifest `development_fixture` | Verified |
| Cleaning/dedupe/batch/progress/recovery | normalization, stable IDs, invalid-rate bound, upsert batches, resume | clean ingestion + 12-record resume verification | Verified on fixture |
| Five chunkers | sentence/window/semantic/metadata/adaptive classes | same 412-token comparison artifact; unit boundary test | Verified |
| Adaptive concrete choice | feature policy records selected strategy | comparison chose `metadata_aware`; fixture records `sentence` | Verified |
| Vector database | embedded Qdrant cosine collection | 34 chunks loaded; health online; query smoke | Verified local |
| BM25 | in-memory lexical index | hybrid traces; vector-failure fallback test | Verified |
| Hybrid scoring | semantic/lexical/metadata weights | candidates retain component/hybrid scores | Verified |
| Reranking | SIGNAL Lightweight Relevance Reranker | ranks/scores in trace; deterministic tests | Verified; explicitly not trained/neural/ML |
| Production multilingual E5 | sentence-transformers adapter with query/passage prefixes, normalization, CPU device, dimension checks | adapter contract test and index mismatch test | Contract-tested; model/runtime not installed |
| No silent embedding fallback | explicit provider construction and manifest compatibility failure | provider mode + mismatch tests | Verified |
| Real JSON generation adapter | OpenAI-compatible chat completions + Pydantic schema | payload/schema/token/key-separation test; timeout/malformed recovery tests | Contract-tested; no live endpoint |
| ElevenLabs Scribe | multipart provider with bounded timeout/retry/schema | timeout, malformed and successful response tests | Contract-tested; no live key |
| Guardrails | injection/unsafe/evidence/query coverage | 24-case evaluator + API suite | Verified |
| Grounding | sentence claims, exact IDs/quotes | evaluation 1.0; unsupported-claim retry/refusal test | Verified |
| Bounded recovery | vector→BM25; generation retry; grounding retry→refusal | semantic recovery unit tests and traces | Verified |
| Inspectable trace | plans, candidates, context, model output, tools, grounding, timings | live query smoke and Evidence Inspector | Verified |
| Real streaming | callbacks from measured operations | NDJSON API test/live smoke | Verified |
| Benchmark percentiles | unique immutable run with P50/P70/P95/P100 and environment/scope | `bench_20260817_143742_aa75ca` | Verified local scope only |
| Sub-200 ms target | local text RAG P100 3.840 ms | 100-unique-query artifact | Verified only for labelled local in-process scope |
| Production/voice latency | profile-gated benchmark support | no artifacts | Not measured; credentials/runtime unavailable |
| ≥100 retrieval evaluation | evaluator-only selected-passage labels, deterministic variants | 131 queries, Recall@1/3/5, MRR, nDCG@5; ranking-label isolation regression | Verified on fixture |
| 24 adversarial/failure scenarios | JSON evaluator plus expanded API/provider/recovery suite | evaluator all pass; 45 tests | Verified across evaluation + tests |
| Judge Mode / Evidence Inspector | backend-driven React views | frontend lint/build; live server smoke | Verified statically/live HTTP; no rendered browser automation |
| Performance from artifacts | `/api/benchmark`, `/api/evaluation`, `/api/chunking` | endpoint tests and live smoke | Verified |
| Responsive/accessibility | mobile/tablet CSS, labels, focus, reduced motion, semantic controls | static review + lint/build | Static verified; browser/AT automation unavailable |
| Security | server secrets, CORS, upload/rate/path/output controls, headers | semantic tests; live header checks; `SECURITY.md` | Verified where executable |
| Dependency audit | pip-audit core/ML, npm audit | all final audits report no known vulnerabilities | Verified |
| Deployment | Docker/Nginx/Compose configs | static review | Docker runtime unavailable |
| Clean archive | deterministic exclusion and ZIP inspection | final archive SHA/file count to be recorded in final report | Pending until packaging |

## Latest artifact identities

- Index: `idx_20260817_143458_3fda05`
- Dataset subset identity: `subset_dc24a3b1ee3fda05` (development fixture identity, not official subset)
- Evaluation: `eval_20260817_143735_6c3422`
- Benchmark: `bench_20260817_143742_aa75ca`
- Chunk comparison: `reports/chunking_comparison.json`
