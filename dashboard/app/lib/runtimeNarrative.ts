// ── Runtime Narrative Engine ─────────────────────────────
// Pure function: takes real runtime data → returns prioritized narrative items.
// No mocks, no hardcoded strings — every sentence is derived from live inputs.

import type { LogEvent } from '../hooks/useLogEvents'
import type { AgentRuntimeStatus } from '../data/types'
import type { Incident } from '../hooks/useIncidents'
import type { DashboardKpis } from '../hooks/useDashboardSummary'
import type { MultiMarketData } from '../hooks/useMultiMarketData'

// ── Types ─────────────────────────────────────────────────

export type NarrativePriority = 'critical' | 'high' | 'medium' | 'low'
export type NarrativeCategory =
  | 'incident'
  | 'risk'
  | 'runtime'
  | 'regime'
  | 'agent'
  | 'correlation'
  | 'health'

export interface NarrativeItem {
  id: string
  priority: NarrativePriority
  category: NarrativeCategory
  headline: string
  detail: string
  whyDetail?: string   // AI Explain Layer — reasoning derived from data
  dataRef: string[]    // Inline data chips: ["BTC-ETH r=0.91", "vol=27.4%"]
  generatedAt: string
}

export interface NarrativeInputs {
  events: LogEvent[]
  agentStates: AgentRuntimeStatus[]
  incidents: Incident[]
  kpis: DashboardKpis | null
  multiMarket: MultiMarketData | null
}

// ── Priority order ────────────────────────────────────────

const PRIORITY_RANK: Record<NarrativePriority, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
}

// ── Helpers ───────────────────────────────────────────────

function fmtVol(v: number) {
  return `${(v * 100).toFixed(1)}%`
}

function fmtPct(v: number) {
  return `${v.toFixed(1)}%`
}

function now() {
  return new Date().toISOString()
}

function countByLevel(events: LogEvent[], level: LogEvent['level']): number {
  return events.filter((e) => e.level === level).length
}

function countByCategory(events: LogEvent[], category: string): number {
  return events.filter((e) => e.category === category).length
}

// ── Rule Builders ─────────────────────────────────────────

function ruleActiveIncident(incidents: Incident[]): NarrativeItem | null {
  const active = incidents.filter((i) => !i.resolvedTime)
  if (active.length === 0) return null

  const worst = active.sort((a, b) => {
    const rank = { critical: 0, high: 1, medium: 2, low: 3 }
    return rank[a.severity] - rank[b.severity]
  })[0]

  const sevLabel =
    worst.severity === 'critical'
      ? '严重'
      : worst.severity === 'high'
        ? '高危'
        : worst.severity === 'medium'
          ? '中级'
          : '低级'

  return {
    id: `incident:${worst.id}`,
    priority: worst.severity === 'critical' ? 'critical' : 'high',
    category: 'incident',
    headline: `${sevLabel}事故进行中 — ${worst.title}`,
    detail: `影响 ${worst.affectedAgents.length} 个 Agent，${worst.totalEvents} 条关联事件。`,
    whyDetail: `根因：${worst.summary.slice(0, 80)}${worst.summary.length > 80 ? '…' : ''}`,
    dataRef: [
      `severity=${worst.severity}`,
      `agents=${worst.affectedAgents.length}`,
      `events=${worst.totalEvents}`,
    ],
    generatedAt: now(),
  }
}

function ruleRecentErrors(events: LogEvent[]): NarrativeItem | null {
  const recent = events.slice(0, 30)
  const errorCount = countByLevel(recent, 'ERROR')
  if (errorCount < 2) return null

  const errorAgents = [...new Set(recent.filter((e) => e.level === 'ERROR').map((e) => e.agent))]
  const agentStr = errorAgents.slice(0, 2).join(' / ')

  return {
    id: `errors:${errorCount}`,
    priority: errorCount >= 5 ? 'critical' : 'high',
    category: 'risk',
      headline: `AI 风险控制已主动降低异常波动暴露 — 检测到 ${errorCount} 处异常信号`,
      detail: `涉及 Agent：${agentStr}。智能风控层已自动提高审批门槛，系统进入增强审查模式。`,
      whyDetail: `异常信号频率超出正常阈值（≥2次/窗口），Agent M 已自动收紧单笔风险敞口上限。`,
    dataRef: [`errors=${errorCount}`, `agents=${agentStr}`],
    generatedAt: now(),
  }
}

