# SIGNAL Security Review

Review date: 2026-08-17

## Trust boundaries

1. **Browser → API:** all query text, metadata filters, uploaded filenames/MIME types/audio bytes, and forwarded client address are untrusted.
2. **API → providers:** evidence and prompts leave the deployment only when a configured OpenAI-compatible, embedding, or ElevenLabs endpoint is called.
3. **Retrieved evidence → generator:** passages are data, not instructions. They are delimited and the generation prompt explicitly treats them as untrusted evidence.
4. **Artifacts → browser:** only fixed report locations and identifier-constrained benchmark files are exposed.
5. **Secrets:** provider credentials are backend environment variables only.

## Implemented controls

### Input and upload

- Pydantic validates trimmed query length (1–1000), `top_k`, language, and request shape.
- Uploads are read only to `MAX_AUDIO_BYTES + 1`, limiting memory use; default maximum is 10 MiB.
- Allowed MIME types and container signatures are checked; empty, oversized, unsupported, and malformed audio return stable 4xx errors.
- Original upload paths are never opened or interpolated into a filesystem path.
- POST requests use a per-client fixed-window rate limiter and semantic `429 RATE_LIMIT_EXCEEDED` response with `Retry-After`.

### Prompt, evidence, and output

- Direct and common indirect prompt-injection patterns are rejected before provider calls.
- Unsafe instruction patterns refuse.
- Evidence must pass both relevance score and material-query coverage.
- Context carries exact document/chunk IDs and treats contents as untrusted evidence.
- Generation requests structured JSON; malformed output is retried within a fixed budget and then refused.
- Grounding checks every sentence, citation ID, and exact quote; unsupported output gets one strict regeneration and then a safe refusal.
- Responses never execute retrieved text or model-produced code.

### Provider and secret handling

- `.env`, `.env.*`, PEM, and key files are ignored; `.env.example` contains placeholders only.
- API keys are added to backend provider headers and are not placed in traces, responses, artifacts, frontend source, or provider request bodies.
- Provider base URLs come only from deployment environment, not request data, reducing SSRF exposure.
- OpenAI-compatible calls and ElevenLabs use bounded timeouts; STT has bounded retries only for transient timeout/5xx/429 cases.
- No silent credentialless production fallback: provider construction fails or health reports offline/degraded.

### HTTP and browser

- Production CORS uses only configured origins. Development additionally allows the sandbox preview host pattern.
- Methods are limited to GET/POST/OPTIONS and accepted CORS headers to Content-Type/Accept.
- API responses set `nosniff`, `DENY`, no-referrer, restrictive permissions policy, no-store, and a data-API CSP (`default-src 'none'; frame-ancestors 'none'; base-uri 'none'`).
- Nginx applies a restrictive same-origin CSP, HSTS on TLS deployments, request size limit, proxy timeouts, and static cache rules.
- Frontend calls relative `/api` paths, keeping provider endpoints and keys outside browser code.

### Files and logs

- Benchmark IDs must match `bench_[A-Za-z0-9_-]+`; route strings cannot become arbitrary paths.
- APIs read only known report files and return `available: false` when absent.
- Structured stage logs contain request/stage/status/timing/error type, not provider keys or authorization headers.
- The final archive process excludes `.env`, credentials, dependencies, caches, build outputs, locks, logs, downloaded corpora, and superseded ZIPs.

## Dependency audit

Commands executed on 2026-08-17:

```bash
python -m pip_audit -r requirements.txt
python -m pip_audit -r requirements-ml.txt
cd frontend && npm audit --audit-level=high
```

Final results: no known vulnerabilities in core Python requirements, optional ML requirements, or npm lockfile. The first optional-ML audit identified vulnerable older `pyarrow`/`transformers` resolutions; minimums were raised to `pyarrow>=23.0.1` and `transformers>=5.5.0`, and the audit then passed. Docker image scanning was not run because Docker CLI is unavailable.

## Residual risks and deployment actions

- The in-memory rate limiter is per process, resets on restart, and trusts the direct socket client. Multi-worker/public deployment should use a shared Redis/gateway limiter and a trusted-proxy policy.
- Regex guardrails reduce common attacks but are not a complete content-safety system. High-risk public deployment needs stronger moderation and abuse monitoring.
- Embedded Qdrant is a local process store, not a network-isolated clustered service. Restrict volume permissions and use backups; use authenticated remote Qdrant if scale requires it.
- Traces intentionally expose evidence/context for judges. In production, add authentication/authorization and retention controls where the indexed corpus is sensitive.
- API docs are enabled for review. Disable or protect them at the edge for a private production deployment.
- TLS termination is expected at the reverse proxy/platform. HSTS has effect only over HTTPS.
- Credentialed provider behavior was contract-tested with mocks, but no live penetration or vendor-endpoint test was possible without credentials.
- No browser-driven XSS scanner, DAST, container scanner, or microphone permission automation was available in this environment.

## Incident-safe behavior

Provider/network/schema failures produce typed errors, bounded retries, recorded recovery actions, and safe refusals. SIGNAL does not return a best-effort unsupported answer after grounding or provider failure. Health reports service states independently so a local fallback cannot masquerade as full production.
