import { useCallback, useEffect, useRef, useState, type ComponentType } from 'react'
import {
  Activity, BarChart3, BookOpen, Bot, BrainCircuit, BriefcaseBusiness, ChevronRight,
  CircleGauge, Database, Menu, Radar, ReceiptText, ScrollText, ShieldCheck, X,
} from 'lucide-react'
import { get } from './api'
import type { Collection, Json, Overview, RiskView, SystemView, TradeDetail } from './types'

type Section = 'overview' | 'research' | 'signals' | 'risk' | 'orders' | 'trades' | 'positions' | 'backtests' | 'memory' | 'agents' | 'system'
type Icon = ComponentType<{ size?: number; 'aria-hidden'?: boolean }>
const sections: { id: Section; label: string; icon: Icon }[] = [
  { id: 'overview', label: 'Overview', icon: CircleGauge }, { id: 'research', label: 'Research', icon: BookOpen },
  { id: 'signals', label: 'Signals', icon: Radar }, { id: 'risk', label: 'Risk', icon: ShieldCheck },
  { id: 'orders', label: 'Orders', icon: ReceiptText }, { id: 'trades', label: 'Trades', icon: ScrollText },
  { id: 'positions', label: 'Positions', icon: BriefcaseBusiness }, { id: 'backtests', label: 'Backtests', icon: BarChart3 },
  { id: 'memory', label: 'Memory', icon: BrainCircuit }, { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'system', label: 'System', icon: Database },
]

function useApi<T>(path: string) {
  const [state, setState] = useState<{ path?: string; data?: T; error?: string }>({})
  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const refresh = () => get<T>(path, controller.signal).then(data => {
      if (!active) return
      setState({ path, data })
      window.dispatchEvent(new CustomEvent('command-center-health', { detail: { ok: true, at: new Date().toISOString() } }))
    }).catch(error => {
      if (!active || (error instanceof DOMException && error.name === 'AbortError')) return
      setState(previous => ({ path, data: previous.path === path ? previous.data : undefined, error: error instanceof Error ? error.message : 'Unknown API error.' }))
      window.dispatchEvent(new CustomEvent('command-center-health', { detail: { ok: false, at: new Date().toISOString() } }))
    })
    void refresh()
    const timer = window.setInterval(refresh, 15_000)
    return () => { active = false; window.clearInterval(timer); controller.abort() }
  }, [path])
  return { ...state, loading: state.path !== path }
}

const words = (value: string) => value.replace(/([a-z])([A-Z])/g, '$1 $2').replaceAll('_', ' ')
const money = (value: string | null, currency: string | null) => value == null ? 'Unavailable' : new Intl.NumberFormat('en', { style: 'currency', currency: currency ?? 'USD', maximumFractionDigits: 0 }).format(Number(value))
const stamp = (value?: string | null) => value ? new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Not recorded'

function Status({ value }: { value: string }) {
  const normalized = value.toLowerCase()
  const tone = /healthy|normal|fresh|connected|ok|available|filled|reviewed/.test(normalized) ? 'good' : /unknown|not_|pending|research/.test(normalized) ? 'neutral' : 'bad'
  return <span className={`status ${tone}`}><span className="status-dot" />{words(value)}</span>
}

function Frame({ loading, error, children }: { loading: boolean; error?: string; children: React.ReactNode }) {
  if (loading) return <div className="state" role="status"><Activity className="spin" />Retrieving live platform state…</div>
  if (error && !children) return <div className="state error" role="alert"><strong>Data unavailable</strong><span>{error} Check API and dependency health in System.</span></div>
  return <>{error && <div className="stale-banner" role="status">Refresh failed. Showing the last successful snapshot.</div>}{children}</>
}

function OverviewPage() {
  const { data, loading, error } = useApi<Overview>('/overview')
  return <Frame loading={loading} error={error}>{data && <>
    <header className="page-head"><div><h1>Operational overview</h1><p>Capital, exposure, and platform readiness at {stamp(data.asOf)}.</p></div><Status value={data.riskStatus} /></header>
    <section className="metrics" aria-label="Portfolio metrics">
      <Metric label="NAV" value={money(data.account.nav, data.account.currency)} />
      <Metric label="Equity" value={money(data.account.equity, data.account.currency)} />
      <Metric label="Today's PnL" value={money(data.performance.pnl, data.account.currency)} tone={Number(data.performance.pnl) < 0 ? 'negative' : 'positive'} />
      <Metric label="Drawdown" value={data.performance.drawdownPct == null ? 'Unavailable' : `${data.performance.drawdownPct.toFixed(2)}%`} />
      <Metric label="Gross exposure" value={money(data.exposure.gross, data.account.currency)} />
      <Metric label="Net exposure" value={money(data.exposure.net, data.account.currency)} />
    </section>
    <section className="overview-grid">
      <div className="panel mode-panel"><h2>Operating posture</h2><div className="mode-value">{words(data.operatingMode)}</div><p>Mode is controlled by deterministic platform configuration.</p></div>
      <div className="panel"><h2>Control plane</h2><StatusRow label="Risk" value={data.riskStatus} /><StatusRow label="MT4" value={data.mt4Status} /><StatusRow label="Data" value={data.dataFreshness.status} note={stamp(data.dataFreshness.latestAt)} /></div>
    </section>
  </>}</Frame>
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) { return <div className="metric"><span>{label}</span><strong className={tone}>{value}</strong></div> }
function StatusRow({ label, value, note }: { label: string; value: string; note?: string }) { return <div className="status-row"><span>{label}</span><div><Status value={value} />{note && <small>{note}</small>}</div></div> }

