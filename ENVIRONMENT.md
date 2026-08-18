# SIGNAL Environment Contract

## Runtime profiles

SIGNAL derives its profile from configured embedding and generation providers:

- `local-development`: `EMBEDDING_PROVIDER=hashing`, `LLM_PROVIDER=extractive`
- `neural-retrieval`: production embedding provider, extractive generator
- `full-production`: production embedding provider, OpenAI-compatible generator

Speech state is reported separately. A full-production text profile can still report STT offline if `ELEVENLABS_API_KEY` is absent.

## Core variables

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | environment disclosure and development preview CORS |
| `DATA_DIR` | project `data/` | manifest, chunks, Qdrant and benchmark root |
| `CORS_ORIGINS` | localhost origins | comma-separated exact origins for browser access |
| `RATE_LIMIT_PER_MINUTE` | `60` | per-client POST limit |
| `MAX_AUDIO_BYTES` | `10485760` | hard audio read limit (10 MiB) |
| `MAX_RETRIES` | `1` | bounded generation retry count |

## Embeddings

| Variable | Development default | Production example |
|---|---|---|
| `EMBEDDING_PROVIDER` | `hashing` | `sentence_transformers` or `openai` |
| `EMBEDDING_MODEL` | resolved to `signal-hashing-v1` | `intfloat/multilingual-e5-small` |
| `EMBEDDING_DIMENSION` | `384` | must equal actual endpoint/model dimension |
| `EMBEDDING_DEVICE` | `cpu` | `cpu`, `cuda`, `mps`, or `auto` |
| `EMBEDDING_API_KEY` | empty | required for `openai` |
| `EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | trusted OpenAI-compatible endpoint |

Changing embedding provider, model, or dimension requires rebuilding the index. Startup intentionally rejects incompatible manifests; there is no silent fallback.

## Generation

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `extractive` | use `openai` for production structured generation |
| `LLM_MODEL` | `gpt-4o-mini` | model identifier sent to endpoint |
| `LLM_API_KEY` | empty | required for `openai` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | trusted endpoint |
| `LLM_TIMEOUT_S` | `12` | bounded request timeout |
| `LLM_MAX_TOKENS` | `700` | output token cap |

## Speech

| Variable | Default | Notes |
|---|---|---|
| `ELEVENLABS_API_KEY` | empty | absent means honest offline STT |
| `ELEVENLABS_STT_MODEL` | `scribe_v1` | speech-to-text model |
| `ELEVENLABS_STT_URL` | ElevenLabs API URL | set only to a trusted endpoint |
| `STT_TIMEOUT_S` | `20` | bounded request timeout |
| `STT_MAX_RETRIES` | `1` | transient timeout/429/5xx retry count |

## Retrieval and grounding

| Variable | Default |
|---|---:|
| `TOP_K_CANDIDATES` | 12 |
| `TOP_K_CONTEXT` | 4 |
| `CONTEXT_TOKEN_BUDGET` | 900 |
| `SEMANTIC_WEIGHT` | 0.55 |
| `LEXICAL_WEIGHT` | 0.35 |
| `METADATA_WEIGHT` | 0.10 |
| `MIN_RETRIEVAL_SCORE` | 0.20 |
| `MIN_QUERY_COVERAGE` | 0.30 |
| `GROUNDING_THRESHOLD` | 0.55 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 160 / 32 |

Weights must sum to 1. Configuration validation rejects invalid bounds.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Only for sentence-transformers E5 or official Hugging Face ingestion:
pip install -r requirements-ml.txt

cd frontend
npm ci
```

Create `.env` from `.env.example`; never commit it. `requirements-ml.txt` is optional because its model/runtime dependencies are large and not needed for honest local fallback operation.

## Production examples

### Neural retrieval, local extractive generation

```env
APP_ENV=production
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIMENSION=384
EMBEDDING_DEVICE=cpu
LLM_PROVIDER=extractive
```

### Full production text plus voice

```env
APP_ENV=production
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIMENSION=384
EMBEDDING_DEVICE=cpu
LLM_PROVIDER=openai
LLM_API_KEY=replace_me
LLM_MODEL=gpt-4o-mini
ELEVENLABS_API_KEY=replace_me
CORS_ORIGINS=https://your-signal.example
```

After changing embedding settings, run ingestion before starting the API. Provider keys stay on the backend.
