# SIGNAL — HH Goa 2026 Task 2 Submission Checklist

Deadline: **August 22, 2026 at 11:59 PM**. Complete human-owned/publication items before the deadline. Checked technical items were verified in the local submission workspace; they do not imply completion of external publishing steps.

## Technical

- [ ] GitHub repository created and pushed
- [ ] Public/live URL deployed and tested from a separate device/network
- [ ] Live ElevenLabs voice demo tested with a real key
- [x] Text fallback works without provider credentials
- [x] Browser microphone and voice API contracts implemented
- [x] Official dataset workflow targets `ai4bharat/MSMARCO-XI`
- [x] Fixture / official subset / full dataset identities remain distinct
- [ ] Official subset actually downloaded/indexed, if the team chooses to claim it
- [x] Five distinct chunking strategies verified
- [x] Embedded Qdrant stores/retrieves real vectors
- [x] BM25 lexical retrieval verified
- [x] Hybrid score decomposition exposed
- [x] SIGNAL Lightweight Relevance Reranker is deterministic and honestly labelled
- [x] Grounding and exact citations verified
- [x] Guardrails and safe refusal verified
- [x] P50 measured and artifact-backed
- [x] P70 measured and artifact-backed
- [x] P95 measured and artifact-backed
- [x] P100 measured and artifact-backed
- [x] 100+ cache-bypassed benchmark requests
- [x] Benchmark profile/scope/warmups/providers/failures recorded
- [x] 100+ retrieval evaluation instances with valid labels
- [x] Recall@1/3/5, MRR and nDCG@5 reported
- [x] Semantic regression suite passes
- [x] Frontend lint and production build pass
- [x] Dependency audits pass
- [x] README and judge documentation included
- [x] Final ZIP opens and passes CRC/content checks

## Videos

- [ ] 90-second team/process video recorded
- [ ] Process video contains only real team/process footage
- [ ] End-to-end demo video recorded
- [ ] Demo shows success, evidence, grounding, refusal, and injection defense
- [ ] Demo truthfully discloses provider/dataset/benchmark mode
- [ ] Captions and audio reviewed

## Promotion

- [ ] Instagram post by every team member
- [ ] X post by every team member
- [ ] LinkedIn post by every team member
- [ ] `#RAGInGoa` included exactly
- [ ] At least one required Instagram account is public
- [ ] All post URLs collected in one submission note
- [ ] Every post checked while logged out / in a private window

## Submission

- [ ] Official form opened and required fields reviewed
- [ ] GitHub URL entered
- [ ] Live application URL entered
- [ ] Process-video links entered
- [ ] End-to-end demo-video links entered
- [ ] Social links for every member entered
- [ ] Team names/contact details verified
- [ ] Final response reviewed for truthful dataset/provider/latency claims
- [ ] Form submitted before August 22, 2026, 11:59 PM
- [ ] Submission confirmation saved

## Final truth checks

- [ ] No claim says the full MSMARCO-XI corpus was indexed unless that was actually completed
- [ ] No claim calls the current fixture an official subset
- [ ] No claim calls local text latency full voice latency
- [ ] No claim calls the deterministic reranker trained, neural, transformer, or ML
- [ ] No claim says ElevenLabs, a remote LLM, or E5 is online unless health verifies it
- [ ] Published demo matches the commit and deployment being submitted

## Exact GitHub commands

Run only after choosing the correct GitHub account/organization and repository URL:

```bash
cd /path/to/signal
git init
git branch -M main
git add .
git status --short
git commit -m "Submit SIGNAL for HH Goa 2026 Task 2"
git remote add origin https://github.com/REPLACE_OWNER/REPLACE_REPOSITORY.git
git push -u origin main
```

Before pushing, verify `.env`, credentials, dependencies, caches, model weights, downloaded corpora, and local artifacts are absent from `git status`.
