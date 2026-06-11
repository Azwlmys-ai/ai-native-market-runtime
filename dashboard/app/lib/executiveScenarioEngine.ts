// ── Executive Scenario Engine ──────────────────────────────────
// 基于 Runtime 数据自动推导 AI 战略情景。
// 每个 scenario 包含：风险说明、AI 响应路径、业务影响、建议动作、时间线步骤。
//
// 禁止工程语言，全部使用企业高管叙事风格。

import type { DashboardKpis } from '../hooks/useDashboardSummary'

// ── Scenario Types ──────────────────────────────────────────

export type ScenarioKind =
  | 'market_crash'
  | 'data_outage'
  | 'high_volatility'
  | 'liquidity_drop'
  | 'risk_lockdown'
  | 'agent_recovery'
  | 'normal_operations'

export type ScenarioSeverity = 'critical' | 'high' | 'moderate' | 'low' | 'normal'

export interface TimelineStep {
  timeOffset: string
  description: string
  status: 'completed' | 'in_progress' | 'pending'
}

export interface ExecutiveScenario {
  scenarioId: string
  kind: ScenarioKind
  title: string
  executiveSummary: string
  businessRisk: string
  aiResponse: string
  expectedImpact: string
  recommendedAction: string
  severity: ScenarioSeverity
  confidence: number
  affectedModules: string[]
  timelineSteps: TimelineStep[]
}

// ── Scenario Derivation Input ───────────────────────────────

export interface ScenarioDerivationInput {
  kpis: DashboardKpis | null
  unresolvedIncidents: number
  hasActiveRecovery: boolean
  sseConnected: boolean
}

// ── Scenario Templates ──────────────────────────────────────

function buildNormalOperations(confidence: number): ExecutiveScenario {
  return {
    scenarioId: 'normal_operations',
    kind: 'normal_operations',
    title: '常规运营模式',
    executiveSummary:
      '系统运行平稳，AI 多智能体协同处于标准监控模式。当前市场环境风险可控，所有数据通道正常运转，无活跃事故。',
    businessRisk: '当前业务风险处于正常水平，无需额外保护措施。',
    aiResponse:
      'AI 协同网络维持标准监控频率，智能研究 Agent 持续评估市场动态，风控 Agent 处于待命状态，审批流程按标准策略执行。',
    expectedImpact:
      '预期 ROI 维持在基准水平，业务连续性指标全部达标，信号处理延迟在优化区间内。',
    recommendedAction:
      '维持当前监控策略不变，建议关注跨市场相关性变化趋势，如有异常信号及时调整风控阈值。',
    severity: 'normal',
    confidence,
    affectedModules: ['标准监控', 'AI 研究', '风控待命', '自动审批'],
    timelineSteps: [
      {
        timeOffset: '持续',
        description: 'AI 多智能体持续监控全局市场动态',
        status: 'in_progress',
      },
      {
        timeOffset: '持续',
        description: '风控系统按标准策略运行',
        status: 'in_progress',
      },
      {
        timeOffset: '持续',
        description: '业务连续性指标实时校验',
        status: 'in_progress',
      },
    ],
  }
}

