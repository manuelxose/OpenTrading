export type Json = null | boolean | number | string | Json[] | { [key: string]: Json }

export interface Envelope<T> { schemaVersion: string; data: T }
export interface Collection { resource: string; items: Record<string, Json>[]; total: number; limit: number; availability?: string }
export interface Overview {
  asOf: string
  operatingMode: string
  account: { nav: string | null; equity: string | null; currency: string | null }
  performance: { pnl: string | null; realizedPnl?: string | null; drawdownPct: number | null }
  exposure: { gross: string | null; net: string | null; asOf?: string | null; status?: string }
  riskStatus: string
  mt4Status: string
  dataFreshness: { status: string; latestAt: string | null; ageSeconds?: number | null }
}
export interface RiskView {
  configuredLimits: { key: string; value: Json; source: string }[]
  currentUtilization: Record<string, Json>[]
  breaches: Record<string, Json>[]
  recentRejections: Record<string, Json>[]
  killSwitch: { status: string; scopes: string[]; note: string }
  safeMode: { active: boolean; reasonCodes: string[]; since?: string | null; note?: string | null }
}
export interface SystemView { status: string; operatingMode: string; dependencies: { name: string; status: string; latency_ms: number; detail?: string }[] }
export interface TradeDetail { tradeId: string; traceId: string; stages: { key: string; status: string; payload: Json }[] }
