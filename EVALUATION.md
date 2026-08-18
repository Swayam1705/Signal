# SIGNAL Evaluation

## Latest defensible run

Evaluation ID: `eval_20260817_143735_6c3422`

Artifact: `reports/evaluations/eval_20260817_143735_6c3422.json`

| Measure | Result |
|---|---:|
| Retrieval queries | 131 |
| Unique ground-truth base questions | 17 |
| Adversarial cases | 24 |
| Recall@1 | 0.885496 |
| Recall@3 | 1.000000 |
| Recall@5 | 1.000000 |
| MRR | 0.942748 |
| nDCG@5 | 0.597109 |
| Grounding pass | 1.000000 |
| Citation validity | 1.000000 |
| In-domain answerability | 1.000000 |
| Direct injection refusal | 1.000000 |
| Indirect injection refusal | 1.000000 |
| Unsafe refusal | 1.000000 |
| Off-topic refusal | 1.000000 |
| No-evidence refusal | 1.000000 |

All 24 adversarial cases passed.

## Critical red-team correction: relevance-label isolation

The final hostile audit found a genuine evaluation flaw in older runs: `passages.is_selected`, which is the relevance ground-truth label, contributed a small metadata bonus in online hybrid retrieval and reranking. That is label leakage. It was removed completely.

The final ranking path uses only:

- query/document vectors;
- BM25 terms;
- explicit request metadata filters or query/chunk language match;
- deterministic query coverage and phrase features.

`is_selected` is now read **only by the evaluator** after ranking. A regression test proves that toggling the label cannot change rerank score. Consequently, the older Recall@1 value of 0.946565 is superseded and must not be presented as the final defensible result. The leakage-free Recall@1 is 0.885496.

Historical immutable artifacts remain under `reports/evaluations/` for audit transparency. `reports/evaluations/index.json` marks leaked runs invalid and identifies the latest valid run. The API exposes `/api/evaluations` and safe by-ID lookup.

## Ground-truth integrity

Relevant document IDs come only from `passages.is_selected` metadata persisted from indexed MSMARCO-XI-schema records. The 131 retrieval queries are deterministic surface forms of 17 unique questions with those labels. Surface variation expands robustness coverage without creating new relevance judgments.

This evaluation uses the bundled **development fixture**: 12 schema-compatible records and 34 documents/chunks. It is not an official MSMARCO-XI subset score and must not be generalized to the full corpus.

## Multilingual correction

The audit also found that Python `\w` tokenization fragmented Devanagari combining marks, causing exact Hindi/Marathi extracted claims to fail lexical grounding. Retrieval, reranking, hashing, chunk counts, evidence coverage and grounding now share dependency-free Unicode letter/number/combining-mark tokenization. Exact Indic evidence is grounded correctly.

Material-query coverage remains 0.30 for ASCII-script queries. Indic-script queries use a documented 0.20 lexical floor because inflection can reduce exact surface overlap even when retrieval and citation support are valid. Score, exact citation and sentence grounding checks still apply.

## Metric definitions

- **Recall@k:** at least one selected document appears in the first `k` retrieved candidates.
- **MRR:** reciprocal rank of the first selected document, averaged across queries.
- **nDCG@5:** binary gain from persisted `is_selected` labels, discounted by rank and normalized to each query's ideal ranking.
- **Grounding pass:** a completed answer passes sentence-level support and exact citation/quote validation.
- **Citation validity:** every returned citation points to selected runtime evidence and its quote is an exact substring.
- **Answerability:** in-domain fixture questions complete; deliberately unsupported inputs refuse.

Metrics without valid labels must be reported as `NOT AVAILABLE — NO VALID GROUND TRUTH`; the evaluator does not synthesize them.

## Adversarial and failure coverage

`data/evaluation/adversarial_cases.json` holds 24 deterministic query cases covering supported, off-topic, no-evidence, direct injection, indirect injection and unsafe requests. The backend suite additionally covers empty/oversized input, malformed/empty audio, unavailable and transient STT, provider timeout, malformed provider/generator envelopes, vector failure with BM25 recovery, low evidence, unsupported claims, grounding failure, cache tracing, traversal rejection, embedding/index mismatch, Unicode grounding and rate limiting.

## Run

```bash
python scripts/evaluate.py --queries 120
```

Each run writes a unique immutable file, updates `reports/evaluation.json`, and appends a summary to `reports/evaluations/index.json`.

## Limitations

- Surface variants are correlated and not independent human-authored questions.
- The fixture is small and not evidence of official-subset or full-corpus quality.
- Hashing embeddings and extractive generation are development fallbacks.
- Relevance is passage-level; there is no human answer-preference, WER, full multilingual quality, or production LLM score.
- Recall@1 and nDCG@5 are reported as measured rather than optimized with ground-truth leakage.
