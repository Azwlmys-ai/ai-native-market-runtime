import { readFile } from 'node:fs/promises'
import { readdir } from 'node:fs/promises'
import { join } from 'node:path'

const LOGS_DIR = '/Users/libo/.hermes/polymarket_arbitrage/logs'

// ── Log parser → RuntimeEvent[] ──

interface ParsedLine {
  ts: string
  source: 'orchestrator' | 'agent_b' | 'agent_m' | 'risk' | 'execution'
  type: 'signal_created' | 'review_started' | 'dry_run_executed' | 'warning' | 'error'
  message: string
}

function parseLogLine(line: string): ParsedLine | null {
  // Format: [2026-05-14 12:18:05] [Orchestrator] ✅ agent_b 执行成功
  const match = line.match(
    /^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+\[(\w+)\]\s+(.*)$/,
  )
  if (!match) return null

  const [, ts, rawSource, rawMsg] = match

  // Map source
  let source: ParsedLine['source'] = 'orchestrator'
  if (/agent_b/i.test(rawSource)) source = 'agent_b'
  else if (/agent_m/i.test(rawSource)) source = 'agent_m'
  else if (/risk|agent_p/i.test(rawSource)) source = 'risk'
  else if (/execution|执行|卖出|买入/i.test(rawSource)) source = 'execution'

  // Determine type
  let type: ParsedLine['type'] = 'signal_created'

  if (/✅|成功|执行成功|完成/i.test(rawMsg)) {
    type = 'dry_run_executed'
  } else if (/❌|失败|错误|异常|timeout/i.test(rawMsg)) {
    type = 'error'
  } else if (/⚠|警告|风险|拒绝/i.test(rawMsg)) {
    type = 'warning'
  } else if (/信号|signal|买入|sell/i.test(rawMsg)) {
    type = 'signal_created'
  } else if (/审查|review|agent_m/i.test(rawMsg)) {
    type = 'review_started'
  }

  return { ts, source, type, message: rawMsg }
}

async function getLatestLogPath(): Promise<string | null> {
  try {
    const files = await readdir(LOGS_DIR)
    const orchestratorLogs = files
      .filter((f) => f.startsWith('orchestrator_') && f.endsWith('.log'))
      .sort()
      .reverse()
    if (orchestratorLogs.length === 0) return null
    return join(LOGS_DIR, orchestratorLogs[0])
  } catch {
    return null
  }
}

async function readLatestEvents(lastKnownTimestamp: string): Promise<{
  events: ParsedLine[]
  latestTs: string
}> {
  const logPath = await getLatestLogPath()
  if (!logPath) return { events: [], latestTs: lastKnownTimestamp }

  try {
    const raw = await readFile(logPath, 'utf-8')
    const lines = raw.split('\n').filter(Boolean)

    // Find lines newer than lastKnownTimestamp
    const newLines = lines.filter((line) => {
      const match = line.match(/^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]/)
      if (!match) return false
      return match[1] > lastKnownTimestamp
    })

    const events = newLines.map(parseLogLine).filter(Boolean) as ParsedLine[]

    // Determine latest timestamp
    let latestTs = lastKnownTimestamp
    for (const ev of events) {
      if (ev.ts > latestTs) latestTs = ev.ts
    }

    return { events, latestTs }
  } catch {
    return { events: [], latestTs: lastKnownTimestamp }
  }
}

// ── SSE streaming endpoint ──

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

  export async function GET(): Promise<Response> {
    let lastTs = '1970-01-01 00:00:00'

    const stream = new ReadableStream({
      async start(controller) {
        const encoder = new TextEncoder()
        let closed = false

        const push = (data: string) => {
          if (closed) return
          try {
            controller.enqueue(encoder.encode(data))
          } catch {
            // Controller already closed — stop all pushes
            closed = true
            clearInterval(interval)
          }
        }

        // Send initial keepalive
        push(':ok\n\n')

        // Poll every 2 seconds
        const interval = setInterval(async () => {
          if (closed) return

          try {
            const { events, latestTs } = await readLatestEvents(lastTs)

            if (events.length > 0) {
              lastTs = latestTs

              // Build SSE data block with all new events
              const payload = JSON.stringify(events)
              push(`data: ${payload}\n\n`)
              push(':keepalive\n\n')
            } else {
              // Send heartbeat comment to keep connection alive
              push(':heartbeat\n\n')
            }
          } catch {
            // Silently ignore errors — don't crash the stream
            push(':heartbeat\n\n')
          }
        }, 2000)

        // Cleanup on abort
        const cleanup = () => {
          closed = true
          clearInterval(interval)
          try {
            controller.close()
          } catch {
            // already closed
          }
        }

        return cleanup
      },
    })

    return new Response(stream, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    })
  }