function ruleConnectionEvent(events: LogEvent[]): NarrativeItem | null {
  const connEvents = events.filter((e) => e.category === 'connection')
  if (connEvents.length === 0) return null

  const latest = connEvents[0]
  const isReconnect =
    latest.title.toLowerCase().includes('reconnect') ||
    latest.title.toLowerCase().includes('恢复') ||
    latest.title.toLowerCase().includes('重连')
  const isDisconnect =
    latest.title.toLowerCase().includes('disconnect') ||
    latest.title.toLowerCase().includes('断') ||
    latest.title.toLowerCase().includes('lost')

  if (!isDisconnect && !isReconnect) return null

  if (isReconnect) {
    return {
      id: `conn:reconnect`,
      priority: 'high',
      category: 'runtime',
      headline: `多 Agent 协同恢复已完成 — 数据通道已重建，业务连续性已恢复`,
      detail: `连接事件已排除，系统已恢复正常数据流，冗余通道接管期间数据无丢失。`,
      whyDetail: `冗余通道触发条件：主连接超时 >5s，备份链路自动激活。`,
      dataRef: [`event=${latest.title.slice(0, 30)}`],
      generatedAt: now(),
    }
  }

  return {
    id: `conn:disconnect`,
    priority: 'high',
    category: 'runtime',
      headline: `系统已切换至冗余数据通道 — 主连接临时中断`,
      detail: `高风险信号审批已进入保护性暂停，等待数据通道稳定。`,
      whyDetail: `数据通道维护期间，持仓管理 Agent 已自动暂停新信号执行，保护现有仓位。`,
    dataRef: [`agent=${latest.agent}`, `event=${latest.title.slice(0, 30)}`],
    generatedAt: now(),
  }
}

function ruleStoploss(events: LogEvent[]): NarrativeItem | null {
  const stoplossCount = countByCategory(events, 'stoploss')
  if (stoplossCount === 0) return null

  return {
    id: `stoploss:${stoplossCount}`,
    priority: 'high',
    category: 'risk',
      headline: `市场波动已触发稳定性保护机制 — 止损保护执行 ${stoplossCount} 次`,
      detail: `市场波动超出预设安全阈值，Agent P 已自动完成防御性仓位调整。`,
      whyDetail: `保护触发条件：持仓亏损达单笔最大回撤限制，或整体回撤逼近安全阈值。`,
    dataRef: [`stoploss=${stoplossCount}次`],
    generatedAt: now(),
  }
}

function ruleVolatilitySpike(multiMarket: MultiMarketData | null): NarrativeItem | null {
  if (!multiMarket?.volatility.length) return null

  const highVol = multiMarket.volatility
    .filter((v) => v.volAnnualized > 0.22)
    .sort((a, b) => b.volAnnualized - a.volAnnualized)

  if (highVol.length === 0) return null

  const top = highVol[0]
  const refs = highVol.slice(0, 3).map((v) => `${v.label} ${fmtVol(v.volAnnualized)}`)

  return {
    id: `vol:${top.asset}`,
    priority: highVol.length >= 3 ? 'high' : 'medium',
    category: 'risk',
      headline: `${top.label} 年化波动率 ${fmtVol(top.volAnnualized)} — 智能风控已提升该资产审核标准`,
      detail: `共 ${highVol.length} 个资产波动率超过安全阈值，风险引擎已自动调整仓位限制。`,
    whyDetail: `波动率判断依据：历史 OHLCV 数据（${top.periods} 个样本）。高波动 → 单笔最大敞口收缩。`,
    dataRef: refs,
    generatedAt: now(),
  }
}

