import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { NextResponse } from 'next/server'

// Legacy API: retained during P3 while the dashboard converges on /api/visualization-state.
// ── Config ───────────────────────────────────────────────
const LOGS_DIR = '/Users/libo/.hermes/polymarket_arbitrage/logs'
const MAX_LOG_FILES = 6 // most recently modified
const MAX_LINES_PER_FILE = 500

// ── Agent definitions ───────────────────────────────────
const ALL_AGENTS = [
  { id: 'orchestrator', name: 'Orchestrator', keywords: ['orchestrat', 'cycle', 'dispatch', 'coordinar', '汇总', '调度', '周期'] },
  { id: 'news_scanner', name: 'News Scanner', keywords: ['news', 'scanner', '扫描', '资讯', 'reuters', 'bloomberg', 'coindesk'] },
  { id: 'market_analyzer', name: 'Market Analyzer', keywords: ['market', 'analyzer', '分析', 'orderbook', '订单簿', 'funding rate', '资金费率', 'liquidity', '流动性'] },
  { id: 'signal_generator', name: 'Signal Generator', keywords: ['signal', '生成信号', '合成', 'arbitrage', '套利', 'advantage', '优势', 'confidence', '置信'] },
  { id: 'regime_detector', name: 'Regime Detector', keywords: ['regime', 'detector', '状态', '波动率', 'volatility', 'VIX', 'correlation', '相关性', 'drawdown', '回撤'] },
  { id: 'agent_m', name: 'Agent M (Risk Reviewer)', keywords: ['agent_m', 'agent m', 'risk', '风控', '审核', '批准', 'approve', 'reject', 'stoploss', '止损'] },
  { id: 'capital_adapter', name: 'Capital Adapter', keywords: ['capital', '资金', '分配', 'allocation', 'position size', '头寸', 'coefficient', '系数'] },
  { id: 'executor', name: 'Executor (DryRun)', keywords: ['execut', '执行', 'dry run', 'dryrun', 'order', '订单', 'submit'] },
  { id: 'learner', name: 'Learning Engine', keywords: ['learn', '学习', 'model', '模型', 'weight', '权重', 'optimize', '优化'] },
]

// ── Activity pattern detection ──────────────────────────
interface PatternMatch {
  agentId: string
  status: 'running' | 'warning' | 'error'
  task: string
  success: boolean
}

function matchAgentFromLine(line: string): string | null {
  const lower = line.toLowerCase()
  let bestAgent: string | null = null
  let bestScore = 0

  for (const agent of ALL_AGENTS) {
    let score = 0
    for (const kw of agent.keywords) {
      if (lower.includes(kw.toLowerCase())) score++
    }
    if (score > bestScore) {
      bestScore = score
      bestAgent = agent.id
    }
  }

  return bestScore >= 2 ? bestAgent : null
}

function detectActivity(line: string): Omit<PatternMatch, 'agentId'> | null {
  const lower = line.toLowerCase()

  // ── Error patterns ─────────────────────────────────
  if (
    lower.includes('timeout') ||
    lower.includes('timed out') ||
    lower.includes('超时')
  ) {
    return {
      status: 'error',
      task: 'Timeout detected',
      success: false,
    }
  }

  if (
    lower.includes('exception') ||
    lower.includes('traceback') ||
    lower.includes('error') ||
    lower.includes('fail') ||
    lower.includes('失败') ||
    lower.includes('异常')
  ) {
    return {
      status: 'error',
      task: 'Error/exception detected',
      success: false,
    }
  }

  // ── Warning patterns ───────────────────────────────
  if (
    lower.includes('stoploss') ||
    lower.includes('drawdown') ||
    lower.includes('reconnect') ||
    lower.includes('retry') ||
    lower.includes('重试') ||
    lower.includes('回撤')
  ) {
    return {
      status: 'warning',
      task: 'Warning event detected',
      success: false,
    }
  }

  // ── Running patterns (successful activity) ─────────
  if (
    lower.includes('completed') ||
    lower.includes('success') ||
    lower.includes('processed') ||
    lower.includes('approved') ||
    lower.includes('signal') ||
    lower.includes('scanning') ||
    lower.includes('aggregation') ||
    lower.includes('完成') ||
    lower.includes('成功') ||
    lower.includes('批准')
  ) {
    return {
      status: 'running',
      task: 'Activity completed',
      success: true,
    }
  }

  if (
    lower.includes('started') ||
    lower.includes('processing') ||
    lower.includes('running') ||
    lower.includes('开始') ||
    lower.includes('处理中')
  ) {
    return {
      status: 'running',
      task: 'Activity in progress',
      success: true,
    }
  }

  // ── WS / connection events ─────────────────────────
  if (
    lower.includes('connected') ||
    lower.includes('disconnected') ||
    lower.includes('ws ') ||
    lower.includes('websocket')
  ) {
    return {
      status: 'running',
      task: 'Connection event',
      success: !lower.includes('disconnected'),
    }
  }

  return null
}

// ── Agent activity aggregation ─────────────────────────
interface AgentActivityState {
  status: 'idle' | 'running' | 'warning' | 'error'
  currentTask: string
  lastActiveAt: string | null
  signalsProcessed: number
  successCount: number
  failureCount: number
  totalLatencyMs: number
  activityCount: number
  recentEvent: string | null
}

export interface AgentRuntimeActivity {
  id: string
  name: string
  status: 'idle' | 'running' | 'warning' | 'error'
  currentTask: string
  lastActiveAt: string | null
  signalsProcessed: number
  successCount: number
  failureCount: number
  avgLatencyMs: number
  recentEvent: string | null
  throughput: number
}

