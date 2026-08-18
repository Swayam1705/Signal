import { useState } from 'react'
import type { QueryResponse } from '../types/api'
import { LatencyWaterfall } from './LatencyWaterfall'

function download(response: QueryResponse) {
  const blob = new Blob([JSON.stringify(response, null, 2)], { type: 'application/json' })
  const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(blob); anchor.download = `signal-${response.request_id}.json`; anchor.click(); URL.revokeObjectURL(anchor.href)
}

export function ResultPanel({ result }: { result: QueryResponse }) {
  const [copied, setCopied] = useState('')
  const copy = async (label: string, text: string) => { await navigator.clipboard.writeText(text); setCopied(label); window.setTimeout(() => setCopied(''), 1400) }
  const sourceText = result.evidence.map(item => `${item.chunk.document_id} / ${item.chunk.chunk_id}\n${item.chunk.text}`).join('\n\n')
  const share = async () => {
    const text = `${result.answer.answer}\n\nSources:\n${sourceText}`
    if (navigator.share) await navigator.share({ title: 'SIGNAL verified answer', text })
    else await copy('SHARE', text)
  }
  const top = result.evidence[0]
  const reveal = (target: 'evidence' | 'latency' | 'inspect') => {
    const element = document.getElementById(`${target}-${result.request_id}`)
    if (element instanceof HTMLDetailsElement) element.open = true
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  return <article className={`result-panel ${result.status === 'refused' ? 'result-refused' : ''}`} aria-live="polite">
    <div className="result-kicker"><span>{result.status === 'refused' ? 'GROUNDING STATUS: REJECTED' : 'ANSWER // EVIDENCE VERIFIED'}</span><code>{result.request_id}</code></div>
    <div className="answer-grid">
      <div>
        <h2>{result.status === 'refused' ? 'NOT ENOUGH SIGNAL' : 'THE ANSWER.'}</h2>
        <p className="answer-copy">{result.answer.answer}</p>
        {result.answer.warnings.map(warning => <div className="warning-note" key={warning}>↳ {warning}</div>)}
      </div>
      <div className="answer-stats">
        <div><span>GROUNDING</span><strong>{result.trace.grounding.passed && !result.answer.refusal ? '● VERIFIED' : '○ REJECTED'}</strong></div>
        <div><span>CONFIDENCE</span><strong>{result.answer.confidence.toFixed(2)}</strong></div>
        <div><span>SOURCES</span><strong>{String(result.evidence.length).padStart(2, '0')}</strong></div>
        <div><span>LATENCY</span><strong>{result.total_ms.toFixed(1)}ms</strong></div>
      </div>
    </div>
    <div className="result-actions">
      <button onClick={() => copy('ANSWER', result.answer.answer)}>{copied === 'ANSWER' ? 'COPIED ✓' : 'COPY ANSWER'}</button>
      <button onClick={() => copy('SOURCES', sourceText)} disabled={!sourceText}>{copied === 'SOURCES' ? 'COPIED ✓' : 'COPY SOURCES'}</button>
      <button onClick={share}>{copied === 'SHARE' ? 'COPIED ✓' : 'SHARE RESULT'}</button>
      <button onClick={() => download(result)}>DOWNLOAD REPORT ↓</button>
    </div>
    <div className="show-buttons" aria-label="Runtime inspection shortcuts">
      <button onClick={() => reveal('evidence')}>SHOW RETRIEVAL</button><button onClick={() => reveal('evidence')}>SHOW CHUNKS</button>
      <button onClick={() => reveal('inspect')}>SHOW CONTEXT</button><button onClick={() => reveal('latency')}>SHOW LATENCY</button>
      <button onClick={() => reveal('inspect')}>SHOW GUARDRAILS</button><button onClick={() => reveal('inspect')}>SHOW GROUNDING</button>
    </div>

    {result.evidence.length > 0 && <section className="evidence-section" id={`evidence-${result.request_id}`}>
      <div className="section-heading"><span>EVIDENCE</span><b>{result.evidence.length} SELECTED / {result.trace.candidate_count} RETRIEVED</b></div>
      <div className="evidence-list">
        {result.evidence.map((candidate, index) => {
          const citation = result.answer.citations.find(item => item.chunk_id === candidate.chunk.chunk_id)
          return <details className="evidence-card" key={candidate.chunk.chunk_id} open={index === 0}>
            <summary><span className="evidence-index">0{index + 1}</span><span><b>{candidate.chunk.document_id}</b><small>{candidate.chunk.chunk_id} · {candidate.chunk.strategy} · CHUNK {candidate.chunk.chunk_index}</small></span><strong>{candidate.rerank_score.toFixed(3)}</strong></summary>
            <p>{candidate.chunk.text}</p><code className="evidence-source">SOURCE // {candidate.chunk.source}</code>
            <div className="score-grid"><span>VECTOR <b>{candidate.semantic_score.toFixed(3)}</b></span><span>BM25 <b>{candidate.lexical_score.toFixed(3)}</b></span><span>METADATA <b>{candidate.metadata_score.toFixed(3)}</b></span><span>HYBRID <b>{candidate.hybrid_score.toFixed(3)}</b></span><span>RERANK <b>{candidate.rerank_score.toFixed(3)}</b></span><span>RANK <b>{candidate.rank_before || '—'} → {candidate.rank_after || '—'}</b></span></div>
            {citation && <blockquote className="supporting-quote"><span>EXACT CITED SUPPORT</span>“{citation.quote}”</blockquote>}
          </details>
        })}
      </div>
    </section>}

    <div id={`latency-${result.request_id}`}><LatencyWaterfall timings={result.telemetry} /></div>

    <details className="inspect-block" id={`inspect-${result.request_id}`}>
      <summary>WHY THIS ANSWER? <span>OPEN COMPLETE TRACE +</span></summary>
      <div className="inspect-grid">
        <div><label>INPUT MODE</label><p>{result.trace.input_mode}</p></div>
        <div><label>NORMALIZED QUERY</label><p>{result.trace.analysis.normalized_query}</p></div>
        <div><label>QUERY TYPE / LANGUAGE</label><p>{result.trace.analysis.intent} · {result.trace.analysis.language}</p></div>
        <div><label>RETRIEVAL MODE</label><p>{result.trace.retrieval_mode}</p></div>
        <div><label>CHUNK STRATEGY</label><p>{result.trace.selected_chunk_strategy}</p></div>
        <div><label>GENERATION / RETRIES</label><p>{result.trace.generation_attempts} attempt(s) · {result.trace.retry_count} retries</p></div>
        <div><label>GUARDRAIL</label><p>{result.trace.guardrail.status} · {result.trace.guardrail.reason}</p></div>
      </div>
      <label>RETRIEVAL PLAN</label><pre>{JSON.stringify(result.trace.retrieval_plan, null, 2)}</pre>
      <label>STRUCTURED TOOL EXECUTION</label><pre>{JSON.stringify(result.trace.tool_calls, null, 2)}</pre>
      <label>RECOVERY ACTIONS</label><pre>{result.trace.recovery_actions.length ? result.trace.recovery_actions.join('\n') : 'No fallback or retry was required.'}</pre>
      <label>CITATIONS</label><pre>{JSON.stringify(result.answer.citations, null, 2)}</pre>
      <label>CONTEXT SENT TO MODEL</label><pre>{result.trace.context || 'No context was sent because the request was refused before generation.'}</pre>
      <label>GROUNDING RESULT</label><pre>{JSON.stringify(result.trace.grounding, null, 2)}</pre>
      {top && <label className="trace-foot">TOP EVIDENCE // {top.chunk.embedding_id}</label>}
    </details>
  </article>
}