function buildHighVolatility(kpis: DashboardKpis | null, confidence: number): ExecutiveScenario {
  const regime = kpis?.regime || '高波动'
  return {
    scenarioId: 'high_volatility',
    kind: 'high_volatility',
    title: '市场剧烈波动 — AI 风险控制已主动降低异常波动暴露',
    executiveSummary:
      `当前市场进入${regime}状态，AI 风控系统已自动提升审查等级。` +
      '多 Agent 协同网络正在加速分析波动传导路径，主动缩小风险暴露窗口。',
    businessRisk:
      '市场异常波动可能导致信号质量下降、套利窗口收窄、组合风险集中度上升。' +
      '若波动持续扩大，部分自动化策略可能被临时冻结以保护资产安全。',
    aiResponse:
      '系统已切换至增强审查模式：风控 Agent 收紧审批阈值，研究 Agent 优先分析波动源，' +
      '执行 Agent 放缓交易节奏。AI 协同网络自动分配更多算力至风险监测模块。',
    expectedImpact:
      '波动期间预期信号通过率下降 15-25%，但可有效降低尾部风险暴露。' +
      '业务连续性保护机制已激活，核心功能不受影响。',
    recommendedAction:
      '建议维持增强审查模式至少 15 分钟，观察波动是否回归正常区间。' +
      '如波动持续扩大，可考虑手动冻结高风险市场对。',
    severity: 'high',
    confidence,
    affectedModules: ['风控审查', '信号审批', '执行管理', '波动率监测', '风险敞口计算'],
    timelineSteps: [
      {
        timeOffset: 'T+0s',
        description: '波动率监测 Agent 检测到异常波动信号，发出初级预警',
        status: 'completed',
      },
      {
        timeOffset: 'T+2s',
        description: '风控 Agent 自动提升审批等级，收紧信号通过阈值',
        status: 'completed',
      },
      {
        timeOffset: 'T+5s',
        description: '研究 Agent 启动波动传导分析，识别受影响市场对',
        status: 'completed',
      },
      {
        timeOffset: 'T+10s',
        description: '执行 Agent 调整交易节奏，降低高风险敞口',
        status: 'in_progress',
      },
      {
        timeOffset: 'T+30s',
        description: 'AI 协同网络评估波动稳定性，决定是否解除增强审查',
        status: 'pending',
      },
    ],
  }
}

function buildDataOutage(confidence: number): ExecutiveScenario {
  return {
    scenarioId: 'data_outage',
    kind: 'data_outage',
    title: '数据通道异常 — 系统已切换至冗余数据通道',
    executiveSummary:
      '主数据通道出现异常，系统自动切换至备用通道。AI 多智能体正在通过冗余链路重建数据视图，' +
      '业务连续性保护已启动。',
    businessRisk:
      '数据通道中断可能导致实时信号延迟增加、部分市场数据更新滞后。' +
      '在冗余通道稳定运行前，部分依赖实时数据的决策模块可能进入保守模式。',
    aiResponse:
      '系统已自动完成以下动作：1) 检测到主通道异常并立即切换至备用链路；' +
      '2) 数据完整性校验通过后进行增量数据同步；' +
      '3) 风控系统在恢复期间提升审查阈值以保护资产安全；' +
      '4) 多 Agent 协同恢复协议已执行完毕。',
    expectedImpact:
      '冗余通道切换耗时约 2-5 秒，期间信号处理暂停。恢复后数据延迟在可接受范围内。' +
      '长期影响：无，系统已恢复业务连续性。',
    recommendedAction:
      '无需人工干预，系统已通过多 Agent 协同恢复完成通道切换。' +
      '建议在恢复后 1 分钟内观察数据一致性指标，如有异常再介入。',
    severity: 'moderate',
    confidence,
    affectedModules: ['数据通道', '实时信号', '市场数据面板', '风险敞口计算'],
    timelineSteps: [
      {
        timeOffset: 'T+0s',
        description: '主数据通道检测到异常信号中断',
        status: 'completed',
      },
      {
        timeOffset: 'T+1s',
        description: '系统自动启动冗余通道切换协议',
        status: 'completed',
      },
      {
        timeOffset: 'T+3s',
        description: '备用链路建立成功，数据完整性校验通过',
        status: 'completed',
      },
      {
        timeOffset: 'T+5s',
        description: '增量数据同步完成，所有模块恢复正常运行',
        status: 'completed',
      },
      {
        timeOffset: '持续',
        description: '系统持续监控数据通道状态，主通道恢复后将自动切回',
        status: 'in_progress',
      },
    ],
  }
}

