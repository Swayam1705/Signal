import type { Timing } from '../types/api'

const labels: Record<string, string> = { stt: 'STT', query_analysis: 'QUERY', retrieval: 'RETRIEVAL', rerank: 'RERANK', context: 'CONTEXT', generation: 'GENERATION', grounding: 'GROUNDING', total: 'TOTAL' }

export function LatencyWaterfall({ timings }: { timings: Timing[] }) {
  const stages = timings.filter(item => item.stage !== 'total')
  const ceiling = Math.max(1, ...stages.map(item => item.duration_ms))
  const total = [...timings].reverse().find((item: Timing) => item.stage === 'total')?.duration_ms ?? stages.reduce((sum, item) => sum + item.duration_ms, 0)
  return <section className="waterfall" aria-label="Measured latency waterfall">
    <div className="section-heading"><span>LATENCY WATERFALL</span><b>REAL TIMERS</b></div>
    {stages.map((timing, index) => <div className="waterfall-row" key={`${timing.stage}-${index}`}>
      <code>{labels[timing.stage] ?? timing.stage.toUpperCase()}</code>
      <div className="waterfall-track"><i style={{ width: `${Math.max(2, timing.duration_ms / ceiling * 100)}%` }} className={timing.status === 'error' ? 'bar-error' : ''} /></div>
      <strong>{timing.duration_ms.toFixed(1)}<small>ms</small></strong>
    </div>)}
    <div className="waterfall-total"><span>TOTAL</span><strong>{total.toFixed(1)}ms</strong></div>
  </section>
}
