// ── Data Truth Layer ──────────────────────────────────────
// Every piece of information displayed on the Executive Dashboard
// carries a DataTruthLevel that describes its provenance.
//
// REAL     – sourced from live runtime (SSE connected, freshness < 10s)
// DERIVED  – computed from REAL data via useMemo / inference
// FALLBACK – API fallback / mock fallback / reconnect mode
// DEMO     – explicitly generated for demonstration
// EMPTY    – no runtime data available, component in initial state

export type DataTruthLevel =
  | 'REAL'
  | 'DERIVED'
  | 'FALLBACK'
  | 'DEMO'
  | 'EMPTY'

export interface DataTruthMeta {
  level: DataTruthLevel
  source: string
  updatedAt?: number
  freshnessMs?: number
  stale?: boolean
  degraded?: boolean
}