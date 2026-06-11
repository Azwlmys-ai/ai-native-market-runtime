import { NextResponse } from 'next/server'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

// Legacy API: retained during P3 while the dashboard converges on /api/visualization-state.
// ── Types ────────────────────────────────────────────────

type LogLevel = 'INFO' | 'SUCCESS' | 'WARN' | 'ERROR'

interface LogEvent {
  id: string
  timestamp: string
  level: LogLevel
  category: string
  title: string
  detail: string
  agent: string
  agentId: string | null
  tags: string[]
}

interface RuntimeLogsResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  events: LogEvent[]
}

// ── Config ───────────────────────────────────────────────

const LOGS_DIR = '/Users/libo/.hermes/polymarket_arbitrage/logs'
const MAX_LINES_PER_FILE = 200 // Only read last N lines per file for performance
const MAX_FILES = 8 // Read at most N most recent files (captures monitor logs)
const MAX_EVENTS = 80 // Cap total events returned

// ── Helpers ──────────────────────────────────────────────

function readFileIfExists(path: string): string {
  try {
    return readFileSync(path, 'utf-8')
  } catch {
    return ''
  }
}

/** Get the most recently modified N .log files, sorted by mtime descending */
function getRecentLogFiles(dir: string, maxFiles: number): string[] {
  try {
    const entries = readdirSync(dir)
    const files = entries
      .filter((f) => f.endsWith('.log'))
      .map((f) => join(dir, f))
      .sort((a, b) => {
        try {
          return statSync(b).mtimeMs - statSync(a).mtimeMs
        } catch {
          return 0
        }
      })
    return files.slice(0, maxFiles)
  } catch {
    return []
  }
}

/** Parse timestamp from log line: [YYYY-MM-DD HH:MM:SS] */
function parseTimestamp(line: string): string | null {
  const m = line.match(/^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]/)
  if (!m) return null
  return m[1].replace(' ', 'T') + 'Z'
}

/** Extract agent name from [AgentName] bracket */
function parseAgent(line: string): string {
  // Match common agent patterns: [Agent X], [Agent xxx], [orchestrator], [agent_m], [Capital Adapter], etc.
  const m = line.match(/\[(Agent\s+\w+|Agent_\w+|agent_\w+|Orchestrator|Regime\s*\w*|Strategy\s*\w*|Capital\s*\w*|Monitor|us_stocks|regime_detector|strategy_manager|capital_adapter|okx_\w+|signal_generator|market_analyzer|news_scanner|agent_m|executor|learner|orchestrat\w*|C\d+)\]/i)
  if (!m) return 'system'
  return m[1]
}

/** Map parsed agent name to topology agent ID */
function mapAgentId(agentName: string): string | null {
  const lower = agentName.toLowerCase()
  if (lower.includes('orchestrat')) return 'orchestrator'
  if (lower.includes('news') || lower.includes('scanner')) return 'news_scanner'
  if (lower.includes('market') || lower.includes('analyzer')) return 'market_analyzer'
  if (lower.includes('signal') || lower.includes('generator')) return 'signal_generator'
  if (lower.includes('regime') || lower.includes('detector')) return 'regime_detector'
  if (lower.includes('agent_m') || lower.includes('agent m') || lower.includes('risk') || lower.includes('审批') || lower.includes('风控')) return 'agent_m'
  if (lower.includes('capital') || lower.includes('adapter')) return 'capital_adapter'
  if (lower.includes('execut')) return 'executor'
  if (lower.includes('learn') || lower.includes('model') || lower.includes('optimize')) return 'learner'
  return null
}

