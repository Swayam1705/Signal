import { useEffect, useState } from 'react'
import { getPipeline } from '../services/api'
import type { PipelineStage } from '../types/api'

export function PipelinePage() {
  const [stages, setStages] = useState<PipelineStage[]>([])
  const [active, setActive] = useState(0)
  useEffect(() => { const controller = new AbortController(); getPipeline(controller.signal).then(setStages).catch(() => setStages([])); return () => controller.abort() }, [])
  const selected = stages[active]
  return <main className="editorial-page pipeline-page">
    <header className="page-hero green-hero"><span className="number-tag">SYSTEM / 10 STAGES</span><h1>THE SIGNAL<br /><em>PIPELINE.</em></h1><p>Every stage is a real operation.<br />Every duration is measured.</p><div className="hero-arrow">↓</div></header>
    <section className="pipeline-layout">
      <div className="pipeline-stack">
        {stages.map((stage, index) => <button className={index === active ? 'active' : ''} onClick={() => setActive(index)} key={stage.id}><span>{stage.id}</span><strong>{stage.name}</strong><i>↘</i></button>)}
        {!stages.length && <div className="empty-state"><b>PIPELINE API UNAVAILABLE</b><span>Start the backend to inspect implementation stages.</span></div>}
      </div>
      {selected && <article className="stage-detail">
        <div className="stage-number">{selected.id}</div><span className="eyebrow">PIPELINE STAGE</span><h2>{selected.name}</h2>
        <dl><div><dt>WHAT</dt><dd>{selected.what}</dd></div><div><dt>WHY</dt><dd>{selected.why}</dd></div><div><dt>IMPLEMENTATION</dt><dd>{selected.implementation}</dd></div></dl>
        <div className="failure-box"><span>FAILURE MODES</span>{selected.failure_modes.map(mode => <b key={mode}>× {mode}</b>)}</div>
        <p className="latency-note">LATENCY // Runtime values appear only after a query. No values are simulated on this page.</p>
      </article>}
    </section>
    <section className="chunking-feature">
      <div><span className="number-tag">ADAPTIVE CHUNKING</span><h2>ONE CORPUS.<br /><em>FIVE STRATEGIES.</em></h2></div>
      <div className="strategy-grid"><article><b>01</b><strong>SEMANTIC</strong><p>Boundary-aware lexical cohesion preserves concepts.</p></article><article><b>02</b><strong>SENTENCE</strong><p>Complete sentences under a configurable budget.</p></article><article><b>03</b><strong>SLIDING WINDOW</strong><p>Controlled overlap for long, dense passages.</p></article><article><b>04</b><strong>METADATA AWARE</strong><p>Language and document context travel with evidence.</p></article><article className="strategy-active"><b>05 / DEFAULT</b><strong>ADAPTIVE HYBRID</strong><p>Selects the strategy from structure, length, and density.</p></article></div>
    </section>
  </main>
}
