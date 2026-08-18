import { useEffect, useState } from 'react'
import { getMetrics } from '../services/api'
import type { Health } from '../types/api'

const nodes = [
  { id: '01', name: 'VOICE / TEXT', tech: 'MediaRecorder or typed request', purpose: 'Two inputs converge before query intelligence.', input: 'Audio upload or validated query text.', output: 'Transcript or text QueryRequest.', stage: 'stt', failure: 'Microphone denied, malformed audio, STT unavailable.' },
  { id: '02', name: 'VALIDATION', tech: 'Pydantic + audio signatures', purpose: 'Reject malformed, empty, oversized, or unsupported requests.', input: 'Untrusted browser request.', output: 'Typed query/audio payload.', stage: null, failure: '422/413/415 typed safe error.' },
  { id: '03', name: 'SAFETY', tech: 'GuardrailEngine', purpose: 'Stop unsafe and injection requests before retrieval.', input: 'Normalized query analysis.', output: 'Pass or policy refusal.', stage: 'query_analysis', failure: 'Safe structured refusal.' },
  { id: '04', name: 'QUERY INTELLIGENCE', tech: 'Normalize / classify / plan', purpose: 'Select language, intent, safety status, and retrieval mode.', input: 'Typed query.', output: 'QueryAnalysis.', stage: 'query_analysis', failure: 'Invalid input is rejected.' },
  { id: '05', name: 'RETRIEVAL PLANNER', tech: 'Adaptive weights + top-k', purpose: 'Make query type materially affect candidate search.', input: 'QueryAnalysis and optional metadata filter.', output: 'Mode, weights and candidate bounds.', stage: 'query_analysis', failure: 'Falls back to declared balanced bounds.' },
  { id: '06', name: 'EMBEDDING', tech: 'Replaceable provider', purpose: 'Encode with the same provider and dimension used at ingestion.', input: 'Normalized query.', output: 'Normalized query vector.', stage: 'retrieval', failure: 'Retrieval error triggers lexical recovery.' },
  { id: '07', name: 'QDRANT + BM25', tech: 'Cosine vector + lexical index', purpose: 'Union semantic and exact-term evidence candidates.', input: 'Vector, terms, filters and top-k.', output: 'Scored candidate pools.', stage: 'retrieval', failure: 'Qdrant failure → BM25-only fallback.' },
  { id: '08', name: 'HYBRID SCORE', tech: 'Semantic + lexical + metadata', purpose: 'Combine inspectable signals with declared weights.', input: 'Vector, BM25 and legitimate query-derived metadata scores.', output: 'Hybrid-ranked candidates.', stage: 'retrieval', failure: 'No/low evidence → refusal.' },
  { id: '09', name: 'RERANK', tech: 'Deterministic relevance features', purpose: 'Improve top-context precision without a second network model.', input: 'Candidates and query terms.', output: 'Rerank score and new order.', stage: 'rerank', failure: 'Empty pool proceeds to evidence refusal.' },
  { id: '10', name: 'CONTEXT', tech: 'Dedupe / token budget', purpose: 'Send only ordered, bounded, attributed evidence.', input: 'Top reranked candidates.', output: 'Delimited evidence context.', stage: 'context', failure: 'Budget exhaustion truncates the final block.' },
  { id: '11', name: 'STRUCTURED LLM', tech: 'JSON schema provider', purpose: 'Generate only after evidence is available.', input: 'Question, schema and untrusted evidence data.', output: 'GeneratedAnswer.', stage: 'generation', failure: 'Timeout/malformed output → bounded retry/refusal.' },
  { id: '12', name: 'GROUNDING', tech: 'Claims + citations + quotes', purpose: 'Prevent unsupported claims from reaching the user.', input: 'Answer and selected evidence.', output: 'Per-claim support and pass/fail.', stage: 'grounding', failure: 'Strict regeneration → safe refusal.' },
  { id: '13', name: 'ANSWER + TRACE', tech: 'Pydantic response contract', purpose: 'Expose evidence, tools, recovery, and real timings.', input: 'Validated answer or refusal.', output: 'QueryResponse and inspectable trace.', stage: 'total', failure: 'Typed pipeline error; no leaked stack trace.' },
] as const

export function ArchitecturePage({ health }: { health: Health | null }) {
  const [active, setActive] = useState(0)
  const [metrics, setMetrics] = useState<{ stage_means_ms: Record<string, number>; sample_count: number } | null>(null)
  useEffect(() => { const controller = new AbortController(); getMetrics(controller.signal).then(setMetrics).catch(() => setMetrics(null)); return () => controller.abort() }, [])
  const selected = nodes[active]
  const measured = selected.stage && metrics?.sample_count ? metrics.stage_means_ms[selected.stage] : undefined
  return <main className="editorial-page architecture-page">
    <header className="page-hero black-hero"><span className="number-tag">SYSTEM ARCHITECTURE / V1.0</span><h1>UNDER<br /><em>THE HOOD.</em></h1><p>Replaceable providers.<br />Inspectable decisions.<br />Bounded failure.</p></header>
    <section className="architecture-board">
      <div className="board-head"><span>CLICKABLE END-TO-END DATA FLOW</span><b>{health?.indexed_documents ?? '—'} DOCS / {health?.indexed_chunks ?? '—'} CHUNKS</b></div>
      <div className="architecture-flow">{nodes.map((node, index) => <div className="architecture-node" key={node.id}><button className={active === index ? 'active' : ''} onClick={() => setActive(index)}><span>{node.id}</span><strong>{node.name}</strong><small>{node.tech}</small></button>{index < nodes.length - 1 && <i>↓</i>}</div>)}</div>
      <article className="architecture-inspector"><span>{selected.id} / SELECTED STAGE</span><h2>{selected.name}</h2><div><b>PURPOSE</b><p>{selected.purpose}</p><b>INPUT</b><p>{selected.input}</p><b>OUTPUT</b><p>{selected.output}</p><b>LATENCY</b><p>{measured == null ? selected.stage ? 'NOT MEASURED IN THIS API PROCESS' : 'NOT SEPARATELY INSTRUMENTED' : `${measured.toFixed(2)}ms PROCESS MEAN · ${metrics?.sample_count} REQUEST(S)`}</p><b>FAILURE MODE</b><p>{selected.failure}</p></div></article>
      <div className="architecture-legend"><span><i className="green" /> ONLINE QUERY PATH</span><span><i className="yellow" /> OFFLINE INDEX IS PRECOMPUTED</span><span><i className="pink" /> POLICY BOUNDARY</span></div>
    </section>
    <section className="provider-section">
      <div><span className="number-tag">PROVIDER ABSTRACTIONS</span><h2>SWAP THE PARTS.<br /><em>KEEP THE CONTRACT.</em></h2></div>
      <div className="provider-list"><code>SpeechToTextProvider</code><code>EmbeddingProvider</code><code>VectorStore</code><code>Reranker</code><code>LLMProvider</code><code>GroundingValidator</code></div>
    </section>
    <section className="failure-architecture"><span>ERROR RECOVERY</span><div><article><b>01</b><strong>QDRANT FAILURE</strong><p>Record the failed tool, then use BM25 fallback.</p></article><article><b>02</b><strong>MALFORMED OUTPUT</strong><p>Strict-schema retry, then safe refusal.</p></article><article><b>03</b><strong>GROUNDING FAILURE</strong><p>Evidence-only regeneration, then refuse.</p></article><article><b>04</b><strong>PROVIDER DOWN</strong><p>Typed safe error with no leaked credentials.</p></article></div></section>
  </main>
}
