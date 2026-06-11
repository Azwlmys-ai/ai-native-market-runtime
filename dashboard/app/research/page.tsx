'use client'

// Phase 5 (Web) — 研究闭环视图（Research Loop）
// 自包含页面，不依赖主 dashboard 的复杂 hooks；只读 3 个新 API 路由：
//   /api/risk-grading（Agent M 三级）· /api/hypotheses（Agent B 假设）· /api/postmortems（Agent G 复盘）
// 体现 PRD「研究→试错→复盘→进化」闭环：当前风险等级、当前 hypothesis、最近失败原因。

import { useCallback, useEffect, useState } from 'react'

const POLL_MS = 30_000

// ── types ───────────────────────────────────────────────
interface GradeRow {
  market_id: string
  market_name: string
  direction: string
  grade: 'approve' | 'paper_probe' | 'reject'
  failure_probability: number | null
  position_size: number | null
  explanation: string
}
interface RiskGrading {
  summary: { total: number; approve: number; paper_probe: number; reject: number }
  rows: GradeRow[]
  updatedAt: string
}
interface Hypothesis {
  market_name?: string
  direction?: string
  confidence?: number | null
  expected_edge?: number | null
  holding_horizon_days?: number | null
  thesis?: string
  failure_conditions?: string | string[]
  source?: string
}
interface FailureConditionItem {
  condition: string
  category: string
  occurred: boolean | null
  basis: string
}
interface Postmortem {
  market_name?: string
  direction?: string
  outcome?: string
  realized_pnl?: number | null
  failure_reason?: string
  liquidity_issue?: boolean
  timing_issue?: boolean
  model_issue?: boolean
  hypothesis_verdict?: 'confirmed' | 'refuted' | 'loss_unexplained' | 'no_prediction' | 'inconclusive'
  failure_conditions_review?: {
    materialized_count?: number
    items?: FailureConditionItem[]
  }
  source?: string
}

// Phase 3e–3i：Learning Runtime 研究/学习产物（/api/learning）
interface LearningData {
  modelEffectiveness: {
    present: boolean
    nPostmortems?: number
    byModel: { key?: string; n_trades?: number; n_win?: number; win_rate?: number | null; total_realized_pnl?: number | null; effectiveness?: string }[]
  }
  ruleWeights: { present: boolean; nRules?: number; retireCandidates: string[]; downWeighted: string[]; entries: { key?: string; effectiveness?: string; weight?: number; recommendation?: string }[] }
  cointegration: {
    present: boolean; nCandidates?: number; nPmPm?: number; nPmAsset?: number
    candidates: { source_markets?: string[]; pair_type?: string; anchor_asset?: string | null; confidence?: number; data_sufficiency?: string; tier?: string; evidence?: { zscore?: number; corr?: number; half_life?: number | null } }[]
  }
  regimes: { present: boolean; nRegimes?: number; nTurbulent?: number; nShift?: number; entries: { series_id?: string; series_kind?: string | null; current_regime?: string; regime_shift?: boolean; news_driven?: boolean; regime_confident?: boolean; confidence?: number }[] }
  volatility: { present: boolean; nStates?: number; nElevated?: number; nClustering?: number; entries: { series_id?: string; risk_state?: string; clustering?: boolean; vol_spike?: boolean }[] }
  sizing: { present: boolean; nSuggestions?: number; entries: { market_id?: string; sized_fraction?: number; markowitz_weight?: number }[] }
}

const EFFECTIVENESS_STYLE: Record<string, string> = {
  effective: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  ineffective: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  decayed: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30',
  marginal: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  insufficient: 'bg-slate-600/20 text-slate-400 border-slate-500/30',
  inconclusive: 'bg-slate-700/20 text-slate-500 border-slate-600/30',
}
const REGIME_TONE: Record<string, string> = {
  turbulent: 'text-rose-300',
  normal: 'text-slate-300',
  calm: 'text-emerald-300',
}

