import { useCallback, useEffect, useState } from 'react'
import { Footer, Header, Marquee, type Page } from './components/Shell'
import { getHealth } from './services/api'
import type { Health } from './types/api'
import { HomePage } from './pages/HomePage'
import { PipelinePage } from './pages/PipelinePage'
import { PerformancePage } from './pages/PerformancePage'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { JudgePage } from './pages/JudgePage'

const pages = new Set<Page>(['home', 'pipeline', 'performance', 'architecture', 'judge'])
function hashPage(): Page { const value = location.hash.slice(1) as Page; return pages.has(value) ? value : 'home' }

export default function App() {
  const [page, setPageState] = useState<Page>(hashPage)
  const [health, setHealth] = useState<Health | null>(null)
  const [demoQuery, setDemoQuery] = useState<string | null>(null)
  const setPage = useCallback((next: Page) => { location.hash = next; setPageState(next); window.scrollTo({ top: 0, behavior: 'smooth' }) }, [])
  useEffect(() => { const listener = () => setPageState(hashPage()); window.addEventListener('hashchange', listener); return () => window.removeEventListener('hashchange', listener) }, [])
  useEffect(() => {
    let active = true
    const refresh = () => getHealth().then(value => { if (active) setHealth(value) }).catch(() => { if (active) setHealth(null) })
    refresh(); const interval = window.setInterval(refresh, 30_000)
    return () => { active = false; window.clearInterval(interval) }
  }, [])
  return <div className="app-shell">
    <Header page={page} setPage={setPage} health={health} />
    {page === 'home' && <HomePage health={health} presetQuery={demoQuery} />}
    {page === 'pipeline' && <PipelinePage />}
    {page === 'performance' && <PerformancePage />}
    {page === 'architecture' && <ArchitecturePage health={health} />}
    {page === 'judge' && <JudgePage health={health} onSelectDemo={query => { setDemoQuery(query); setPage('home') }} />}
    <Marquee /><Footer />
  </div>
}
