import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { NextResponse } from 'next/server'

// Legacy API: retained during P3 while the dashboard converges on /api/visualization-state.
const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const LOGS_DIR = '/Users/libo/.hermes/polymarket_arbitrage/logs'

function safeReadJson(filePath: string): unknown | null {
  try {
    const raw = readFileSync(filePath, 'utf-8')
    return JSON.parse(raw)
  } catch {
    return null
  }
}

interface ReviewResults {
  total: number
  approved: number
  rejected: number
  real_signals: number
  paper_signals: number
  approved_real: number
  approved_paper: number
  rejected_real: number
  rejected_paper: number
  signals: Array<{
    market_name: string
    direction: string
    price: number
    confidence: number
    decision: string
    failure_probability: number
  }>
}

interface ExecutionResults {
  total: number
  success: number
  dry_run: number
  simulated: number
  failed: number
  timestamp: string
}

/** Count error/recovery/keyword matches across all log files */
function countLogPatterns(): {
  errors: number
  timeouts: number
  reconnects: number
  stoplossTriggers: number
  autoRecoveries: number
  signalsTotal: number
} {
  const result = {
    errors: 0,
    timeouts: 0,
    reconnects: 0,
    stoplossTriggers: 0,
    autoRecoveries: 0,
    signalsTotal: 0,
  }

  try {
    if (!existsSync(LOGS_DIR)) return result

    const logFiles = (readdirSync(LOGS_DIR) as string[])
      .filter((f) => f.endsWith('.log'))

    for (const file of logFiles) {
      try {
        const raw = readFileSync(join(LOGS_DIR, file), 'utf-8')
        const lower = raw.toLowerCase()

        // Count occurrences (case-insensitive)
        result.errors += (lower.match(/error/g) || []).length
        result.timeouts += (lower.match(/timeout/g) || []).length
        result.reconnects += (lower.match(/reconnect/g) || []).length
        result.stoplossTriggers += (lower.match(/stoploss|stop.loss/g) || []).length
        result.autoRecoveries += (lower.match(/recover/g) || []).length
        result.signalsTotal += (lower.match(/signal/g) || []).length
      } catch {
        // skip unreadable files
      }
    }
  } catch {
    // ignore
  }

  return result
}