const VERDICT_STYLE: Record<string, string> = {
  confirmed: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  refuted: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  loss_unexplained: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30',
  inconclusive: 'bg-slate-600/20 text-slate-300 border-slate-500/30',
  no_prediction: 'bg-slate-700/20 text-slate-500 border-slate-600/30',
}
const VERDICT_LABEL: Record<string, string> = {
  confirmed: '假设成立',
  refuted: '假设证伪',
  loss_unexplained: '亏损·预测外',
  inconclusive: '无定论',
  no_prediction: '无预测',
}

// ── small ui helpers ────────────────────────────────────
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

const GRADE_STYLE: Record<GradeRow['grade'], string> = {
  approve: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  paper_probe: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  reject: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
}
const GRADE_LABEL: Record<GradeRow['grade'], string> = {
  approve: 'APPROVE',
  paper_probe: 'PAPER_PROBE',
  reject: 'REJECT',
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="flex flex-col rounded-lg border border-slate-700/50 bg-slate-800/40 px-4 py-3">
      <span className="text-[11px] uppercase tracking-wide text-slate-400">{label}</span>
      <span className={`mt-1 text-2xl font-semibold ${tone ?? 'text-slate-100'}`}>{value}</span>
    </div>
  )
}

function asConditions(fc?: string | string[]): string[] {
  if (!fc) return []
  if (Array.isArray(fc)) return fc.map((x) => String(x))
  try {
    const p = JSON.parse(fc)
    return Array.isArray(p) ? p.map((x) => String(x)) : [String(fc)]
  } catch {
    return [String(fc)]
  }
}