function buildRiskLockdown(unresolvedIncidents: number, confidence: number): ExecutiveScenario {
  return {
    scenarioId: 'risk_lockdown',
    kind: 'risk_lockdown',
    title: '风险锁定 — AI 已启动全面风险暴露收缩',
    executiveSummary:
      `系统检测到 ${unresolvedIncidents} 起活跃事故，AI 自动触发风险锁定协议。` +
      '所有非必要的自动化审批已临时冻结，风险暴露正在主动收缩。业务连续性保护模式已激活。',
    businessRisk:
      '多起事故同时活跃可能表明系统性风险正在积聚。如不及时收敛，' +
      '可能导致交易信号验证延迟增加、部分 Agent 集群负载升高、关键决策路径拥堵。',
    aiResponse:
      'AI 协同网络已执行以下保护动作：1) 非关键审批路径临时冻结；' +
      '2) 研究 Agent 集群重新分配至风险评估优先；' +
      '3) 执行 Agent 停止新开仓操作；' +
      '4) 学习 Agent 分析事故根因并生成恢复策略；' +
      '5) 风控 Agent 将所有敞口收缩至安全边界以内。',
    expectedImpact:
      '短期内信号吞吐量下降约 30-40%，但可有效防止事故链反应。' +
      '系统预计在事故收敛后 2-5 分钟内恢复正常运作。',
    recommendedAction:
      '建议等待 AI 自动恢复流程完成，同时关注事故指挥中心中的处置进度。' +
      '如事故超过 5 分钟未收敛，可手动触发全局安全模式。',
    severity: 'critical',
    confidence,
    affectedModules: ['风险控制', '审批管理', '执行管理', 'Agent 集群调度', '事故指挥'],
    timelineSteps: [
      {
        timeOffset: 'T+0s',
        description: '第 2 起事故触发风险收敛阈值',
        status: 'completed',
      },
      {
        timeOffset: 'T+2s',
        description: 'AI 自动启动风险锁定协议，冻结非关键审批路径',
        status: 'completed',
      },
      {
        timeOffset: 'T+5s',
        description: 'Agent 集群重新分配：研究优先 → 风险评估',
        status: 'completed',
      },
      {
        timeOffset: 'T+10s',
        description: '执行 Agent 停止新开仓操作，风控收紧敞口上限',
        status: 'in_progress',
      },
      {
        timeOffset: 'T+30s',
        description: '学习 Agent 生成根因分析报告，提交恢复策略',
        status: 'in_progress',
      },
    ],
  }
}

function buildAgentRecovery(confidence: number): ExecutiveScenario {
  return {
    scenarioId: 'agent_recovery',
    kind: 'agent_recovery',
    title: 'Agent 恢复模式 — AI 自愈网络已完成多 Agent 协同恢复',
    executiveSummary:
      '系统检测到 Agent 集群异常后自动触发自愈协议。AI 自愈网络已协调完成受影响 Agent 的隔离、' +
      '状态重建与恢复验证。业务连续性已恢复。',
    businessRisk:
      'Agent 异常可能影响部分决策链路完整性。系统在设计层面具备冗余 Agent 能力，' +
      '单 Agent 故障不会中断整体业务运转。恢复期间相关审批路径可能短暂延迟。',
    aiResponse:
      'AI 自愈网络执行以下恢复动作：1) 检测并隔离异常 Agent；' +
      '2) 备份 Agent 自动接管异常 Agent 的待处理任务；' +
      '3) 状态重建引擎从快照恢复 Agent 完整状态；' +
      '4) 恢复验证通过后重新接入协同网络。全流程自动完成。',
    expectedImpact:
      '恢复期间相关审批路径延迟增加约 1-2 秒，整体业务影响极小。' +
      '自愈成功率达到设计目标，系统弹性验证通过。',
    recommendedAction:
      '无需人工干预。AI 自愈网络已完成恢复。建议关注恢复后的 Agent 运行指标，' +
      '确认无残留异常后再恢复原审批策略。',
    severity: 'low',
    confidence,
    affectedModules: ['Agent 集群管理', '审批管理', '状态快照', '自愈引擎'],
    timelineSteps: [
      {
        timeOffset: 'T+0s',
        description: '监测系统发现 Agent 异常信号',
        status: 'completed',
      },
      {
        timeOffset: 'T+1s',
        description: '自愈引擎自动启动，隔离异常 Agent',
        status: 'completed',
      },
      {
        timeOffset: 'T+2s',
        description: '备份 Agent 接管待处理任务',
        status: 'completed',
      },
      {
        timeOffset: 'T+5s',
        description: '状态快照恢复与完整性校验',
        status: 'completed',
      },
      {
        timeOffset: 'T+8s',
        description: 'Agent 重新接入协同网络，恢复验证通过',
        status: 'completed',
      },
    ],
  }
}

