# SIGNAL Deployment

## Local VS Code / judge run

```bash
cd /path/to/signal
code .
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/ingest.py --source fixture --strategy adaptive_hybrid
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead of `source .venv/bin/activate`.

In a second VS Code terminal:

```bash
cd /path/to/signal/frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

Vite proxies relative `/api` calls to port 8000. Open `http://localhost:5173`.

## Docker Compose

```bash
cp .env.example .env
# Edit only local .env; never commit it.
docker compose up --build
```

Open `http://localhost:8080`. Nginx serves the compiled SPA and proxies `/api` to the single backend worker. `./data` is mounted for index/benchmark persistence.

For multilingual E5 or official ingestion dependencies:

```bash
INSTALL_ML=true docker compose build backend
```

The environment used to verify this submission did not include Docker CLI, so image build/compose runtime remains **not executed here**. Dockerfiles and Compose syntax were statically reviewed only.

## Official subset workflow

The official source is `ai4bharat/MSMARCO-XI`, language config `hi` by default, split `validation`, with canonical file `validation/hinval.parquet`. The workflow streams records and does not intentionally materialize the full corpus.

Validate configuration without download:

```bash
python scripts/ingest.py \
  --source huggingface \
  --language hi \
  --split validation \
  --selection first \
  --max-records 10000 \
  --scan-limit 100000 \
  --strategy adaptive_hybrid \
  --dry-run
```

Build a deterministic official subset (requires `requirements-ml.txt`, network, storage, and a production embedding configuration if production retrieval is intended):

```bash
python scripts/ingest.py \
  --source huggingface \
  --language hi \
  --split validation \
  --selection hash \
  --seed 2026 \
  --max-records 10000 \
  --scan-limit 100000 \
  --batch-size 256 \
  --strategy adaptive_hybrid
```

Use `--resume` only to continue an interrupted build with the same subset/index settings. A clean final build should omit it. `--max-records 0` means full dataset and is deliberately not the recommended judge workflow.

## Production rollout sequence

1. Provision TLS and an authenticated ingress/reverse proxy.
2. Choose and pin embedding provider/model/dimension/device.
3. Install optional ML dependencies or configure a trusted OpenAI-compatible embedding endpoint.
4. Configure OpenAI-compatible LLM and ElevenLabs credentials as secret environment variables.
5. Set exact `CORS_ORIGINS`, `APP_ENV=production`, upload/time/rate bounds.
6. Ingest the intended fixture/subset/full dataset with an explicit label; back up manifest/chunks/Qdrant together.
7. Start one embedded-Qdrant API worker per volume. For horizontal scale, move rate limiting and vector storage to shared production services.
8. Confirm `/api/health` reports expected provider modes and index compatibility.
9. Run regression, smoke, evaluation and the matching benchmark profile.
10. Configure logs/metrics, retention, provider quotas and alerts.

## Health and smoke

```bash
curl -fsS http://localhost:8000/api/health
curl -fsS -H 'content-type: application/json' \
  -d '{"query":"What causes tides?","bypass_cache":true}' \
  http://localhost:8000/api/query
curl -fsS http://localhost:8000/api/benchmark
curl -fsS http://localhost:8000/api/evaluation
```

A credentialless local deployment should report `degraded` / `development_fallback`, not full production. STT should report offline while text remains functional.

## Operational notes

- Embedded Qdrant uses a file lock: do not run ingestion/benchmark and the API concurrently against the same path.
- Keep `data/index/manifest.json`, `chunks.jsonl`, and `qdrant/` synchronized.
- Responses and artifact APIs use `Cache-Control: no-store`; Nginx may cache only fingerprinted static assets.
- The built frontend contains no backend secrets.
- Add centralized rate limiting before using multiple backend workers.
- Disable or protect API docs at the edge if they are not intended for public access.