// ── page ────────────────────────────────────────────────
export default function ResearchPage() {
  const { data: grading } = useJson<RiskGrading>('/api/risk-grading')
  const { data: hyp } = useJson<{ summary: { total: number; agent_b: number; derived: number }; hypotheses: Hypothesis[] }>(
    '/api/hypotheses?limit=20',
  )
  const { data: pm } = useJson<{
    summary: { total: number; win: number; loss: number; flat: number; verdicts?: Record<string, number> }
    postmortems: Postmortem[]
  }>('/api/postmortems?limit=20')
  const { data: learn } = useJson<LearningData>('/api/learning')

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-6 text-slate-200">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">研究闭环 · Research Loop</h1>
        <p className="text-xs text-slate-400">
          Agent B 假设 → Agent M 三级风控 → paper 试错 → Agent G 复盘。只读视图，30s 轮询。
        </p>
      </header>

      {/* 风险等级 */}
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-slate-300">Agent M · 三级风险评级</h2>
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="待审总数" value={grading?.summary.total ?? '—'} />
          <Stat label="approve" value={grading?.summary.approve ?? '—'} tone="text-emerald-300" />
          <Stat label="paper_probe" value={grading?.summary.paper_probe ?? '—'} tone="text-amber-300" />
          <Stat label="reject" value={grading?.summary.reject ?? '—'} tone="text-rose-300" />
        </div>
        <div className="overflow-hidden rounded-lg border border-slate-700/50">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/60 text-slate-400">
              <tr>
                <th className="px-3 py-2 font-medium">市场</th>
                <th className="px-3 py-2 font-medium">方向</th>
                <th className="px-3 py-2 font-medium">评级</th>
                <th className="px-3 py-2 font-medium">失败概率</th>
                <th className="px-3 py-2 font-medium">仓位</th>
              </tr>
            </thead>
            <tbody>
              {(grading?.rows ?? []).map((r, i) => (
                <tr key={`${r.market_id}-${i}`} className="border-t border-slate-800/60">
                  <td className="max-w-[280px] truncate px-3 py-2 text-slate-200">{r.market_name}</td>
                  <td className="px-3 py-2 text-slate-400">{r.direction}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded border px-2 py-0.5 text-[10px] font-medium ${GRADE_STYLE[r.grade]}`}>
                      {GRADE_LABEL[r.grade]}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-300">
                    {r.failure_probability != null ? `${r.failure_probability}%` : '—'}
                  </td>
                  <td className="px-3 py-2 text-slate-300">
                    {r.position_size != null ? `${(r.position_size * 100).toFixed(1)}%` : '—'}
                  </td>
                </tr>
              ))}
              {(!grading || grading.rows.length === 0) && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                    暂无评级数据（等一轮 Agent M 审查）
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* 研究假设 */}
        <section>
          <h2 className="mb-3 text-sm font-semibold text-slate-300">
            Agent B · 研究假设{' '}
            <span className="text-[11px] font-normal text-slate-500">
              （原生 {hyp?.summary.agent_b ?? 0} / 派生 {hyp?.summary.derived ?? 0}）
            </span>
          </h2>
          <div className="space-y-3">
            {(hyp?.hypotheses ?? []).map((h, i) => (
              <article key={i} className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3">
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm text-slate-100">{h.market_name}</span>
                  <span
                    className={`ml-2 shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${
                      h.source === 'agent_b'
                        ? 'border-sky-500/30 bg-sky-500/15 text-sky-300'
                        : 'border-slate-600/40 bg-slate-700/30 text-slate-400'
                    }`}
                  >
                    {h.source ?? 'derived'}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
                  <span>方向 {h.direction}</span>
                  <span>置信 {h.confidence ?? '—'}</span>
                  <span>预期边 {h.expected_edge ?? '—'}</span>
                  <span>持仓 {h.holding_horizon_days ?? '—'} 天</span>
                </div>
                {asConditions(h.failure_conditions).length > 0 && (
                  <div className="mt-2">
                    <span className="text-[10px] uppercase tracking-wide text-slate-500">失败条件</span>
                    <ul className="mt-0.5 list-disc pl-4 text-[11px] text-slate-300">
                      {asConditions(h.failure_conditions).slice(0, 3).map((c, j) => (
                        <li key={j}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </article>
            ))}
            {(!hyp || hyp.hypotheses.length === 0) && (
              <p className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 text-center text-slate-500">
                暂无假设
              </p>
            )}
          </div>
        </section>

        {/* 复盘 */}
        <section>
          <h2 className="mb-3 text-sm font-semibold text-slate-300">
            Agent G · 逐笔复盘{' '}
            <span className="text-[11px] font-normal text-slate-500">
              （win {pm?.summary.win ?? 0} / loss {pm?.summary.loss ?? 0} / flat {pm?.summary.flat ?? 0}
              {pm?.summary.verdicts?.refuted ? ` · 证伪 ${pm.summary.verdicts.refuted}` : ''}
              {pm?.summary.verdicts?.confirmed ? ` · 成立 ${pm.summary.verdicts.confirmed}` : ''}）
            </span>
          </h2>
          <div className="space-y-3">
            {(pm?.postmortems ?? []).map((p, i) => (
              <article key={i} className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3">
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm text-slate-100">{p.market_name}</span>
                  <span
                    className={`ml-2 shrink-0 text-xs font-medium ${
                      p.outcome === 'win'
                        ? 'text-emerald-300'
                        : p.outcome === 'loss'
                          ? 'text-rose-300'
                          : 'text-slate-400'
                    }`}
                  >
                    {p.outcome} {p.realized_pnl != null ? `${p.realized_pnl > 0 ? '+' : ''}${p.realized_pnl}` : ''}
                  </span>
                </div>
                {p.failure_reason && <p className="mt-1 text-[11px] text-slate-300">{p.failure_reason}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {p.hypothesis_verdict && p.hypothesis_verdict !== 'no_prediction' && (
                    <span
                      className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                        VERDICT_STYLE[p.hypothesis_verdict] ?? VERDICT_STYLE.no_prediction
                      }`}
                    >
                      失败条件对照：{VERDICT_LABEL[p.hypothesis_verdict] ?? p.hypothesis_verdict}
                    </span>
                  )}
                  {p.liquidity_issue && (
                    <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">流动性</span>
                  )}
                  {p.timing_issue && (
                    <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] text-sky-300">时机</span>
                  )}
                  {p.model_issue && (
                    <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-300">模型</span>
                  )}
                </div>
                {(p.failure_conditions_review?.items?.length ?? 0) > 0 && (
                  <ul className="mt-2 space-y-0.5 border-t border-slate-700/40 pt-2 text-[11px]">
                    {p.failure_conditions_review!.items!.slice(0, 3).map((it, j) => (
                      <li key={j} className="flex items-start gap-1.5">
                        <span
                          className={
                            it.occurred === true
                              ? 'text-rose-300'
                              : it.occurred === false
                                ? 'text-emerald-300'
                                : 'text-slate-500'
                          }
                        >
                          {it.occurred === true ? '●发生' : it.occurred === false ? '○未发生' : '◌未知'}
                        </span>
                        <span className="text-slate-400">{it.condition}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
            {(!pm || pm.postmortems.length === 0) && (
              <p className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 text-center text-slate-500">
                暂无复盘
              </p>
            )}
          </div>
        </section>
      </div>

      {/* 模型与学习 · Models & Learning (Phase 3e–3i) */}
      <section className="mt-10">
        <h2 className="mb-3 text-sm font-semibold text-slate-300">
          模型与学习 · Models &amp; Learning{' '}
          <span className="text-[11px] font-normal text-slate-500">
            （协整 / HMM regime / GARCH / Kelly·Markowitz — 全部 enforced=false 研究/建议产物）
          </span>
        </h2>
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="复盘样本" value={learn?.modelEffectiveness.nPostmortems ?? '—'} />
          <Stat label="协整候选" value={learn?.cointegration.nCandidates ?? '—'} tone="text-sky-300" />
          <Stat label="跨资产" value={learn?.cointegration.nPmAsset ?? '—'} tone="text-sky-300" />
          <Stat label="regime 动荡" value={learn?.regimes.nTurbulent ?? '—'} tone="text-rose-300" />
          <Stat label="波动升高" value={learn?.volatility.nElevated ?? '—'} tone="text-amber-300" />
          <Stat label="仓位建议" value={learn?.sizing.nSuggestions ?? '—'} />
        </div>

        <div className="grid gap-8 lg:grid-cols-2">
          {/* 模型有效性 by_model */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              模型有效性 · by_model（闭环归因）
            </h3>
            <div className="overflow-hidden rounded-lg border border-slate-700/50">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-800/60 text-slate-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">模型</th>
                    <th className="px-3 py-2 font-medium">样本</th>
                    <th className="px-3 py-2 font-medium">胜率</th>
                    <th className="px-3 py-2 font-medium">盈亏</th>
                    <th className="px-3 py-2 font-medium">裁定</th>
                  </tr>
                </thead>
                <tbody>
                  {(learn?.modelEffectiveness.byModel ?? []).map((m, i) => (
                    <tr key={`${m.key}-${i}`} className="border-t border-slate-800/60">
                      <td className="px-3 py-2 text-slate-200">{m.key}</td>
                      <td className="px-3 py-2 text-slate-400">{m.n_trades ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-300">{m.win_rate != null ? `${(m.win_rate * 100).toFixed(0)}%` : '—'}</td>
                      <td className={`px-3 py-2 ${(m.total_realized_pnl ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                        {m.total_realized_pnl ?? '—'}
                      </td>
                      <td className="px-3 py-2">
                        {m.effectiveness && (
                          <span className={`rounded border px-1.5 py-0.5 text-[10px] ${EFFECTIVENESS_STYLE[m.effectiveness] ?? EFFECTIVENESS_STYLE.inconclusive}`}>
                            {m.effectiveness}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {(!learn || learn.modelEffectiveness.byModel.length === 0) && (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                        暂无真实模型成交归因（待 paper_probe 积累）
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {(learn?.ruleWeights.retireCandidates.length ?? 0) > 0 && (
              <p className="mt-2 text-[11px] text-slate-400">
                规则淘汰候选：
                {learn!.ruleWeights.retireCandidates.map((k) => (
                  <span key={k} className="ml-1 rounded bg-fuchsia-500/15 px-1.5 py-0.5 text-fuchsia-300">{k}</span>
                ))}
              </p>
            )}
          </div>

          {/* 协整 / 跨市场关联候选 */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              协整候选 · 跨市场关联（含跨资产）
            </h3>
            <div className="space-y-2">
              {(learn?.cointegration.candidates ?? []).map((c, i) => (
                <article key={i} className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="truncate text-xs text-slate-100">
                      {(c.source_markets ?? []).join(' ↔ ')}
                    </span>
                    <span className={`ml-2 shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${
                      c.pair_type === 'pm_asset'
                        ? 'border-violet-500/30 bg-violet-500/15 text-violet-300'
                        : 'border-sky-500/30 bg-sky-500/15 text-sky-300'
                    }`}>
                      {c.pair_type === 'pm_asset' ? `跨资产·${c.anchor_asset ?? ''}` : 'pm×pm'}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-slate-400">
                    <span>z {c.evidence?.zscore ?? '—'}</span>
                    <span>corr {c.evidence?.corr ?? '—'}</span>
                    <span>半衰期 {c.evidence?.half_life ?? '—'}</span>
                    <span>置信 {c.confidence ?? '—'}</span>
                    {c.tier === 'exploration' && (
                      <span className="rounded bg-amber-500/15 px-1.5 text-amber-300">探索</span>
                    )}
                  </div>
                </article>
              ))}
              {(!learn || learn.cointegration.candidates.length === 0) && (
                <p className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 text-center text-slate-500">
                  暂无协整候选（价格历史累积后出现）
                </p>
              )}
            </div>
          </div>

          {/* regime + 波动状态 */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              市场状态 · HMM regime + GARCH 波动
            </h3>
            <div className="space-y-1.5">
              {(learn?.regimes.entries ?? []).slice(0, 8).map((r, i) => (
                <div key={i} className="flex items-center justify-between rounded border border-slate-700/40 bg-slate-800/30 px-3 py-1.5 text-[11px]">
                  <span className="truncate text-slate-300">{r.series_id} <span className="text-slate-500">{r.series_kind}</span></span>
                  <span className="flex items-center gap-1.5">
                    {r.regime_shift && <span className="rounded bg-sky-500/15 px-1 text-sky-300">切换</span>}
                    {r.news_driven && <span className="rounded bg-rose-500/15 px-1 text-rose-300">新闻</span>}
                    <span className={`font-medium ${REGIME_TONE[r.current_regime ?? ''] ?? 'text-slate-300'}`}>
                      {r.current_regime}
                    </span>
                  </span>
                </div>
              ))}
              {(!learn || learn.regimes.entries.length === 0) && (
                <p className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 text-center text-slate-500">暂无 regime 数据</p>
              )}
            </div>
          </div>

          {/* Kelly/Markowitz 仓位建议 */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              仓位建议 · Kelly × regime + Markowitz（enforced=false）
            </h3>
            <div className="overflow-hidden rounded-lg border border-slate-700/50">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-800/60 text-slate-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">市场</th>
                    <th className="px-3 py-2 font-medium">Kelly×regime</th>
                    <th className="px-3 py-2 font-medium">Markowitz 权重</th>
                  </tr>
                </thead>
                <tbody>
                  {(learn?.sizing.entries ?? []).map((s, i) => (
                    <tr key={`${s.market_id}-${i}`} className="border-t border-slate-800/60">
                      <td className="px-3 py-2 text-slate-200">{s.market_id}</td>
                      <td className="px-3 py-2 text-slate-300">{s.sized_fraction != null ? `${(s.sized_fraction * 100).toFixed(2)}%` : '—'}</td>
                      <td className="px-3 py-2 text-slate-400">{s.markowitz_weight != null ? `${(s.markowitz_weight * 100).toFixed(1)}%` : '—'}</td>
                    </tr>
                  ))}
                  {(!learn || learn.sizing.entries.length === 0) && (
                    <tr>
                      <td colSpan={3} className="px-3 py-6 text-center text-slate-500">暂无仓位建议</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
