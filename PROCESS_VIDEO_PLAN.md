# SIGNAL — 90-Second Team / Process Video Plan

Official deliverable: a 90-second **team/process** video. This is distinct from the end-to-end product demo.

Do not fabricate team members, footage, conversations, or provider runs. Replace every bracketed placeholder with real human names, roles, clips, and artifacts before publishing.

## Format

- Duration: 85–90 seconds
- Orientation: record one high-resolution master that can be safely cropped for Instagram, X, and LinkedIn
- Tone: direct engineering narrative, not a feature commercial
- On-screen text: large, high contrast, platform-safe margins
- Audio: human narration; captions burned in

## 00:00–00:10 — Problem

**Footage:** `[TEAM MEMBER / REAL WORKSPACE CLIP]`

**Narration:**

> RAG systems can sound confident without showing whether the answer is supported. For HH Goa Task 2, we built SIGNAL to make voice retrieval measurable, inspectable, and safe to refuse.

**Overlay:** `VOICE → EVIDENCE → VERIFICATION`

## 00:10–00:25 — Architecture decision

**Footage:** architecture page or a real whiteboard/code review clip.

**Narration:**

> We kept voice and text on one typed orchestration path. ElevenLabs produces the transcript; Qdrant and BM25 retrieve complementary candidates; a deterministic low-latency reranker orders them; grounding validates claims and exact quotes.

**Overlay:** `ONE ORCHESTRATOR · HYBRID RETRIEVAL · GROUNDED OUTPUT`

## 00:25–00:40 — Dataset and chunking work

**Footage:** real ingestion code, manifest, and five-strategy comparison.

**Narration:**

> We inspected the MSMARCO-XI schema, built deterministic subset tooling, retained selected-passage labels only for evaluation, and compared sentence, sliding, semantic, metadata-aware, and adaptive chunk boundaries on the same document.

**Overlay:** `5 REAL CHUNKERS · REPRODUCIBLE INDEX`

## 00:40–00:57 — Iteration and red-team

**Footage:** `[REAL TEST RUN / TEAM DEBUGGING CLIP]`, failure traces, refusal demo.

**Narration:**

> We red-teamed prompt injection, no-evidence questions, malformed model output, provider timeouts, Qdrant failure, invalid audio, grounding failures, and rate limits. Failures produce bounded recovery or a typed refusal—not an unsupported answer.

**Overlay:** `BREAK IT → TRACE IT → FIX THE ROOT CAUSE`

## 00:57–01:12 — Measurement discipline

**Footage:** Performance and Evaluation pages.

**Narration:**

> Our evaluation uses persisted relevance labels. Our benchmark bypasses response cache and records immutable profile, scope, warmups, percentiles, providers, and failures. We never call local text latency full voice latency.

**Overlay:** `VALID LABELS · IMMUTABLE RUNS · HONEST SCOPE`

## 01:12–01:25 — Engineering proof

**Footage:** actual terminal output for Ruff, tests, build and audits.

**Narration:**

> We finished with semantic regression tests, frontend build checks, dependency audits, security review, live API smoke tests, and a clean reproducible archive.

**Overlay:** `[FINAL REAL TEST COUNT] · AUDITED · REPRODUCIBLE`

## 01:25–01:30 — Team close

**Footage:** `[ALL REAL TEAM MEMBERS ON CAMERA OR REAL SHARED WORK CLIP]`

**Narration:**

> We are `[TEAM NAME / MEMBER NAMES]`. This is SIGNAL. Less noise. More signal.

**Overlay:** `#RAGInGoa`

## Required human completion before publishing

- [ ] Insert real team member names and roles
- [ ] Record real team/process footage
- [ ] Replace final test-count placeholder with the final verified result
- [ ] Add accurate captions
- [ ] Confirm no secrets, tokens, personal notifications, or private URLs appear
- [ ] Obtain consent from every visible person
- [ ] Export platform-safe master and review the full 90 seconds
- [ ] Publish through every required team-member account