function buildMarketCrash(confidence: number): ExecutiveScenario {
  return {
    scenarioId: 'market_crash',
    kind: 'market_crash',
    title: '极端市场环境 — AI 全面启动安全边界保护',
    executiveSummary:
      '市场出现极端波动，AI 系统已全面切换至安全边界保护模式。' +
      '所有交易策略进入保护性暂停，风险敞口已收缩至最低水平。多 Agent 协同网络专注于实时风险评估与恢复路径推演。',
    businessRisk:
      '极端市场环境可能导致：1) 流动性急剧下降，部分市场对无法正常交易；' +
      '2) 套利窗口快速变化，信号时效性大幅缩短；' +
      '3) 跨市场相关性急剧上升，组合分散化效果减弱。' +
      '如不采取保护措施，资产安全可能受到严重威胁。',
    aiResponse:
      '系统已执行最高级别保护：1) 所有自动交易策略暂停执行；' +
      '2) 风险敞口收缩至安全边界下限；' +
      '3) AI 预测模型切换至极端场景推演模式；' +
      '4) 实时计算恢复路径与回撤上限；' +
      '5) 学习 Agent 对比历史极端事件提供处置建议。',
    expectedImpact:
      '交易活动完全暂停，所有资源集中于资产保护与情景推演。' +
      '系统将在市场波动回归至可操作区间后自动评估恢复条件。',
    recommendedAction:
      '立即通知决策层。所有自动操作已暂停，等待市场稳定信号。' +
      '建议使用情景推演结果评估恢复时机，切勿在市场未稳定前手动恢复交易。',
    severity: 'critical',
    confidence,
    affectedModules: ['全部模块', '交易策略', '风险控制', '情景推演', '资产保护'],
    timelineSteps: [
      {
        timeOffset: 'T+0s',
        description: '极端波动触发最高级别保护协议',
        status: 'completed',
      },
      {
        timeOffset: 'T+1s',
        description: '所有交易策略进入保护性暂停',
        status: 'completed',
      },
      {
        timeOffset: 'T+3s',
        description: '风险敞口收缩至安全边界下限',
        status: 'completed',
      },
      {
        timeOffset: 'T+5s',
        description: 'AI 预测模型切换至极端场景推演模式',
        status: 'in_progress',
      },
      {
        timeOffset: '持续',
        description: '系统持续评估市场恢复条件，自动判断恢复时机',
        status: 'pending',
      },
    ],
  }
}

function buildLiquidityDrop(confidence: number): ExecutiveScenario {
  return {
    scenarioId: 'liquidity_drop',
    kind: 'liquidity_drop',
    title: '流动性下降 — AI 已调整策略安全边界',
    executiveSummary:
      '市场流动性出现显著下降，AI 系统已自动调整交易策略参数以保护执行质量。' +
      '信号审批阈值已上调，风控模块对流动性敏感指标进行增强监测。',
    businessRisk:
      '流动性下降可能导致：1) 大额交易滑点增加；2) 套利执行成本上升；' +
      '3) 部分市场对出现临时价差扩大；4) 策略收益预期下调。',
    aiResponse:
      'AI 协同网络已执行：1) 上调信号审批阈值 20%；' +
      '2) 缩小单笔交易规模上限；' +
      '3) 增加流动性监测频率至实时模式；' +
      '4) 暂停高滑点预期的市场对交易。',
    expectedImpact:
      '交易量下降约 25-35%，但可有效控制执行成本。' +
      '一旦流动性恢复至正常水平，系统将自动恢复原策略参数。',
    recommendedAction:
      '观察流动性恢复趋势，如 30 分钟内未恢复，可考虑进一步缩紧安全边界。' +
      '建议关注头部市场对的流动性深度变化。',
    severity: 'moderate',
    confidence,
    affectedModules: ['执行管理', '流动性监测', '信号审批', '风控策略'],
    timelineSteps: [
      {
        timeOffset: 'T+0s',
        description: '流动性监测发现多个市场对深度下降',
        status: 'completed',
      },
      {
        timeOffset: 'T+2s',
        description: 'AI 自动上调信号审批阈值',
        status: 'completed',
      },
      {
        timeOffset: 'T+5s',
        description: '缩小交易规模上限，暂停高滑点预期市场对',
        status: 'completed',
      },
      {
        timeOffset: 'T+10s',
        description: '流动性监测频率提升至实时模式',
        status: 'in_progress',
      },
      {
        timeOffset: '持续',
        description: '等待流动性恢复信号，自动恢复策略参数',
        status: 'pending',
      },
    ],
  }
}

