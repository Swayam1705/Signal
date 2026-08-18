import { useEffect, useState } from 'react'
import { getBenchmark, getBenchmarkProfiles } from '../services/api'
import type { Benchmark, BenchmarkProfile } from '../types/api'

const ms = (value?: number) => value == null ? '—' : `${value.toFixed(1)}ms`
const pct = (value?: number) => value == null ? '—' : `${(value * 100).toFixed(1)}%`

export function PerformancePage() {
  const [data, setData] = useState<Benchmark | null>(null)
  const [profiles, setProfiles] = useState<BenchmarkProfile[]>([])
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getBenchmark(controller.signal), getBenchmarkProfiles(controller.signal)])
      .then(([benchmark, registry]) => { setData(benchmark); setProfiles(registry) })
      .catch(() => setData({ available: false, reason: 'Benchmark API unavailable' }))
    return () => controller.abort()
  }, [])
  return <main className="editorial-page performance-page">
    <header className="page-hero yellow-hero"><span className="number-tag">OBSERVABILITY / MEASURED</span><h1>SPEED IS<br /><em>A FEATURE.</em></h1><p>No lucky query. No stopped clock.<br />Complete text RAG, measured.</p></header>
    {!data ? <div className="metric-loading">READING MEASUREMENTS…</div> : !data.available ? <section className="no-benchmark"><span>NO VERIFIED BENCHMARK AVAILABLE</span><h2>METRICS<br />AREN'T DECORATION.</h2><p>{data.reason}</p><code>python scripts/benchmark.py --profile auto --queries 100</code></section> : <>
      <section className="profile-registry" aria-label="Separated benchmark profiles">
        <div className="section-heading"><span>PROFILE REGISTRY</span><b>INCOMPARABLE SCOPES STAY SEPARATE</b></div>
        <div>{profiles.map(profile => <article className={profile.profile === data.profile ? 'active' : ''} key={profile.profile}><span>{profile.label}</span><strong>{profile.available ? `${profile.measurement_count} VERIFIED RUN${profile.measurement_count === 1 ? '' : 'S'}` : 'NOT MEASURED'}</strong><p>{profile.scope}</p>{profile.latest && <code>P50 {ms(profile.latest.p50_ms)} · P100 {ms(profile.latest.p100_ms)}</code>}</article>)}</div>
      </section>
      <section className="benchmark-profile"><span>ACTIVE LATEST ARTIFACT</span><strong>{data.profile?.replaceAll('-', ' ').toUpperCase()}</strong><code>{data.query_count} QUERIES · {data.warmup_count} WARMUPS · {data.indexed_documents} DOCUMENTS · {data.indexed_chunks} CHUNKS</code></section>
      <section className="metric-strip four-metrics">
        <article><span>P50</span><strong>{ms(data.p50_ms)}</strong><small>MEDIAN</small></article>
        <article className="metric-focus"><span>P70</span><strong>{ms(data.p70_ms)}</strong><small>70TH PERCENTILE</small></article>
        <article><span>P95</span><strong>{ms(data.p95_ms)}</strong><small>TAIL LATENCY</small></article>
        <article><span>P100</span><strong>{ms(data.p100_ms)}</strong><small>MAXIMUM · NOT ESTIMATED</small></article>
      </section>
      <section className="target-band"><span>DECLARED {data.profile === 'full-voice' ? 'FULL VOICE' : 'TEXT RAG'} TARGET // &lt;200MS</span><div><i style={{ width: `${Math.min(100, (data.p100_ms ?? 0) / 2)}%` }} /></div><b>{(data.p100_ms ?? Infinity) < 200 ? 'TARGET MET FOR THIS PROFILE' : 'TARGET NOT MET'}</b></section>
      <section className="metrics-grid">
        <article><div className="section-heading"><span>RELIABILITY</span><b>{data.query_count} QUERIES</b></div><dl><div><dt>SUCCESS RATE</dt><dd>{pct(1 - (data.failure_rate ?? 0))}</dd></div><div><dt>FAILURE RATE</dt><dd>{pct(data.failure_rate)}</dd></div><div><dt>RETRY RATE</dt><dd>{pct(data.retry_rate)}</dd></div></dl></article>
        <article><div className="section-heading"><span>GROUNDING</span><b>EVIDENCE FIRST</b></div><dl><div><dt>PASS RATE</dt><dd>{pct(data.grounding_pass_rate)}</dd></div><div><dt>REFUSAL RATE</dt><dd>{pct(data.refusal_rate)}</dd></div><div><dt>AVG SCORE</dt><dd>{data.avg_score?.toFixed(3)}</dd></div></dl></article>
        <article><div className="section-heading"><span>QUERY PATH</span><b>STAGE MEANS</b></div><dl><div><dt>RETRIEVAL</dt><dd>{ms(data.avg_retrieval_ms)}</dd></div><div><dt>GENERATION</dt><dd>{ms(data.avg_generation_ms)}</dd></div><div><dt>FULL MEAN</dt><dd>{ms(data.mean_ms)}</dd></div></dl></article>
      </section>
      <section className="benchmark-transparency">
        <div><span className="number-tag">BENCHMARK TRANSPARENCY</span><h2>MEASURE<br /><em>THE WHOLE PATH.</em></h2><p>{data.latency_scope}</p><p><strong>CACHE POLICY //</strong> {data.cache_policy}</p></div>
        <dl>{Object.entries(data.environment ?? {}).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}</dl>
        <footer><span>BENCHMARK ID // {data.benchmark_id}</span><span>{data.timestamp && new Date(data.timestamp).toLocaleString()}</span></footer>
      </section>
    </>}
  </main>
}