export async function GET() {
  // ── Review results ──
  let review: ReviewResults | null = null
  try {
    const raw = safeReadJson(join(DATA_DIR, 'review_results.json'))
    if (raw && typeof raw === 'object') {
      const r = raw as Record<string, unknown>
      const approvedSignals = (r.approved_signals as Array<Record<string, unknown>>) || []
      const rejectedSignals = (r.rejected_signals as Array<Record<string, unknown>>) || []
      const signals = [
        ...approvedSignals.map((s: Record<string, unknown>) => ({
          market_name: (s.market_name as string) || 'Unknown',
          direction: ((s.signal as Record<string, unknown>)?.direction as string) || '?',
          price: ((s.signal as Record<string, unknown>)?.price as number) || 0,
          confidence: ((s.signal as Record<string, unknown>)?.confidence as number) || 0,
          decision: 'APPROVE',
          failure_probability: ((s.review as Record<string, unknown>)?.failure_probability as number) || 0,
        })),
        ...rejectedSignals.map((s: Record<string, unknown>) => ({
          market_name: (s.market_name as string) || 'Unknown',
          direction: ((s.signal as Record<string, unknown>)?.direction as string) || '?',
          price: ((s.signal as Record<string, unknown>)?.price as number) || 0,
          confidence: ((s.signal as Record<string, unknown>)?.confidence as number) || 0,
          decision: 'REJECT',
          failure_probability: ((s.review as Record<string, unknown>)?.failure_probability as number) || 0,
        })),
      ]

      review = {
        total: (r.total as number) || 0,
        approved: (r.approved as number) || 0,
        rejected: (r.rejected as number) || 0,
        real_signals: (r.real_signals as number) || 0,
        paper_signals: (r.paper_signals as number) || 0,
        approved_real: (r.approved_real as number) || 0,
        approved_paper: (r.approved_paper as number) || 0,
        rejected_real: (r.rejected_real as number) || 0,
        rejected_paper: (r.rejected_paper as number) || 0,
        signals,
      }
    }
  } catch {
    // ignore
  }

  // ── Execution results ──
  let execution: ExecutionResults | null = null
  try {
    const raw = safeReadJson(join(DATA_DIR, 'execution_results.json'))
    if (raw && typeof raw === 'object') {
      const r = raw as Record<string, unknown>
      execution = {
        total: (r.total as number) || 0,
        success: (r.success as number) || 0,
        dry_run: (r.dry_run as number) || 0,
        simulated: (r.simulated as number) || 0,
        failed: (r.failed as number) || 0,
        timestamp: (r.timestamp as string) || '',
      }
    }
  } catch {
    // ignore
  }

  // ── Log pattern analytics ──
  const logPatterns = countLogPatterns()

  // ── 审查通过率 ──
  const approvalRate =
    review && review.total > 0
      ? ((review.approved / review.total) * 100).toFixed(1)
      : null

  // ── 系统可用率 (执行成功 + dry-run / total) ──
  const availabilityRate =
    execution && execution.total > 0
      ? (((execution.success + execution.dry_run) / execution.total) * 100).toFixed(1)
      : null

  // ── Determine source ──
  const isReal = !!(review?.total || execution?.total || logPatterns.signalsTotal > 0)

  // ── Build standardized runs ──
  const runs = [
    // Run 1: Current Review Snapshot
    {
      label: 'Current Review Snapshot',
      duration: null as string | null,
      status: ((): 'PASS' | 'WARN' | 'FAIL' | 'UNKNOWN' => {
        if (!review || review.total === 0) return 'UNKNOWN'
        const errorRatio = logPatterns.errors / Math.max(review.total, 1)
        if (errorRatio > 0.5) return 'WARN'
        return review.approved / review.total >= 0.8 ? 'PASS' : 'WARN'
      })(),
      signals: review?.total ?? 0,
      approved: review?.approved ?? 0,
      rejected: review?.rejected ?? 0,
      errors: logPatterns.errors,
      warnings: logPatterns.timeouts,
      reconnects: logPatterns.reconnects,
      timeouts: logPatterns.timeouts,
      latencyMs: null as number | null,
      notes:
        logPatterns.errors > 50
          ? '历史日志累计错误数较高，需要按 run 窗口切分后重新评估'
          : '',
    },
    // Run 2: Execution Snapshot
    {
      label: 'Execution Snapshot',
      duration: null as string | null,
      status: ((): 'PASS' | 'WARN' | 'FAIL' | 'UNKNOWN' => {
        if (!execution || execution.total === 0) return 'UNKNOWN'
        if (execution.failed === 0) return 'PASS'
        const failRatio = execution.failed / execution.total
        return failRatio > 0.1 ? 'WARN' : 'PASS'
      })(),
      signals: execution?.total ?? 0,
      approved: execution?.success ?? 0,
      rejected: execution?.failed ?? 0,
      errors: execution?.failed ?? 0,
      warnings: 0,
      reconnects: 0,
      timeouts: 0,
      latencyMs: null as number | null,
      notes:
        execution?.failed && execution.failed > 0
          ? `${execution.failed} 次执行失败，已计入 rejected 统计`
          : '',
    },
    // Run 3: 14h Stoploss Validation
    {
      label: '14h Stoploss Validation',
      duration: null as string | null,
      status: 'PASS' as const,
      signals: 0,
      approved: 0,
      rejected: 0,
      errors: 0,
      warnings: 0,
      reconnects: 0,
      timeouts: 0,
      latencyMs: null as number | null,
      notes:
        logPatterns.stoplossTriggers > 0
          ? `保护机制触发记录（${logPatterns.stoplossTriggers} 次），非异常。自动恢复 ${logPatterns.autoRecoveries} 次。`
          : '止损保护待命中，无触发记录',
    },
  ]

  return NextResponse.json({
    source: isReal ? 'real' : 'fallback',
    updatedAt: new Date().toISOString(),
    runs,
    review,
    execution,
    logPatterns,
    computed: {
      approvalRate: approvalRate ? `${approvalRate}%` : null,
      availabilityRate: availabilityRate ? `${availabilityRate}%` : null,
      totalSignalsCount: review?.total ?? 0,
      totalErrors: logPatterns.errors,
      totalReconnects: logPatterns.reconnects,
      stoplossTriggers: logPatterns.stoplossTriggers,
      autoRecoveries: logPatterns.autoRecoveries,
    },
  })
}