// ── Main GET handler ───────────────────────────────────
export async function GET() {
  try {
    // ── Check if logs directory exists ────────────────
    if (!existsSync(LOGS_DIR)) {
      return NextResponse.json({
        source: 'fallback',
        updatedAt: new Date().toISOString(),
        agents: buildFallback(),
      })
    }

    // ── Get recently modified log files ───────────────
    const allFiles = readdirSync(LOGS_DIR)
      .filter((f) => f.endsWith('.log'))
      .map((f) => {
        const fullPath = join(LOGS_DIR, f)
        try {
          return { name: f, path: fullPath, mtime: statSync(fullPath).mtimeMs }
        } catch {
          return null
        }
      })
      .filter((f): f is NonNullable<typeof f> => f !== null)
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, MAX_LOG_FILES)

    if (allFiles.length === 0) {
      return NextResponse.json({
        source: 'fallback',
        updatedAt: new Date().toISOString(),
        agents: buildFallback(),
      })
    }

    // ── Initialize agent state map ────────────────────
    const agentMap = new Map<string, AgentActivityState>()
    for (const agent of ALL_AGENTS) {
      agentMap.set(agent.id, {
        status: 'idle',
        currentTask: 'Waiting for activity',
        lastActiveAt: null,
        signalsProcessed: 0,
        successCount: 0,
        failureCount: 0,
        totalLatencyMs: 0,
        activityCount: 0,
        recentEvent: null,
      })
    }

    // ── Parse log files ───────────────────────────────
    let totalLines = 0
    for (const file of allFiles) {
      try {
        const raw = readFileSync(file.path, 'utf-8')
        const lines = raw.split('\n').filter(Boolean)
        const tail = lines.slice(-MAX_LINES_PER_FILE)

        for (const line of tail) {
          totalLines++
          const agentId = matchAgentFromLine(line)
          if (!agentId) continue

          const activity = detectActivity(line)
          if (!activity) continue

          const state = agentMap.get(agentId)!
          state.activityCount++
          state.lastActiveAt = new Date().toISOString()
          state.recentEvent = line.slice(0, 200).trim()

          if (activity.success) {
            state.successCount++
            // Estimate latency from line if possible
            const latencyMatch = line.match(/(\d+(?:\.\d+)?)\s*(?:ms|milliseconds|秒)/)
            if (latencyMatch) {
              const ms = parseFloat(latencyMatch[1])
              state.totalLatencyMs += ms < 100 ? ms * 1000 : ms
            }
          } else {
            state.failureCount++
          }

          // Track signals
          if (
            line.toLowerCase().includes('signal') &&
            (line.toLowerCase().includes('generated') || line.toLowerCase().includes('approve') || line.toLowerCase().includes('生成') || line.toLowerCase().includes('批准'))
          ) {
            state.signalsProcessed++
          }

          // Update status (worst wins: error > warning > running > idle)
          const statusPriority: Record<string, number> = {
            error: 3,
            warning: 2,
            running: 1,
            idle: 0,
          }
          if (statusPriority[activity.status] > statusPriority[state.status]) {
            state.status = activity.status
          }

          // Update task description
          state.currentTask = activity.task
        }
      } catch {
        // Skip unreadable files
      }
    }

    // ── If no real activity found, return fallback ─────
    if (totalLines === 0) {
      return NextResponse.json({
        source: 'fallback',
        updatedAt: new Date().toISOString(),
        agents: buildFallback(),
      })
    }

    // ── Build response ────────────────────────────────
    const now = new Date().toISOString()
    const agents: AgentRuntimeActivity[] = ALL_AGENTS.map((agent) => {
      const state = agentMap.get(agent.id)!
      // If agent had no activity at all, mark as idle
      if (state.activityCount === 0) {
        return {
          id: agent.id,
          name: agent.name,
          status: 'idle',
          currentTask: 'No recent activity',
          lastActiveAt: null,
          signalsProcessed: 0,
          successCount: 0,
          failureCount: 0,
          avgLatencyMs: 0,
          recentEvent: null,
          throughput: 0,
        } satisfies AgentRuntimeActivity
      }

      return {
        id: agent.id,
        name: agent.name,
        status: state.status,
        currentTask: state.currentTask,
        lastActiveAt: state.lastActiveAt,
        signalsProcessed: state.signalsProcessed,
        successCount: state.successCount,
        failureCount: state.failureCount,
        avgLatencyMs:
          state.activityCount > 0
            ? Math.round(state.totalLatencyMs / state.activityCount)
            : 0,
        recentEvent: state.recentEvent,
        throughput: Math.round((state.activityCount / Math.max(allFiles.length, 1)) * 100) / 100,
      } satisfies AgentRuntimeActivity
    })

    return NextResponse.json({
      source: 'real',
      updatedAt: now,
      agents,
    })
  } catch {
    return NextResponse.json({
      source: 'fallback',
      updatedAt: new Date().toISOString(),
      agents: buildFallback(),
    })
  }
}

// ── Fallback data ──────────────────────────────────────
function buildFallback(): AgentRuntimeActivity[] {
  return ALL_AGENTS.map((agent) => ({
    id: agent.id,
    name: agent.name,
    status: 'idle' as const,
    currentTask: 'Waiting for log data...',
    lastActiveAt: null,
    signalsProcessed: 0,
    successCount: 0,
    failureCount: 0,
    avgLatencyMs: 0,
    recentEvent: null,
    throughput: 0,
  }))
}
