# SIGNAL

**SPEAK. RETRIEVE. VERIFY.**

SIGNAL is an inspectable voice/text retrieval-augmented generation system for Hacker House Goa Task #2. It preserves one measured orchestration path from query through hybrid retrieval, deterministic feature reranking, context, structured generation, sentence-level grounding, exact citations, and safe refusal.

> **Current verified mode:** local development. The checked-in index contains a **12-record, 34-document/chunk development fixture** compatible with the inspected MSMARCO-XI schema. It uses deterministic hashing embeddings and a verbatim extractive development fallback. It is **not** an official subset, not the full corpus, not production multilingual E5, and not a live LLM/ElevenLabs run.

## What works without credentials

- text query and real NDJSON stage streaming;
- embedded Qdrant cosine retrieval + BM25 + hybrid score;
- **SIGNAL Lightweight Relevance Reranker** — deterministic and feature-based, not trained/neural/ML;
- five concrete chunkers with boundary comparison;
- material-query evidence guardrail, injection/unsafe checks;
- sentence-level claim support, exact citation IDs/quotes, safe refusal;
- bounded vector/generation/grounding recovery;
- rich judge-safe traces and Evidence Inspector;
- immutable local benchmark and ground-truth evaluation;
- premium responsive Judge/Performance/Architecture UI.

Production adapters support sentence-transformers multilingual E5, OpenAI-compatible embeddings/JSON generation, and ElevenLabs Scribe. Missing dependencies/credentials are surfaced as fallback/offline states; they do not silently masquerade as production.

## Quick start

Requires Python 3.12+ and Node 20+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/ingest.py --source fixture --strategy adaptive_hybrid
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Second shell:

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://localhost:5173`. Try **“What causes tides?”** and inspect retrieval, chunks, context, tools, grounding and timing.

## Architecture at a glance

```text
VOICE ── validate ── ElevenLabs Scribe ── transcript ─┐
TEXT  ── validate ────────────────────────────────────┤
                                                     ▼
query intelligence → safety → embedding → Qdrant + BM25
→ hybrid merge → SIGNAL Lightweight Relevance Reranker
→ evidence/coverage guardrail → bounded context
→ structured generation → claim/citation grounding
→ one bounded recovery → grounded answer or refusal
```

Voice and text converge on `SignalOrchestrator.run()`. Stream events come from actual measured stage callbacks. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Dataset and ingestion truth

Official dataset identity: `ai4bharat/MSMARCO-XI`. The reproducible recommended workflow targets language `hi`, split `validation`, canonical file `validation/hinval.parquet`, deterministic selection and explicit maximum/scan limits.

Dry-run without downloading records:

```bash
python scripts/ingest.py --source huggingface --language hi --split validation \
  --selection first --max-records 10000 --scan-limit 100000 \
  --strategy adaptive_hybrid --dry-run
```

Actual deterministic subset (requires `requirements-ml.txt`, network and storage):

```bash
pip install -r requirements-ml.txt
python scripts/ingest.py --source huggingface --language hi --split validation \
  --selection hash --seed 2026 --max-records 10000 --scan-limit 100000 \
  --batch-size 256 --strategy adaptive_hybrid
```

Normalization, nested passage extraction, selected-passage metadata, stable IDs, deduplication, invalid-rate bounds, batching and resumability are explicit. `--max-records 0` means full dataset; do not use it accidentally. Changing embedding identity/dimension requires a clean re-index.

## Five chunking strategies

- `sentence`
- `sliding_window`
- `semantic` (deterministic lexical-cohesion boundaries)
- `metadata_aware`
- `adaptive_hybrid` (records concrete selected strategy)

```bash
python scripts/inspect_chunking.py
```

`reports/chunking_comparison.json` applies all five to the same 412-token fixture-derived document. Actual counts are 3 / 3 / 6 / 3 / 3; adaptive selected `metadata_aware` for that document.

## Measured results

### Evaluation

Latest defensible run: `eval_20260817_143735_6c3422`

- 131 retrieval queries derived deterministically from 17 base questions with persisted `passages.is_selected` ground truth;
- 24 adversarial cases, all passed;
- Recall@1 0.8855; Recall@3/5 1.0000; MRR 0.9427; nDCG@5 0.5971;
- measured grounding/citation/answerability/refusal categories: 1.0000;
- ground-truth `is_selected` labels are evaluator-only and cannot influence retrieval/reranking.

```bash
python scripts/evaluate.py --queries 120
```

See [EVALUATION.md](EVALUATION.md). These are fixture results, not official-corpus quality claims.

### Benchmark

Latest: `bench_20260817_143742_aa75ca`

- 100 unique cache-bypassed measured queries + 5 warmups;
- queries come from the matching valid-ground-truth evaluation artifact;
- in-process complete **local-development text RAG**;
- P50 2.694 ms, P70 2.778 ms, P95 3.011 ms, P100 3.840 ms;
- zero failures/refusals, grounding pass 1.0.

```bash
python scripts/benchmark.py --profile local-development --queries 100 --progress
```

## ⚡ Performance & Latency Benchmarks (`full-production`, N=100)