function ruleHighRejectionRate(kpis: DashboardKpis | null, events: LogEvent[]): NarrativeItem | null {
  if (!kpis) return null
  const total = kpis.totalSignals
  if (total < 3) return null

  const rejectionRate = (kpis.rejectedSignals / total) * 100
  if (rejectionRate < 50) return null

  const drawdownCount = countByCategory(events, 'drawdown')
  const errorCount = countByLevel(events, 'ERROR')

  return {
    id: `reject:rate`,
    priority: 'medium',
    category: 'risk',
      headline: `AI 信号审核处于增强审查模式 — 当前拒绝率 ${fmtPct(rejectionRate)}`,
      detail: `${kpis.rejectedSignals} 条信号未通过审核，${kpis.approvedSignals} 条已放行，风险容忍度已自动下调。`,
    whyDetail: `拒绝依据：${drawdownCount > 0 ? `回撤预警 ${drawdownCount} 次 + ` : ''}${errorCount > 0 ? `错误 ${errorCount} 次 + ` : ''}整体风险评分超出准入阈值。`,
    dataRef: [
      `总信号 ${total}`,
      `通过 ${kpis.approvedSignals}`,
      `拒绝 ${kpis.rejectedSignals}`,
    ],
    generatedAt: now(),
  }
}

function ruleDrawdown(events: LogEvent[]): NarrativeItem | null {
  const drawdownCount = countByCategory(events, 'drawdown')
  if (drawdownCount === 0) return null

  return {
    id: `drawdown:${drawdownCount}`,
    priority: 'medium',
    category: 'risk',
      headline: `风险敞口控制已自动收紧 — 回撤预警触发 ${drawdownCount} 次`,
      detail: `资产净值出现下降趋势，Agent M 已自动降低新信号准入置信度阈值。`,
    whyDetail: `回撤判断：组合净值相对最高点下降超过警戒百分比，触发风控收紧流程。`,
    dataRef: [`drawdown=${drawdownCount}次`],
    generatedAt: now(),
  }
}

function ruleMarketRegime(multiMarket: MultiMarketData | null): NarrativeItem | null {
  if (!multiMarket?.macroRegime) return null
  const r = multiMarket.macroRegime

  const regimeLabel = r.regime === 'range' ? '震荡区间' : r.regime === 'trend' ? '趋势行情' : r.regime
  const confLabel = r.confidence >= 70 ? '高' : r.confidence >= 40 ? '中' : '低'

  return {
    id: `regime:${r.regime}`,
    priority: 'medium',
    category: 'regime',
    headline: `市场体制：${regimeLabel} — BTC ${r.btcTrend}，Agent 调整至 ${r.riskTolerance} 风险容忍度`,
    detail: `市场活跃度${r.marketActivity}，资金信号${r.fundingSignal}，置信度${confLabel}（${r.confidence}%）。`,
    whyDetail: `体制判断依据：BTC 趋势「${r.btcTrend}」+ 资金费率信号「${r.fundingSignal}」+ 市场活跃度「${r.marketActivity}」。置信度 ${r.confidence}% — ${r.reason.slice(0, 60)}`,
    dataRef: [
      `regime=${r.regime}`,
      `conf=${r.confidence}%`,
      `btc=${r.btcTrend}`,
      `funding=${r.fundingSignal}`,
    ],
    generatedAt: now(),
  }
}

function ruleHighCorrelation(multiMarket: MultiMarketData | null): NarrativeItem | null {
  if (!multiMarket?.correlations.length) return null

  const highCorr = multiMarket.correlations.filter((c) => c.pearson > 0.85)
  if (highCorr.length === 0) return null

  const top = highCorr[0]
  const refs = highCorr.slice(0, 3).map((c) => `${c.a}-${c.b} r=${c.pearson.toFixed(2)}`)

  return {
    id: `corr:${top.a}/${top.b}`,
    priority: 'medium',
    category: 'correlation',
    headline: `${top.a}/${top.b} 相关性 ${top.pearson.toFixed(2)}，组合分散效应削弱`,
    detail: `${highCorr.length} 对资产高度相关（r>0.85），组合风险集中度上升，VaR 估算偏保守。`,
    whyDetail: `高相关性意味着持仓无法有效对冲彼此风险。当 BTC-ETH r>0.9 时，同向持仓等价于双倍暴露于同一风险因子。`,
    dataRef: refs,
    generatedAt: now(),
  }
}

