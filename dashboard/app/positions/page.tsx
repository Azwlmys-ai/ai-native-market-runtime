'use client'

// Canonical 持仓视图（VNext 里程碑尾巴 #4）— 独立页面 /positions
// 自包含，不依赖主 dashboard 复杂 hooks；只读 /api/positions（better-sqlite3 直读 runtime.db）。
// 展示「去重后的 canonical 持仓」（按 canonical_market_id），而非膨胀的裸 paper_portfolio.json。

import { useCallback, useEffect, useState } from 'react'

const POLL_MS = 30_000

interface Position {
  position_uid: string
  canonical_market_id: string | null
  market_id: string | null
  market_name: string | null
  direction: string | null
  status: string | null
  entry_price: number | null
  exit_price: number | null
  position_size: number | null
  notional_usd: number | null
  realized_pnl: number | null
  close_reason: string | null
  dry_run: number | null
  synthetic: number | null
  opened_at: string | null
  closed_at: string | null
}
interface PositionsSummary {
  total: number
  open: number
  closed: number
  openNotional: number
  realizedPnl: number
  dryRun: number
}
interface PositionsApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  summary: PositionsSummary
  positions: Position[]
  note?: string
}

function useJson<T>(url: string): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData((await res.json()) as T)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'fetch failed')
    }
  }, [url])
  useEffect(() => {
    load()
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [load])
  return { data, error }
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="flex flex-col rounded-lg border border-slate-700/50 bg-slate-800/40 px-4 py-3">
      <span className="text-[11px] uppercase tracking-wide text-slate-400">{label}</span>
      <span className={`mt-1 text-2xl font-semibold ${tone ?? 'text-slate-100'}`}>{value}</span>
    </div>
  )
}

function fmtUsd(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}
function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(4)
}
function fmtDate(v: string | null | undefined): string {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? String(v).slice(0, 16) : d.toISOString().slice(0, 16).replace('T', ' ')
}

export default function PositionsPage() {
  const { data, error } = useJson<PositionsApiResponse>('/api/positions')
  const s = data?.summary
  const positions = data?.positions ?? []

  const realizedTone =
    (s?.realizedPnl ?? 0) > 0 ? 'text-emerald-300' : (s?.realizedPnl ?? 0) < 0 ? 'text-rose-300' : 'text-slate-100'

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-6 text-slate-200">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Canonical 持仓 · Paper Positions</h1>
        <p className="text-xs text-slate-400">
          按 canonical_market_id 去重的影子库视图（runtime.db），非膨胀裸 JSON。只读，30s 轮询。
          {data?.source === 'fallback' && (
            <span className="ml-2 rounded border border-amber-500/30 bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
              fallback{data.note ? `：${data.note}` : ''}
            </span>
          )}
          {error && <span className="ml-2 text-rose-400">· {error}</span>}
        </p>
      </header>

      <section className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="总持仓" value={s?.total ?? '—'} />
        <Stat label="持有中 open" value={s?.open ?? '—'} tone="text-sky-300" />
        <Stat label="已平仓 closed" value={s?.closed ?? '—'} tone="text-slate-300" />
        <Stat label="open 名义敞口" value={s ? fmtUsd(s.openNotional) : '—'} />
        <Stat label="已实现 PnL" value={s ? fmtUsd(s.realizedPnl) : '—'} tone={realizedTone} />
        <Stat label="dry_run 笔数" value={s?.dryRun ?? '—'} tone="text-amber-300" />
      </section>

      <div className="overflow-x-auto rounded-lg border border-slate-700/50">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-800/60 text-slate-400">
            <tr>
              <th className="px-3 py-2 font-medium">市场（canonical）</th>
              <th className="px-3 py-2 font-medium">方向</th>
              <th className="px-3 py-2 font-medium">状态</th>
              <th className="px-3 py-2 font-medium">入场</th>
              <th className="px-3 py-2 font-medium">出场</th>
              <th className="px-3 py-2 font-medium">名义</th>
              <th className="px-3 py-2 font-medium">已实现 PnL</th>
              <th className="px-3 py-2 font-medium">开仓时间</th>
              <th className="px-3 py-2 font-medium">平仓原因</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.position_uid} className="border-t border-slate-800/60">
                <td className="max-w-[280px] px-3 py-2 text-slate-200">
                  <span className="block truncate">{p.market_name || p.canonical_market_id || '—'}</span>
                  <span className="text-[10px] text-slate-500">id {p.canonical_market_id ?? '—'}</span>
                </td>
                <td className="px-3 py-2 text-slate-400">{p.direction ?? '—'}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded border px-2 py-0.5 text-[10px] font-medium ${
                      p.status === 'open'
                        ? 'border-sky-500/30 bg-sky-500/15 text-sky-300'
                        : 'border-slate-600/40 bg-slate-700/30 text-slate-400'
                    }`}
                  >
                    {p.status ?? '—'}
                  </span>
                  {num(p.dry_run) === 1 && (
                    <span className="ml-1 rounded bg-amber-500/15 px-1 py-0.5 text-[9px] text-amber-300">dry</span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-300">{fmtPrice(p.entry_price)}</td>
                <td className="px-3 py-2 text-slate-300">{fmtPrice(p.exit_price)}</td>
                <td className="px-3 py-2 text-slate-300">{fmtUsd(p.notional_usd)}</td>
                <td
                  className={`px-3 py-2 ${
                    num(p.realized_pnl) > 0
                      ? 'text-emerald-300'
                      : num(p.realized_pnl) < 0
                        ? 'text-rose-300'
                        : 'text-slate-400'
                  }`}
                >
                  {p.realized_pnl != null ? `${p.realized_pnl > 0 ? '+' : ''}${fmtUsd(p.realized_pnl)}` : '—'}
                </td>
                <td className="px-3 py-2 text-slate-500">{fmtDate(p.opened_at)}</td>
                <td className="max-w-[160px] truncate px-3 py-2 text-slate-500">{p.close_reason || '—'}</td>
              </tr>
            ))}
            {positions.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-slate-500">
                  暂无 canonical 持仓数据（影子库为空或未生成）
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  )
}

function num(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}