// ── Primary Scenario Derivation ──────────────────────────────

export function derivePrimaryScenario(input: ScenarioDerivationInput): ExecutiveScenario {
  const { kpis, unresolvedIncidents, hasActiveRecovery, sseConnected } = input

  // Derive confidence from available data
  const confidence = sseConnected ? 92 : 68

  // 1. Critical: risk_lockdown — multiple active incidents
  if (unresolvedIncidents >= 2) {
    return buildRiskLockdown(unresolvedIncidents, confidence)
  }

  // 2. Critical: market_crash — extreme conditions
  const regime = kpis?.regime || ''
  const errorCount = kpis?.errorCount ?? 0
  const reconnects = kpis?.reconnects ?? 0
  if (regime === '极端波动' || errorCount > 8) {
    return buildMarketCrash(confidence)
  }

  // 3. High: high_volatility
  if (regime === '高波动' || errorCount > 2) {
    return buildHighVolatility(kpis, confidence)
  }

  // 4. Moderate: data_outage
  if (!sseConnected || reconnects > 0) {
    return buildDataOutage(confidence)
  }

  // 5. Low: agent_recovery
  if (hasActiveRecovery) {
    return buildAgentRecovery(confidence)
  }

  // 6. Moderate: liquidity_drop
  const totalSignals = kpis?.totalSignals ?? 0
  const approvedSignals = kpis?.approvedSignals ?? 0
  const approvalRate = totalSignals > 0 ? approvedSignals / totalSignals : 1
  if (totalSignals > 50 && approvalRate < 0.6) {
    return buildLiquidityDrop(confidence)
  }

  // 7. Default: normal_operations
  return buildNormalOperations(confidence)
}

// ── All Candidate Scenarios ─────────────────────────────────

export function deriveCandidateScenarios(input: ScenarioDerivationInput): ExecutiveScenario[] {
  const { kpis, unresolvedIncidents, hasActiveRecovery, sseConnected } = input

  const baseConfidence = sseConnected ? 92 : 68
  const regime = kpis?.regime || ''
  const errorCount = kpis?.errorCount ?? 0
  const reconnects = kpis?.reconnects ?? 0
  const totalSignals = kpis?.totalSignals ?? 0
  const approvedSignals = kpis?.approvedSignals ?? 0
  const approvalRate = totalSignals > 0 ? approvedSignals / totalSignals : 1

  const scenarios: ExecutiveScenario[] = []

  // Always include normal_operations
  scenarios.push(buildNormalOperations(baseConfidence))

  // Include matching scenarios
  if (regime === '高波动' || errorCount > 2) {
    scenarios.push(buildHighVolatility(kpis, baseConfidence - 2))
  }

  if (!sseConnected || reconnects > 0) {
    scenarios.push(buildDataOutage(baseConfidence - 2))
  }

  if (unresolvedIncidents >= 2) {
    scenarios.push(buildRiskLockdown(unresolvedIncidents, baseConfidence - 3))
  } else if (unresolvedIncidents >= 1) {
    scenarios.push(buildRiskLockdown(unresolvedIncidents, baseConfidence - 5))
  }

  if (hasActiveRecovery) {
    scenarios.push(buildAgentRecovery(baseConfidence - 1))
  }

  if (totalSignals > 50 && approvalRate < 0.6) {
    scenarios.push(buildLiquidityDrop(baseConfidence - 3))
  }

  if (regime === '极端波动' || errorCount > 8) {
    scenarios.push(buildMarketCrash(baseConfidence - 5))
  }

  return scenarios
}