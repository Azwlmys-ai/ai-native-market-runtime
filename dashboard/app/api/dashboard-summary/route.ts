import { NextResponse } from 'next/server'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

// ── Types ────────────────────────────────────────────────

interface DashboardKpis {
  totalSignals: number
  approvedSignals: number
  rejectedSignals: number
  timeoutSignals: number
  activeAgents: number
  errorCount: number
  warningCount: number
  healthScore: number
  pnl: number
  reconnects: number
  runtimeStatus: 'ONLINE' | 'DEGRADED' | 'OFFLINE'
  regime: string
}

interface DashboardSummaryResponse {
  source: 'real' | 'mixed' | 'fallback'
  updatedAt: string
  kpis: DashboardKpis
}

type LogLevel = 'INFO' | 'SUCCESS' | 'WARN' | 'ERROR'

interface LogEvent {
  id: string
  timestamp: string
  level: LogLevel
  category: string
  tags: string[]
}

// ── Config ───────────────────────────────────────────────

const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const LOGS_DIR = '/Users/libo/.hermes/polymarket_arbitrage/logs'
const SIGNALS_FILE = join(DATA_DIR, 'signals.json')
const REVIEW_FILE = join(DATA_DIR, 'review_results.json')
const MAX_LINES_PER_FILE = 200
const MAX_FILES = 4
const MAX_EVENTS = 80

// ── Helpers ──────────────────────────────────────────────

function readFileIfExists(path: string): string {
  try {
    return readFileSync(path, 'utf-8')
  } catch {
    return ''
  }
}

function safeParse<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

interface RawSignal {
  market_id: string
  source?: string
}

interface ReviewResultSignal {
  market_id: string
  signal?: RawSignal
  decision?: string
  reason?: string
}

interface ReviewResults {
  approved_signals?: ReviewResultSignal[]
  rejected_signals?: ReviewResultSignal[]
}

// ── Signals parsing ──────────────────────────────────────

function getSignalCounts(): {
  total: number
  approved: number
  rejected: number
  timeout: number
} {
  try {
    const signalsRaw = readFileIfExists(SIGNALS_FILE)
    const reviewRaw = readFileIfExists(REVIEW_FILE)

    const rawSignals: RawSignal[] = safeParse(signalsRaw, [])
    const reviewResults: ReviewResults = safeParse(reviewRaw, {})

    const total = rawSignals.length
    const approved = reviewResults.approved_signals?.length ?? 0
    const rejected = reviewResults.rejected_signals?.length ?? 0
    const timeout = 0 // timeout is a runtime concept, not in static files

    return { total, approved, rejected, timeout }
  } catch {
    return { total: 0, approved: 0, rejected: 0, timeout: 0 }
  }
}

// ── Log parsing ──────────────────────────────────────────

function getRecentLogFiles(): string[] {
  try {
    const entries = readdirSync(LOGS_DIR)
    return entries
      .filter((f) => f.endsWith('.log'))
      .map((f) => join(LOGS_DIR, f))
      .sort((a, b) => {
        try {
          return statSync(b).mtimeMs - statSync(a).mtimeMs
        } catch {
          return 0
        }
      })
      .slice(0, MAX_FILES)
  } catch {
    return []
  }
}

function parseTimestamp(line: string): string | null {
  const m = line.match(/^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]/)
  if (!m) return null
  return m[1].replace(' ', 'T') + 'Z'
}

function classifyLine(line: string): LogEvent | null {
  const trimmed = line.trim()
  if (!trimmed) return null
  const lower = trimmed.toLowerCase()

  const ts = parseTimestamp(trimmed)
  if (!ts) return null

  let level: LogLevel = 'INFO'
  let category = 'info'
  const tags: string[] = []

  // Error classification
  if (/\berror\b/i.test(lower) || /\bfailed\b/i.test(lower)) {
    level = lower.includes('recovered') ? 'WARN' : 'ERROR'
    category = 'error'
    tags.push('error')
    if (lower.includes('timeout')) tags.push('timeout')
    if (lower.includes('reconnect')) tags.push('reconnect')
  } else if (lower.includes('stoploss') || lower.includes('stop_loss')) {
    level = 'WARN'
    category = 'stoploss'
    tags.push('stoploss', 'risk')
  } else if (lower.includes('drawdown') && (lower.includes('threshold') || lower.includes('warning'))) {
    level = 'WARN'
    category = 'drawdown'
    tags.push('drawdown', 'risk')
  } else if (lower.includes('recover') || trimmed.includes('恢复')) {
    level = 'SUCCESS'
    category = 'recovery'
    tags.push('recovery')
  } else if (lower.includes('reconnect')) {
    level = 'SUCCESS'
    category = 'connection'
    tags.push('reconnect')
  } else if (lower.includes('connected')) {
    level = 'SUCCESS'
    category = 'connection'
    tags.push('connection')
  } else if (lower.includes('disconnected')) {
    level = 'WARN'
    category = 'connection'
    tags.push('connection')
  } else if (lower.includes('warn') || lower.includes('警告') || lower.includes('风险')) {
    level = 'WARN'
    category = 'warning'
    tags.push('warning')
  } else if (trimmed.includes('✅')) {
    level = 'SUCCESS'
    category = 'task'
    tags.push('success')
  }

  return { id: `ev-${ts}`, timestamp: ts, level, category, tags }
}

