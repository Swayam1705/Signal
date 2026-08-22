import { FormEvent, useEffect, useRef, useState } from 'react'
import { useVoiceRecorder } from '../hooks/useVoiceRecorder'
import { streamTextQuery, streamVoiceQuery } from '../services/api'
import type { Health, QueryResponse, StageEvent, StreamMessage } from '../types/api'
import { ResultPanel } from '../components/ResultPanel'
import { SystemStatus } from '../components/SystemStatus'

const stageOrder = ['stt', 'query_analysis', 'retrieval', 'rerank', 'context', 'generation', 'grounding']
const stageNames: Record<string, string> = { stt: 'TRANSCRIBING', query_analysis: 'ANALYZING', retrieval: 'RETRIEVING', rerank: 'RERANKING', context: 'CONTEXT BUILDING', generation: 'GENERATING', grounding: 'VERIFYING' }

type HistoryItem = { timestamp: string; query: string; result: QueryResponse }

export function HomePage({ health, presetQuery }: { health: Health | null; presetQuery?: string | null }) {
  const recorder = useVoiceRecorder()
  const [mode, setMode] = useState<'voice' | 'text'>('voice')
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [events, setEvents] = useState<Record<string, StageEvent>>({})
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)
  const consoleRef = useRef<HTMLDivElement>(null)
  const [history, setHistory] = useState<HistoryItem[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('signal-history') ?? '[]') as HistoryItem[] } catch { return [] }
  })
  const suggested = health?.manifest?.demo_queries?.[0]

  useEffect(() => { sessionStorage.setItem('signal-history', JSON.stringify(history.slice(0, 8))) }, [history])
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => {
    if (!presetQuery) return
    setMode('text'); setQuery(presetQuery); setResult(null); setEvents({}); setError(null)
    window.setTimeout(() => consoleRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0)
  }, [presetQuery])

  const begin = () => {
    controller.current?.abort(); controller.current = new AbortController(); setResult(null); setEvents({}); setError(null); setRunning(true)
  }
  const onMessage = (message: StreamMessage) => {
    if (message.type === 'stage') {
      setEvents(previous => ({ ...previous, [message.data.stage]: message.data }))
      if (message.data.transcript) setQuery(message.data.transcript)
    } else if (message.type === 'result') {
      setResult(message.data); setRunning(false)
      const visibleQuery = message.data.trace.transcript || message.data.trace.analysis.normalized_query
      setHistory(previous => [{ timestamp: new Date().toISOString(), query: visibleQuery, result: message.data }, ...previous.filter(item => item.result.request_id !== message.data.request_id)].slice(0, 8))
    } else {
      setError(`${message.data.code}: ${message.data.message}`); setRunning(false)
    }
  }
  const submitText = async (event?: FormEvent) => {
    event?.preventDefault(); if (!query.trim() || running) return
    begin()
    try { await streamTextQuery(query.trim(), onMessage, controller.current?.signal) }
    catch (cause) { if ((cause as Error).name !== 'AbortError') { setError((cause as Error).message); setRunning(false) } }
  }
  const startVoice = async () => { setMode('voice'); setError(null); setResult(null); consoleRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); await recorder.start() }
  const stopAndSend = async () => {
    try {
      const blob = await recorder.stop()
      if (!blob.size) throw new Error('EMPTY_AUDIO')
      begin(); await streamVoiceQuery(blob, onMessage, controller.current?.signal)
    } catch (cause) { setError((cause as Error).message); setRunning(false) }
  }
  const cancel = () => { controller.current?.abort(); recorder.cancel(); setRunning(false); setEvents({}) }

  const activeStage = [...stageOrder].reverse().find(stage => events[stage]?.status === 'started')
  return <main>
    <section className="hero">
      <div className="hero-copy">
        <div className="hero-meta-top"><span>VOICE RETRIEVAL INTELLIGENCE</span><span>ENGINE // SIGNAL-RAG/1.0</span></div>
        <h1><span>ASK</span><span>THE</span><em>DATA.</em></h1>
        <p>Speak a question. Retrieve the evidence. Verify the answer.</p>
        <div className="hero-actions">
          <button className="primary-cta" onClick={startVoice}>START VOICE QUERY <b>↗</b></button>
          <button className="secondary-cta" onClick={() => { setMode('text'); consoleRef.current?.scrollIntoView({ behavior: 'smooth' }) }}>TYPE A QUERY <b>→</b></button>
        </div>
        <div className="flow-label"><i /> VOICE <b>→</b> RETRIEVE <b>→</b> VERIFY</div>
      </div>
      <div className="hero-visual" aria-label="Signal identity graphic">
        <div className="orbit orbit-one" /><div className="orbit orbit-two" />
        <div className="signal-core"><span>S</span><small>LESS NOISE.<br />MORE SIGNAL.</small></div>
        <code>GROUNDING / ACTIVE</code><code>{health?.runtime_profile === 'local-development' ? 'LOCAL TEXT TARGET' : 'TEXT RAG TARGET'} / &lt;200MS</code>
      </div>
      <div className="hero-specs">
        <div><span>DATASET</span><b>{health?.dataset_mode?.replaceAll('_', ' ').toUpperCase() ?? 'UNKNOWN'}</b></div><div><span>RETRIEVAL</span><b>HYBRID</b></div>
        <div><span>CHUNKING</span><b>ADAPTIVE</b></div><div><span>GROUNDING</span><b>ACTIVE</b></div>
        <div><span>VOICE</span><b>{health?.services.find(item => item.name === 'STT')?.status === 'online' ? 'READY' : 'NEEDS KEY'}</b></div>
      </div>
    </section>

    <section className="query-zone" ref={consoleRef}>
      <div className="query-main">
        <div className="zone-head"><div><span className="number-tag">01 / QUERY</span><h2>RETRIEVE<br /><em>THE SIGNAL.</em></h2></div><p>Your next answer starts with a question.<br />Voice and text use the exact same RAG path.</p></div>
        <div className="mode-switch" role="tablist"><button role="tab" aria-selected={mode === 'voice'} className={mode === 'voice' ? 'selected' : ''} onClick={() => setMode('voice')}>◉ VOICE INPUT</button><button role="tab" aria-selected={mode === 'text'} className={mode === 'text' ? 'selected' : ''} onClick={() => setMode('text')}>⌨ TEXT INPUT</button></div>

        <div className={`console ${running ? 'processing' : ''}`}>
          {mode === 'voice' ? <div className="voice-console">
            <div className="console-label"><span>MICROPHONE // {recorder.state.toUpperCase()}</span><span>{recorder.duration.toFixed(1)} SEC</span></div>
            <div className="real-waveform" aria-label={recorder.state === 'listening' ? 'Live microphone amplitude' : 'Microphone idle'}>
              {recorder.waveform.map((value, index) => <i key={index} style={{ transform: `scaleY(${recorder.state === 'listening' ? Math.max(.12, value) : .08})` }} />)}
            </div>
            <button className={`mic-button ${recorder.state}`} onClick={recorder.state === 'listening' ? stopAndSend : startVoice} disabled={running || recorder.state === 'requesting' || recorder.state === 'unsupported'} aria-label={recorder.state === 'listening' ? 'Stop and send recording' : 'Start recording'}>
              <span className="mic-icon">{recorder.state === 'listening' ? '■' : '●'}</span><b>{recorder.state === 'listening' ? 'STOP + SEND' : recorder.state === 'requesting' ? 'REQUESTING…' : 'PRESS TO SPEAK'}</b>
            </button>
            {(recorder.state === 'listening' || running) && <button className="cancel-button" onClick={cancel}>CANCEL</button>}
            {(recorder.error || recorder.state === 'unsupported') && <div className="console-error">SIGNAL LOST — {recorder.error || 'This browser does not support MediaRecorder. Switch to text mode.'}</div>}
          </div> : <form className="text-console" onSubmit={submitText}>
            <label htmlFor="signal-query">TYPE YOUR QUESTION</label>
            <textarea id="signal-query" value={query} onChange={event => setQuery(event.target.value)} maxLength={1000} placeholder="What do you want to verify?" disabled={running} />
            <div><span>{query.length} / 1000</span><button type="submit" disabled={!query.trim() || running}>{running ? 'RETRIEVING…' : 'RUN SIGNAL →'}</button></div>
          </form>}

          {(running || Object.keys(events).length > 0) && <div className="pipeline-live" aria-live="polite">
            <div className="console-label"><span>LIVE PIPELINE</span><span>{activeStage ? stageNames[activeStage] : result ? 'COMPLETE' : 'INITIALIZING'}</span></div>
            <div className="stage-track">{stageOrder.map((stage, index) => {
              const event = events[stage]
              const skipped = stage === 'stt' && mode === 'text'
              const state = event?.status === 'complete' ? 'done' : event?.status === 'started' ? 'active' : event?.status === 'error' ? 'failed' : skipped ? 'skipped' : ''
              return <div className={state} key={stage}><span>{String(index + 1).padStart(2, '0')}</span><b>{stageNames[stage]?.replace('ING', '')}</b><small>{skipped ? 'TEXT MODE' : event?.duration_ms != null ? `${event.duration_ms.toFixed(1)}ms` : state === 'active' ? 'RUNNING' : '—'}</small></div>
            })}</div>
          </div>}
          {error && <div className="signal-error"><div><span>×</span><strong>SIGNAL LOST</strong></div><p>{error}</p><button onClick={() => { setError(null); setMode('text') }}>SWITCH TO TEXT MODE →</button></div>}
        </div>

        {suggested && !result && <button className="recommended" onClick={() => { setMode('text'); setQuery(suggested) }}><span>RECOMMENDED DEMO QUERY</span><b>“{suggested}”</b><i>USE THIS QUERY →</i></button>}
        {result && <ResultPanel result={result} />}

        <section className="history-section">
          <div className="section-heading"><span>SESSION HISTORY</span><b>{history.length || 'NO'} QUERIES</b></div>
          {history.length ? history.map(item => <button className="history-row" key={item.result.request_id} onClick={() => { setResult(item.result); setQuery(item.query) }}><time>{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time><span>{item.query}</span><b className={item.result.status}>{item.result.status === 'complete' ? 'VERIFIED' : 'REFUSED'}</b><code>{item.result.total_ms.toFixed(1)}ms</code></button>) : <div className="empty-state"><b>NO QUERY YET</b><span>Your next answer starts with a question.</span></div>}
        </section>
      </div>
      <SystemStatus health={health} />
    </section>
  </main>
}