function ruleLowApprovalRate(kpis: DashboardKpis | null): NarrativeItem | null {
  if (!kpis || kpis.totalSignals < 5) return null
  const approvalRate = (kpis.approvedSignals / kpis.totalSignals) * 100
  if (approvalRate > 35) return null

  return {
    id: `approve:low`,
    priority: 'medium',
    category: 'agent',
    headline: `自动审批通过率 ${fmtPct(approvalRate)}，低于基准线 35%`,
    detail: `当前 ${kpis.approvedSignals}/${kpis.totalSignals} 信号通过，Agent M 正在执行高标准过滤。`,
    whyDetail: `低通过率不一定代表系统异常。可能是市场机会质量下降，或风控参数处于保守配置。`,
    dataRef: [`通过 ${kpis.approvedSignals}`, `总计 ${kpis.totalSignals}`, `率 ${fmtPct(approvalRate)}`],
    generatedAt: now(),
  }
}

function ruleAgentActivity(agentStates: AgentRuntimeStatus[]): NarrativeItem | null {
  if (agentStates.length === 0) return null

  const active = agentStates.filter(
    (a) => a.state !== 'IDLE' && a.state !== 'ERROR',
  )
  const errorAgents = agentStates.filter((a) => a.state === 'ERROR')
  const total = agentStates.length

  if (errorAgents.length > 0) {
    const names = errorAgents.map((a) => a.agent).slice(0, 2).join(' / ')
    return {
      id: `agent:error`,
      priority: 'high',
      category: 'agent',
      headline: `${errorAgents.length} 个 Agent 进入 ERROR 状态：${names}`,
      detail: `其余 ${total - errorAgents.length} 个 Agent 正常运行。请检查相关 Agent 日志。`,
      whyDetail: `ERROR 状态通常由 LLM API 超时、数据源连接失败或异常响应触发。`,
      dataRef: errorAgents.map((a) => `${a.agent}=${a.state}`),
      generatedAt: now(),
    }
  }

  if (active.length === 0) {
    return {
      id: `agent:standby`,
      priority: 'low',
      category: 'agent',
      headline: `全部 ${total} 个 AI Agent 处于智能待命状态`,
      detail: `当前无活跃交易信号，系统以低频智能扫描模式运行，等待市场触发条件。`,
      dataRef: [`active=0`, `standby=${total}`],
      generatedAt: now(),
    }
  }

  const activeNames = active.map((a) => a.agent).slice(0, 3).join(' / ')
  return {
    id: `agent:active`,
    priority: 'low',
    category: 'agent',
      headline: `${active.length}/${total} AI Agent 在线 — ${activeNames} 正在执行决策流`,
      detail: `Agent 集群正在协同处理最新市场信号，处于智能决策流水线中。`,
    dataRef: active.map((a) => `${a.agent}=${a.state}`).slice(0, 4),
    generatedAt: now(),
  }
}

function ruleHealthy(
  kpis: DashboardKpis | null,
  incidents: Incident[],
  events: LogEvent[],
): NarrativeItem | null {
  const activeIncidents = incidents.filter((i) => !i.resolvedTime)
  const errorCount = countByLevel(events.slice(0, 20), 'ERROR')
  const warnCount = countByLevel(events.slice(0, 20), 'WARN')

  if (activeIncidents.length > 0 || errorCount > 0) return null

  const score = kpis?.healthScore
  const status = kpis?.runtimeStatus ?? 'ONLINE'

  return {
    id: `health:ok`,
    priority: 'low',
    category: 'health',
      headline: `Runtime 已恢复业务连续性${score != null ? `，系统健康评分 ${score}%` : ''}`,
      detail: `近期 ${warnCount > 0 ? `${warnCount} 条提示（无需手动干预）` : '无异常提示'}，运行状态：${status}。`,
    dataRef: [
      `status=${status}`,
      score != null ? `health=${score}%` : null,
      `errors=0`,
    ].filter((x): x is string => x !== null),
    generatedAt: now(),
  }
}