function getLogStats(): {
  errorCount: number
  warningCount: number
  reconnects: number
  hasRecentEvents: boolean
} {
  try {
    const logFiles = getRecentLogFiles()
    if (logFiles.length === 0) {
      return { errorCount: 0, warningCount: 0, reconnects: 0, hasRecentEvents: false }
    }

    let errorCount = 0
    let warningCount = 0
    let reconnects = 0
    const allEvents: LogEvent[] = []

    for (const filePath of logFiles) {
      try {
        const raw = readFileIfExists(filePath)
        if (!raw) continue
        const lines = raw.split('\n').slice(-MAX_LINES_PER_FILE)
        for (const line of lines) {
          const ev = classifyLine(line)
          if (ev) allEvents.push(ev)
        }
      } catch {
        // skip file
      }
    }

    // Deduplicate + sort
    allEvents.sort((a, b) => b.timestamp.localeCompare(a.timestamp))
    const seen = new Set<string>()
    const unique = allEvents.filter((ev) => {
      const key = `${ev.timestamp.slice(0, 19)}|${ev.category}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })

    const capped = unique.slice(0, MAX_EVENTS)

    errorCount = capped.filter((e) => e.level === 'ERROR').length
    warningCount = capped.filter((e) => e.level === 'WARN').length
    reconnects = capped.filter((e) => e.tags.includes('reconnect')).length

    const hasRecentEvents = capped.length > 0

    return { errorCount, warningCount, reconnects, hasRecentEvents }
  } catch {
    return { errorCount: 0, warningCount: 0, reconnects: 0, hasRecentEvents: false }
  }
}

// ── Health score ─────────────────────────────────────────

function computeHealthScore(
  errorCount: number,
  warningCount: number,
  reconnects: number,
  timeoutSignals: number,
): number {
  let score = 100
  score -= errorCount * 3
  score -= warningCount * 1
  score -= reconnects * 2
  score -= timeoutSignals * 2
  return Math.max(0, Math.min(100, score))
}

// ── Regime detection (simple heuristic from log content) ─

const REGIME_PATTERNS: Array<{ pattern: RegExp; regime: string }> = [
  { pattern: /bear|下跌|crash|暴跌/i, regime: 'BEAR_HIGH_VOL' },
  { pattern: /bull|上涨|rally|反弹/i, regime: 'BULL_LOW_VOL' },
  { pattern: /sideway|横盘|range/i, regime: 'SIDEWAYS_HIGH_VOL' },
  { pattern: /trend|趋势|breakout|突破/i, regime: 'TRENDING_UP' },
  { pattern: /fomc|美联储|利率决议/i, regime: 'PRE_FOMC' },
]

function detectRegime(): string {
  try {
    const logFiles = getRecentLogFiles()
    for (const filePath of logFiles) {
      try {
        const raw = readFileIfExists(filePath)
        if (!raw) continue
        const tail = raw.split('\n').slice(-100).join('\n')
        for (const { pattern, regime } of REGIME_PATTERNS) {
          if (pattern.test(tail)) return regime
        }
      } catch {
        // skip
      }
    }
  } catch {
    // fall through
  }
  return 'SIDEWAYS_HIGH_VOL' // Default regime
}

// ── Runtime status ───────────────────────────────────────

function computeRuntimeStatus(
  hasRecentEvents: boolean,
  signalsTotal: number,
): 'ONLINE' | 'DEGRADED' | 'OFFLINE' {
  if (hasRecentEvents && signalsTotal > 0) return 'ONLINE'
  if (hasRecentEvents || signalsTotal > 0) return 'DEGRADED'
  return 'OFFLINE'
}

// ── GET Handler ──────────────────────────────────────────

export async function GET(): Promise<NextResponse<DashboardSummaryResponse>> {
  try {
    // 1. Signals
    const { total: totalSignals, approved, rejected, timeout } = getSignalCounts()

    // 2. Log stats
    const { errorCount, warningCount, reconnects, hasRecentEvents } = getLogStats()

    // 3. Derived KPIs
    const timeoutSignals = timeout
    const healthScore = computeHealthScore(errorCount, warningCount, reconnects, timeoutSignals)
    const regime = detectRegime()
    const runtimeStatus = computeRuntimeStatus(hasRecentEvents, totalSignals)

    // activeAgents: placeholder until real agent runtime is connected
    const activeAgents = 0

    return NextResponse.json({
      source: 'real',
      updatedAt: new Date().toISOString(),
      kpis: {
        totalSignals,
        approvedSignals: approved,
        rejectedSignals: rejected,
        timeoutSignals,
        activeAgents,
        errorCount,
        warningCount,
        healthScore,
        pnl: 0,
        reconnects,
        runtimeStatus,
        regime,
      },
    })
  } catch {
    return NextResponse.json({
      source: 'fallback',
      updatedAt: new Date().toISOString(),
      kpis: {
        totalSignals: 0,
        approvedSignals: 0,
        rejectedSignals: 0,
        timeoutSignals: 0,
        activeAgents: 0,
        errorCount: 0,
        warningCount: 0,
        healthScore: 0,
        pnl: 0,
        reconnects: 0,
        runtimeStatus: 'OFFLINE',
        regime: 'UNKNOWN',
      },
    })
  }
}