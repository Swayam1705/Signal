import type { Health } from '../types/api'

export function SystemStatus({ health }: { health: Health | null }) {
  return <aside className="system-card" aria-label="Live system status">
    <div className="eyebrow">LIVE SYSTEM STATUS</div>
    <h3>{health ? health.status.toUpperCase() : 'CONNECTING'}</h3>
    <div className="service-list">
      {(health?.services ?? []).map(service => <div className="service-row" key={service.name} title={service.detail}>
        <span>{service.name}</span><span className={`service-led ${service.status}`} aria-label={service.status} />
      </div>)}
      {!health && Array.from({ length: 6 }, (_, index) => <div className="service-row skeleton" key={index}><span /><i /></div>)}
    </div>
    <div className="system-foot"><span>INDEX</span><strong>{health?.indexed_documents ?? '—'} DOCS / {health?.indexed_chunks ?? '—'} CHUNKS</strong></div>
    <div className="system-foot"><span>DATA</span><strong>{health?.dataset_mode?.replaceAll('_', ' ').toUpperCase() ?? 'UNKNOWN'}</strong></div>
    <div className="system-foot"><span>PROFILE</span><strong>{health?.runtime_profile?.replaceAll('-', ' ').toUpperCase() ?? '—'}</strong></div>
  </aside>
}