function CollectionPage({ section, onTrade }: { section: Exclude<Section, 'overview' | 'risk' | 'system'>; onTrade: (id: string) => void }) {
  const { data, loading, error } = useApi<Collection>(`/${section}`)
  const title = sections.find(item => item.id === section)!.label
  return <Frame loading={loading} error={error}><header className="page-head"><div><h1>{title}</h1><p>Canonical {title.toLowerCase()} records from platform persistence.</p></div>{data && <span className="count">{data.total} records</span>}</header>
    {data && (data.items.length ? <div className="record-list">{data.items.map((item, index) => <button className="record" key={String(item.trade_id ?? item.order_intent_id ?? item.trace_id ?? index)} onClick={() => section === 'trades' && item.trade_id && onTrade(String(item.trade_id))} disabled={section !== 'trades'}><RecordSummary item={item} /><ChevronRight aria-hidden size={18} /></button>)}</div> : <Empty availability={data.availability} title={title} />)}
  </Frame>
}

function RecordSummary({ item }: { item: Record<string, Json> }) {
  const primary = item.instrument_id ?? item.strategy_id ?? item.name ?? item.trade_id ?? item.trace_id ?? 'Record'
  const state = item.state ?? item.status ?? item.verdict ?? item.direction
  const time = item.updated_at ?? item.created_at ?? item.started_at ?? item.closed_at
  return <div><strong>{String(primary)}</strong><span>{state ? words(String(state)) : 'Persisted record'} · {stamp(typeof time === 'string' ? time : null)}</span></div>
}

function Empty({ availability, title }: { availability?: string; title: string }) { return <div className="empty"><Activity size={28} aria-hidden /><h2>No {title.toLowerCase()} records</h2><p>{availability === 'NOT_IMPLEMENTED_BY_PLATFORM' ? 'This capability is not yet persisted by the platform. The API is available and reports that state explicitly.' : 'No canonical records currently match this view.'}</p></div> }

function RiskPage() {
  const { data, loading, error } = useApi<RiskView>('/risk')
  return <Frame loading={loading} error={error}>{data && <><header className="page-head"><div><h1>Risk controls</h1><p>Configured constraints, observed use, rejections, and capital protection.</p></div><Status value={data.safeMode.active ? 'SAFE_MODE_ACTIVE' : 'NORMAL'} /></header>
    <div className="risk-layout"><section className="panel"><h2>Configured limits</h2>{data.configuredLimits.map(limit => <div className="definition" key={limit.key}><span>{words(limit.key)}</span><strong>{String(limit.value)}</strong><small>{limit.source}</small></div>)}</section>
    <section className="panel"><h2>Current utilization</h2>{data.currentUtilization.length ? data.currentUtilization.map(item => <div className={`definition ${item.isBreached ? 'breached' : ''}`} key={String(item.key)}><span>{words(String(item.key))}</span><strong>{item.utilizationPct == null ? 'Unavailable' : `${Number(item.utilizationPct).toFixed(1)}%`}</strong><small>{item.isBreached ? 'BREACHED · ' : ''}{String(item.current ?? '—')} / {String(item.limit)}</small></div>) : <p className="muted">No persisted utilization snapshot is available.</p>}</section>
    <section className="panel kill"><h2>Capital protection</h2><StatusRow label="Reconciliation safe mode" value={data.safeMode.active ? 'ACTIVE' : 'CLEAR'} /><StatusRow label="Scoped kill switches" value={data.killSwitch.status} /><p>{data.killSwitch.note}</p></section>
    <section className="panel"><h2>Recent rejections</h2>{data.recentRejections.length ? data.recentRejections.map((r, i) => <JsonBlock key={i} value={r} />) : <p className="muted">No recent risk rejections.</p>}</section></div></>}</Frame>
}

