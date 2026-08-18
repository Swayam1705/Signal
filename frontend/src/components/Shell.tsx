import type { Health } from '../types/api'

export type Page = 'home' | 'pipeline' | 'performance' | 'architecture' | 'judge'

export function Header({ page, setPage, health }: { page: Page; setPage: (page: Page) => void; health: Health | null }) {
  const navigation: [Page, string][] = [['home', 'QUERY'], ['pipeline', 'PIPELINE'], ['performance', 'PERFORMANCE'], ['architecture', 'UNDER THE HOOD'], ['judge', 'JUDGE MODE']]
  return <>
    <header className="topbar">
      <button className="wordmark" onClick={() => setPage('home')} aria-label="SIGNAL home"><span className="signal-mark">S</span>SIGNAL<span className="wordmark-slash">//</span></button>
      <nav aria-label="Primary navigation">
        {navigation.map(([id, label]) => <button key={id} className={page === id ? 'nav-active' : ''} aria-current={page === id ? 'page' : undefined} onClick={() => setPage(id)}>{label}</button>)}
      </nav>
      <div className={`online-pill ${health?.status ?? 'offline'}`} role="status"><span className="status-dot" />{health?.status === 'online' ? 'SIGNAL ONLINE' : health?.status === 'degraded' ? 'SIGNAL DEGRADED' : 'SIGNAL OFFLINE'}</div>
    </header>
    {health?.mode === 'development_fallback' && <div className="fallback-banner" role="status"><strong>{health.runtime_profile.replaceAll('-', ' ').toUpperCase()}</strong><span>LLM: {health.services.find(item => item.name === 'LLM')?.detail} · STT: {health.services.find(item => item.name === 'STT')?.detail}</span></div>}
  </>
}

export function Marquee() {
  return <div className="marquee" aria-hidden="true"><div>SPEAK → RETRIEVE → VERIFY → GROUND EVERY ANSWER → KNOW WHEN NOT TO ANSWER → SPEAK → RETRIEVE → VERIFY →</div></div>
}

export function Footer() {
  return <footer><div><strong>SIGNAL // RAG</strong><span>VOICE RETRIEVAL INTELLIGENCE</span></div><div><span>GOA / INDIA</span><strong>TASK 02 · 2026</strong></div><div className="footer-note">LESS NOISE.<br />MORE SIGNAL.</div></footer>
}