/** Get line priority: higher = more important */
function getLinePriority(line: string): number {
  const lower = line.toLowerCase()
  // Critical signals
  if (lower.includes('stoploss') || lower.includes('stop_loss')) return 100
  if (lower.includes('drawdown') && (lower.includes('threshold') || lower.includes('warning'))) return 95
  // Errors & timeouts
  if (/\berror\b/i.test(lower) || /\bfailed\b/i.test(lower)) return 90
  if (lower.includes('timeout')) return 85
  // Connection events
  if (lower.includes('reconnect') || lower.includes('connected') || lower.includes('disconnected')) return 80
  // Recovery
  if (lower.includes('recover')) return 75
  // Approve/reject
  if (/\bapprov/i.test(lower) || /\breject/i.test(lower)) return 70
  // High confidence
  if (lower.includes('high') && lower.includes('confid')) return 65
  if (lower.includes('高置信')) return 65
  // Cycle summary
  if (lower.includes('signals=') && lower.includes('approved=')) return 60
  // Signal summary
  if (lower.includes('汇总') || lower.includes('汇总')) return 55
  // Agent success
  if (line.includes('✅')) return 50
  // Warning
  if (lower.includes('warn')) return 40
  // Cycle start/monitor start
  if (lower.includes('cycle') && (lower.includes('start') || lower.includes('───'))) return 35
  if (lower.includes('monitor start')) return 34
  if (lower.includes('新的扫描周期')) return 33
  return 0
}

/** Classify a log line into a structured event, or null if not worth showing */
function classifyLine(raw: string): LogEvent | null {
  const line = raw.trim()
  if (!line) return null

  const priority = getLinePriority(line)
  if (priority < 30) return null // Skip low-value lines

  const ts = parseTimestamp(line)
  if (!ts) return null // Lines without timestamp aren't our structured format

  const agent = parseAgent(line)
  let level: LogLevel = 'INFO'
  let category = 'system'
  let title = ''
  const tags: string[] = []

  const lower = line.toLowerCase()

  // ── Error / Failure ──
  if (/\berror\b/i.test(lower) || /\bfailed\b/i.test(lower)) {
    level = lower.includes('recovered') || lower.includes('auto') ? 'WARN' : 'ERROR'
    category = 'error'
    if (lower.includes('timeout')) {
      title = 'Timeout Isolated'
      tags.push('timeout')
    } else if (lower.includes('reconnect')) {
      title = 'Auto Reconnect Attempt'
      tags.push('reconnect')
    } else {
      title = 'Error Detected'
    }
    tags.push('error')
  }
  // ── Stoploss ──
  else if (lower.includes('stoploss') || lower.includes('stop_loss')) {
    level = 'WARN'
    category = 'stoploss'
    title = 'Stoploss Protection Activated'
    tags.push('stoploss', 'risk')
  }
  // ── Drawdown ──
  else if (lower.includes('drawdown') && (lower.includes('threshold') || lower.includes('warning'))) {
    level = 'WARN'
    category = 'drawdown'
    title = 'Drawdown Threshold Warning'
    tags.push('drawdown', 'risk')
  }
  // ── Recovery ──
  else if (lower.includes('recover') || line.includes('恢复')) {
    level = 'SUCCESS'
    category = 'recovery'
    title = 'Recovery Completed'
    tags.push('recovery')
  }
  // ── Reconnect / Connection ──
  else if (lower.includes('reconnect')) {
    level = 'SUCCESS'
    category = 'connection'
    title = 'Auto Reconnect Success'
    tags.push('reconnect')
  } else if (lower.includes('connected')) {
    level = 'SUCCESS'
    category = 'connection'
    title = 'WS Connection Established'
    tags.push('connection')
  } else if (lower.includes('disconnected')) {
    level = 'WARN'
    category = 'connection'
    title = 'WS Connection Lost'
    tags.push('connection')
  }
  // ── Approve / Reject ──
  else if (/\bapprov/i.test(lower)) {
    level = 'SUCCESS'
    category = 'signal'
    title = 'Signal Approved'
    tags.push('approve')
  } else if (/\breject/i.test(lower)) {
    level = 'WARN'
    category = 'signal'
    title = 'Signal Rejected'
    tags.push('reject')
  }
  // ── High Confidence ──
  else if (lower.includes('high') && lower.includes('confid')) {
    level = 'SUCCESS'
    category = 'signal'
    title = 'High-Confidence Arbitrage Detected'
    tags.push('high_confidence')
  } else if (line.includes('高置信')) {
    level = 'SUCCESS'
    category = 'signal'
    title = 'High-Confidence Arbitrage Detected'
    tags.push('high_confidence')
  }
  // ── Cycle summary ──
  else if (lower.includes('signals=') && lower.includes('approved=')) {
    level = 'INFO'
    category = 'cycle'
    title = 'Cycle Summary'
    tags.push('cycle_summary')
    // Extract approval rate for detail
    const appMatch = line.match(/approved=(\d+)/)
    const rejMatch = line.match(/rejected=(\d+)/)
    const sigMatch = line.match(/signals=(\d+)/)
    if (sigMatch) {
      title = `Cycle: ${sigMatch[1]} signals, ${appMatch?.[1] ?? '?'} approved, ${rejMatch?.[1] ?? '?'} rejected`
    }
  }
  // ── Signal summary ──
  else if (line.includes('汇总') && line.includes('信号')) {
    level = 'SUCCESS'
    category = 'signal'
    title = 'New Signals Aggregated'
    tags.push('signal_aggregation')
    const nMatch = line.match(/(\d+)\s*个/)
    if (nMatch) {
      title = `${nMatch[1]} New Signals Aggregated`
    }
  }
  // ── Agent success ──
  else if (line.includes('✅')) {
    level = 'SUCCESS'
    category = 'task'
    title = 'Agent Task Completed'
    tags.push('success')
  }
  // ── Cycle DONE ──
  else if (lower.includes('cycle') && lower.includes('done')) {
    level = 'SUCCESS'
    category = 'cycle'
    title = 'Scan Cycle Completed'
    tags.push('cycle_done')
    const cnMatch = line.match(/Cycle\s+(\d+)\/(\d+)/)
    if (cnMatch) title = `Cycle ${cnMatch[1]}/${cnMatch[2]} Completed`
  }
  // ── Cycle start ──
  else if (lower.includes('扫描周期') || (lower.includes('cycle') && lower.includes('start='))) {
    level = 'INFO'
    category = 'cycle'
    title = 'Scan Cycle Started'
    tags.push('cycle_start')
  }
  // ── Monitor start ──
  else if (lower.includes('monitor start')) {
    level = 'INFO'
    category = 'system'
    title = 'Monitor Started'
    tags.push('monitor_start')
  }
  // ── Warning ──
  else if (lower.includes('warn')) {
    level = 'WARN'
    category = 'warning'
    title = 'Warning'
    tags.push('warning')
  }
  // ── Fallback (generic important line) ──
  else {
    level = 'INFO'
    category = 'info'
    title = line.length > 60 ? line.slice(0, 57) + '...' : line
  }

  // Clean up detail: remove timestamp + agent prefix, keep message body
  let detail = line
    .replace(/^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]\s*/, '')
    .replace(/^\[\w+\]\s*/, '')
    .trim()
  // Truncate long detail
  if (detail.length > 200) detail = detail.slice(0, 197) + '...'

  const id = `log-${ts}-${Math.random().toString(36).slice(2, 8)}`
  const agentId = mapAgentId(agent)

  return {
    id,
    timestamp: ts,
    level,
    category,
    title: title || 'Event',
    detail,
    agent,
    agentId,
    tags,
  }
}