function SystemPage() { const { data, loading, error } = useApi<SystemView>('/system'); return <Frame loading={loading} error={error}>{data && <><header className="page-head"><div><h1>System health</h1><p>Direct dependency probes. No terminal access required.</p></div><Status value={data.status} /></header><div className="dependency-list">{data.dependencies.map(dep => <div className="dependency" key={dep.name}><div><strong>{words(dep.name)}</strong><span>{dep.detail ?? 'Probe completed normally'}</span></div><div><Status value={dep.status} /><small>{dep.latency_ms} ms</small></div></div>)}</div></>}</Frame> }

export function TradeDrawer({ id, close }: { id: string; close: () => void }) {
  const { data, loading, error } = useApi<TradeDetail>(`/trades/${encodeURIComponent(id)}`)
  const dialog = useRef<HTMLElement>(null)
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const background = document.querySelectorAll<HTMLElement>('.sidebar,.workspace')
    background.forEach(element => { element.inert = true })
    const scrim = document.querySelector<HTMLButtonElement>('.scrim')
    if (scrim) scrim.tabIndex = -1
    dialog.current?.querySelector<HTMLElement>('button')?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
      if (event.key !== 'Tab' || !dialog.current) return
      const focusable = [...dialog.current.querySelectorAll<HTMLElement>('button,[href],[tabindex]:not([tabindex="-1"])')]
      if (!focusable.length) return
      const first = focusable[0], last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      background.forEach(element => { element.inert = false })
      previous?.focus()
    }
  }, [close])
  return <div className="drawer-shell"><button className="scrim" onClick={close} aria-label="Close trade detail" /><aside ref={dialog} tabIndex={-1} className="drawer" role="dialog" aria-modal="true" aria-labelledby="trade-title"><header><div><h2 id="trade-title">Trade reconstruction</h2><p>{id}</p></div><button className="icon-button" onClick={close} aria-label="Close trade detail"><X /></button></header><Frame loading={loading} error={error}>{data && <div className="timeline">{data.stages.map((stage, index) => <article key={stage.key} className="stage"><div className="stage-index">{index + 1}</div><div><div className="stage-head"><h3>{words(stage.key)}</h3><Status value={stage.status} /></div>{stage.payload ? <JsonBlock value={stage.payload} /> : <p className="muted">No canonical payload was recorded for this stage.</p>}</div></article>)}</div>}</Frame></aside></div>
}
function JsonBlock({ value }: { value: Json | Record<string, Json>[] }) { return <pre>{JSON.stringify(value, null, 2)}</pre> }

export function App() {
  const [active, setActive] = useState<Section>('overview'), [menu, setMenu] = useState(false), [trade, setTrade] = useState<string>()
  const [health, setHealth] = useState<{ ok: boolean; at?: string }>({ ok: false })
  useEffect(() => {
    const listener = (event: Event) => setHealth((event as CustomEvent<{ ok: boolean; at: string }>).detail)
    window.addEventListener('command-center-health', listener)
    return () => window.removeEventListener('command-center-health', listener)
  }, [])
  const closeTrade = useCallback(() => setTrade(undefined), [])
  const current = sections.find(section => section.id === active)!
  const select = (id: Section) => { setActive(id); setMenu(false) }
  let page: React.ReactNode
  if (active === 'overview') page = <OverviewPage />
  else if (active === 'risk') page = <RiskPage />
  else if (active === 'system') page = <SystemPage />
  else page = <CollectionPage section={active} onTrade={setTrade} />
  return <div className="app"><aside className={`sidebar ${menu ? 'open' : ''}`}><div className="brand"><div className="brand-mark"><Activity /></div><div><strong>OpenTrading</strong><span>Command Center</span></div></div><nav aria-label="Command Center sections">{sections.map(({ id, label, icon: NavIcon }) => <button key={id} className={active === id ? 'active' : ''} aria-current={active === id ? 'page' : undefined} onClick={() => select(id)}><NavIcon size={18} aria-hidden /><span>{label}</span></button>)}</nav><div className={`sidebar-foot ${health.ok ? '' : 'offline'}`}><span className="live-dot" />{health.ok ? `Live · ${new Date(health.at!).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'API unavailable'}</div></aside><div className="workspace"><header className="mobile-head"><button className="icon-button" onClick={() => setMenu(!menu)} aria-label="Toggle navigation">{menu ? <X /> : <Menu />}</button><strong>{current.label}</strong><div className="brand-mark small"><Activity /></div></header><main>{page}</main></div>{menu && <button className="mobile-scrim" onClick={() => setMenu(false)} aria-label="Close navigation" />}{trade && <TradeDrawer id={trade} close={closeTrade} />}</div>
}