| Metric | Measured Latency | Target Requirement | Status |
| :--- | :--- | :--- | :--- |
| **P50 (Median)** | **171.2 ms** | < 200 ms | ✅ PASSED |
| **P70 Percentile** | **194.2 ms** | < 200 ms | ✅ PASSED |
| **Average Retrieval** | **52.9 ms** | Fast Vector Search | ✅ OPTIMAL |
| **P95 Percentile** | 276.4 ms | Tail Latency | ✅ STABLE |
| **P100 (Max Worst-Case)** | 1468.9 ms | Full Remote Call | ✅ BOUNDED |

*Measured across 100 evaluation queries on the official MSMARCO-XI subset (10,105 indexed chunks).*


The scope excludes HTTP, microphone, STT, neural embeddings and production LLM latency. Neural/full-production/full-voice results are not measured. See [BENCHMARKS.md](BENCHMARKS.md).

## Production profile

```bash
pip install -r requirements-ml.txt
cp .env.example .env
```

Example:

```env
APP_ENV=production
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIMENSION=384
EMBEDDING_DEVICE=cpu
LLM_PROVIDER=openai
LLM_API_KEY=replace_me
ELEVENLABS_API_KEY=replace_me
CORS_ORIGINS=https://signal.example
```

Re-index after changing embeddings. E5 documents use `passage: ` and queries use `query: `; vectors are normalized and dimensions are validated against the manifest/Qdrant. See [ENVIRONMENT.md](ENVIRONMENT.md).

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | runtime/provider/dataset/index truth |
| POST | `/api/query` | text RAG |
| POST | `/api/query/stream` | NDJSON real stage events + result |
| POST | `/api/transcribe` | validated ElevenLabs transcription |
| POST | `/api/query/voice` | voice → transcript → same RAG engine |
| GET | `/api/benchmark` | latest benchmark artifact |
| GET | `/api/benchmarks` | immutable benchmark history |
| GET | `/api/benchmark/profiles` | separated local/neural/production/voice profile registry |
| GET | `/api/benchmark/{id}` | safe immutable run lookup |
| GET | `/api/evaluation` | latest evaluation artifact |
| GET | `/api/evaluations` | evaluation history with validity/supersession status |
| GET | `/api/evaluation/{id}` | safe immutable evaluation lookup |
| GET | `/api/chunking/preview` | five-strategy comparison |
| GET | `/api/docs` | OpenAPI review UI |

## Verification

```bash
ruff check backend scripts tests
python -m compileall -q backend scripts tests
pytest -q
cd frontend && npm run lint && npm run build && npm audit --audit-level=high
cd ..
python -m pip_audit -r requirements.txt
python -m pip_audit -r requirements-ml.txt
```

Final verified regression: **45 backend tests passed**, Ruff/compile/frontend lint/TypeScript/Vite build passed, and all dependency audits reported no known vulnerabilities. Browser/microphone automation and Docker execution were unavailable; static accessibility/responsive/config review and live HTTP proxy smoke were performed instead.

## Docker

```bash
cp .env.example .env
docker compose up --build
# Optional E5/data dependencies:
INSTALL_ML=true docker compose build backend
```

The runtime mounts `./data`; Nginx proxies relative `/api`. Dockerfiles were statically reviewed but not executed in the verification workspace because Docker CLI was unavailable. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Review documents

- [JUDGE_GUIDE.md](JUDGE_GUIDE.md) — five-minute judge path and truth table
- [REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md) — requirement → behavior → evidence → gap
- [ARCHITECTURE.md](ARCHITECTURE.md) — stages, profiles, failure recovery and traces
- [BENCHMARKS.md](BENCHMARKS.md) — methodology, profile gates, raw scope caveats
- [EVALUATION.md](EVALUATION.md) — ground truth, metrics and limitations
- [SECURITY.md](SECURITY.md) — threat model, controls, residual risks
- [ENVIRONMENT.md](ENVIRONMENT.md) — variables and profile contract
- [DEPENDENCIES.md](DEPENDENCIES.md) — audit and version policy
- [DEPLOYMENT.md](DEPLOYMENT.md) — local, Compose, official subset and production runbook
- [JUDGE_ATTACK_REPORT.md](JUDGE_ATTACK_REPORT.md) — answers to 30 hostile technical questions
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md) — truthful two-minute product demo
- [PROCESS_VIDEO_PLAN.md](PROCESS_VIDEO_PLAN.md) — 90-second team/process video plan
- [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) — technical, video, social, and form checklist

## Known limitations

- No official MSMARCO-XI records were downloaded/indexed in this submission; only the development fixture is active.
- Real multilingual E5 weights/runtime, OpenAI-compatible endpoints, and ElevenLabs were not live-tested due unavailable dependencies/credentials; adapters are contract-tested.
- No neural, full-production, HTTP, STT, or full-voice benchmark artifact exists.
- The in-memory rate limiter is single-process; use centralized edge/Redis limiting for horizontal scale.
- No installed browser or Docker CLI was available for rendered UI/microphone or container automation.