// ── GET Handler ─────────────────────────────────────────

export async function GET(): Promise<NextResponse<RuntimeLogsResponse>> {
  try {
    const logFiles = getRecentLogFiles(LOGS_DIR, MAX_FILES)

    if (logFiles.length === 0) {
      return NextResponse.json({
        source: 'fallback',
        updatedAt: new Date().toISOString(),
        events: [],
      })
    }

    const allEvents: LogEvent[] = []

    for (const filePath of logFiles) {
      try {
        const raw = readFileIfExists(filePath)
        if (!raw) continue

        const lines = raw.split('\n')

        // Only process the most recent lines
        const tailLines = lines.slice(-MAX_LINES_PER_FILE)

        for (const line of tailLines) {
          const ev = classifyLine(line)
          if (ev) allEvents.push(ev)
        }
      } catch {
        // skip file on error
      }
    }

    // Sort by timestamp descending, deduplicate, limit
    allEvents.sort((a, b) => b.timestamp.localeCompare(a.timestamp))

    // Deduplicate identical events (same title + detail + timestamp second-granularity)
    const seen = new Set<string>()
    const unique = allEvents.filter((ev) => {
      const key = `${ev.timestamp.slice(0, 19)}|${ev.title}|${ev.detail}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })

    const capped = unique.slice(0, MAX_EVENTS)

    return NextResponse.json({
      source: 'real',
      updatedAt: new Date().toISOString(),
      events: capped,
    })
  } catch {
    return NextResponse.json({
      source: 'fallback',
      updatedAt: new Date().toISOString(),
      events: [],
    })
  }
}
