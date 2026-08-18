# SIGNAL Dependency Policy

## Dependency sets

### Core backend — `requirements.txt`

FastAPI/Uvicorn, Pydantic, multipart parsing, HTTPX, NumPy, Qdrant client, and testing/lint tooling. This set runs the complete labelled local-development path and production HTTP adapters without installing a neural model.

### Optional ML/data — `requirements-ml.txt`

Sentence Transformers, Transformers, Hugging Face Datasets, and PyArrow. Install this set only for production multilingual E5 or official dataset ingestion. It is separated to keep the default submission small and reproducible.

### Frontend — `frontend/package-lock.json`

React, React DOM, Vite, TypeScript, ESLint and their locked transitive dependencies. Production output is static HTML/CSS/JavaScript behind Nginx.

## Audit results — 2026-08-17

```text
python -m pip_audit -r requirements.txt       → No known vulnerabilities found
python -m pip_audit -r requirements-ml.txt    → No known vulnerabilities found
npm audit --audit-level=high                  → found 0 vulnerabilities
```

The initial optional-ML audit found advisories in a resolver result using PyArrow 19.0.1 and Transformers 4.57.6. The security floors were updated to PyArrow 23.0.1 and Transformers 5.5.0, with Sentence Transformers 5.2.3+, then the audit passed.

## Reproducibility

- Frontend installs use `npm ci` and the committed lockfile.
- Python uses bounded compatible ranges rather than exact transitive locks. For regulated/release builds, generate and review a hash-locked environment for the deployment platform.
- The Docker backend accepts `--build-arg INSTALL_ML=true`; the default image installs only core dependencies.
- Model weights are not committed. Production E5 downloads must be pinned/cached by the deployment process and included in its software bill of materials.

## Maintenance policy

1. Run both `pip-audit` commands and `npm audit` before release.
2. Review changelogs before major upgrades; do not auto-accept provider schema changes.
3. Re-run adapter, retrieval, full regression, benchmark, and evaluation suites after dependency changes.
4. Rebuild the vector index if embedding model behavior or dimensions change.
5. Scan built container images in CI; this was not possible in the verified workspace because Docker CLI is unavailable.
6. Keep runtime dependencies out of the source archive (`.venv`, `node_modules`, build output, model caches).