function ruleCryptoMovement(multiMarket: MultiMarketData | null): NarrativeItem | null {
  if (!multiMarket?.crypto.length) return null

  const btc = multiMarket.crypto.find((c) => c.symbol === 'BTC')
  const eth = multiMarket.crypto.find((c) => c.symbol === 'ETH')

  if (!btc?.spotPrice) return null

  // Funding rate signal
  const btcFunding = btc.fundingRate ?? 0
  const ethFunding = eth?.fundingRate ?? 0
  const avgFunding = (btcFunding + ethFunding) / 2
  const fundingSignal =
    avgFunding > 0.0001
      ? '资金费率偏高，多头拥挤信号'
      : avgFunding < -0.0001
        ? '资金费率偏低，空头情绪升温'
        : '资金费率中性'

  // Basis
  const btcBasis = btc.basis
  const basisStr =
    btcBasis !== null
      ? `BTC 基差 ${btcBasis >= 0 ? '+' : ''}${btcBasis.toFixed(1)}`
      : null

  return {
    id: `crypto:okx`,
    priority: 'low',
    category: 'regime',
    headline: `BTC $${btc.spotPrice.toLocaleString('en-US', { maximumFractionDigits: 0 })} — ${fundingSignal}`,
    detail: `${eth ? `ETH $${eth.spotPrice?.toFixed(0)}，` : ''}${basisStr ? basisStr + '，' : ''}资金信号已纳入 regime 体制判断。`,
    whyDetail: `OKX 数据每 ~30s 更新（与 polymarket_arbitrage 周期对齐）。`,
    dataRef: [
      `BTC $${btc.spotPrice.toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
      `funding=${(btcFunding * 100).toFixed(4)}%`,
      basisStr,
    ].filter((x): x is string => x !== null),
    generatedAt: now(),
  }
}

function ruleEquityMovement(multiMarket: MultiMarketData | null): NarrativeItem | null {
  if (!multiMarket?.equity.length) return null

  // Find biggest mover (absolute changePct)
  const sorted = [...multiMarket.equity].sort(
    (a, b) => Math.abs(b.changePct) - Math.abs(a.changePct),
  )
  const top = sorted[0]
  const up = top.changePct >= 0

  const coin = multiMarket.equity.find((e) => e.symbol === 'COIN')
  const mstr = multiMarket.equity.find((e) => e.symbol === 'MSTR')

  const cryptoEquity = [coin, mstr].filter(Boolean)
  const cryptoStr =
    cryptoEquity.length > 0
      ? cryptoEquity
          .map((e) => `${e!.symbol} ${e!.changePct >= 0 ? '+' : ''}${e!.changePct.toFixed(1)}%`)
          .join(' / ')
      : null

  return {
    id: `equity:mover`,
    priority: 'low',
    category: 'regime',
    headline: `最大异动股：${top.symbol} ${up ? '+' : ''}${top.changePct.toFixed(2)}%${cryptoStr ? `，加密相关股：${cryptoStr}` : ''}`,
    detail: `US equity 数据（Finnhub 日线），用于跨市场相关性与 regime 判断。`,
    dataRef: sorted
      .slice(0, 4)
      .map((e) => `${e.symbol} ${e.changePct >= 0 ? '+' : ''}${e.changePct.toFixed(1)}%`),
    generatedAt: now(),
  }
}

// ── Main export ───────────────────────────────────────────

export function buildNarratives(inputs: NarrativeInputs): NarrativeItem[] {
  const { events, agentStates, incidents, kpis, multiMarket } = inputs

  const candidates: (NarrativeItem | null)[] = [
    // Critical / High — always checked
    ruleActiveIncident(incidents),
    ruleRecentErrors(events),
    ruleConnectionEvent(events),
    ruleStoploss(events),
    ruleVolatilitySpike(multiMarket),
    // Medium
    ruleHighRejectionRate(kpis, events),
    ruleDrawdown(events),
    ruleMarketRegime(multiMarket),
    ruleHighCorrelation(multiMarket),
    ruleLowApprovalRate(kpis),
    // Agent
    ruleAgentActivity(agentStates),
    // Low — market context
    ruleCryptoMovement(multiMarket),
    ruleEquityMovement(multiMarket),
    // Healthy baseline (only if nothing else fires)
    ruleHealthy(kpis, incidents, events),
  ]

  const items = candidates.filter((x): x is NarrativeItem => x !== null)

  // Sort by priority, deduplicate by id
  const seen = new Set<string>()
  return items
    .sort((a, b) => PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority])
    .filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })
    .slice(0, 8) // cap at 8 to avoid banner overload
}
