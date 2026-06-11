import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'
import path from 'path'

// Legacy API: retained during P3 while the dashboard converges on /api/visualization-state.
// ── Constants ──────────────────────────────────────────
const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const SIGNALS_FILE = path.join(DATA_DIR, 'signals.json')
const REVIEW_FILE = path.join(DATA_DIR, 'review_results.json')
const EXECUTION_FILE = path.join(DATA_DIR, 'execution_results.json')

// ── Types ──────────────────────────────────────────────

interface RawSignal {
  market_id: string
  market_name?: string
  market?: string
  direction: 'YES' | 'NO'
  price: number
  position_size: number
  expected_value: number
  confidence: number
  source: string
  generated_at?: string
  timestamp?: string
}

interface ReviewResultSignal {
  market_id: string
  market_name?: string
  signal: RawSignal
  decision: string
  reason?: string
}

interface ReviewResults {
  timestamp?: string
  total?: number
  approved?: number
  rejected?: number
  approved_signals?: ReviewResultSignal[]
  rejected_signals?: ReviewResultSignal[]
}

interface ExecutionResultItem {
  status: 'dry_run' | 'success' | 'failed' | 'simulated'
  signal?: RawSignal
  timestamp?: string
}

interface ExecutionResults {
  timestamp?: string
  total?: number
  success?: number
  dry_run?: number
  simulated?: number
  failed?: number
  results?: ExecutionResultItem[]
}

type SignalDecision = 'APPROVE' | 'REJECT' | 'TIMEOUT' | 'PENDING'

interface SignalOutput {
  id: string
  market: string
  direction: 'LONG' | 'SHORT'
  decision: SignalDecision
  confidence: number
  price: number
  edge: number
  status: 'dry_run' | 'pending' | 'executed' | 'unknown'
  sourceAgent: string
  simulated: boolean
  timestamp: string
}

interface SignalsApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  queue: {
    total: number
    approved: number
    rejected: number
    pending: number
    timeout: number
  }
  signals: SignalOutput[]
}

// ── Helpers ────────────────────────────────────────────

function safeParse<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function normalizeDirection(dir: string): 'LONG' | 'SHORT' {
  const d = dir.toUpperCase()
  if (d === 'YES' || d === 'LONG') return 'LONG'
  return 'SHORT'
}

function getMarketName(s: RawSignal): string {
  return s.market_name || s.market || s.market_id || 'Unknown Market'
}

function buildSignalId(marketId: string, idx: number): string {
  return `sig-${marketId}-${idx}`
}

function normalizeEdge(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Number(value.toFixed(1))
    : 0
}

// ── Main Handler ───────────────────────────────────────

export async function GET(): Promise<NextResponse<SignalsApiResponse>> {
  try {
    // Read all source files
    const [signalsRaw, reviewRaw, executionRaw] = await Promise.all([
      readFileIfExists(SIGNALS_FILE),
      readFileIfExists(REVIEW_FILE),
      readFileIfExists(EXECUTION_FILE),
    ])

    const rawSignals: RawSignal[] = safeParse(signalsRaw, [])
    const reviewResults: ReviewResults = safeParse(reviewRaw, {})
    const executionResults: ExecutionResults = safeParse(executionRaw, {})

    // Build review decision map: market_id → decision
    const reviewMap = new Map<string, { decision: SignalDecision; reason?: string }>()
    const approvedSet = new Set<string>()
    const rejectedSet = new Set<string>()

    if (reviewResults.approved_signals) {
      for (const item of reviewResults.approved_signals) {
        const mid = item.market_id
        reviewMap.set(mid, { decision: 'APPROVE', reason: item.reason })
        approvedSet.add(mid)
      }
    }
    if (reviewResults.rejected_signals) {
      for (const item of reviewResults.rejected_signals) {
        const mid = item.market_id
        reviewMap.set(mid, { decision: 'REJECT', reason: item.reason })
        rejectedSet.add(mid)
      }
    }

    // Build execution status map: market_id → status
    const executionMap = new Map<string, string>()
    if (executionResults.results) {
      for (const item of executionResults.results) {
        if (item.signal?.market_id) {
          executionMap.set(item.signal.market_id, item.status)
        }
      }
    }

    // Merge signals with review + execution data
    const outputSignals: SignalOutput[] = rawSignals.map((s, idx) => {
      const mid = s.market_id
      const review = reviewMap.get(mid)
      const decision = review?.decision ?? 'PENDING'
      const execStatus = executionMap.get(mid) ?? 'pending'

      return {
        id: buildSignalId(mid, idx),
        market: getMarketName(s),
        direction: normalizeDirection(s.direction),
        decision,
        confidence: Math.round(s.confidence),
        price: s.price,
        edge: normalizeEdge(s.expected_value),
        status: execStatus as SignalOutput['status'],
        sourceAgent: s.source || 'unknown',
        simulated: execStatus === 'dry_run',
        timestamp: s.generated_at || s.timestamp || '',
      }
    })

    // Also add approved/rejected signals from review that might not be in signals.json
    const existingMarketIds = new Set(rawSignals.map((s) => s.market_id))

    // Add approved signals not in raw signals
    if (reviewResults.approved_signals) {
      reviewResults.approved_signals.forEach((item, idx) => {
        if (!existingMarketIds.has(item.market_id) && item.signal) {
          const s = item.signal
          const mid = item.market_id
          const execStatus = executionMap.get(mid) ?? 'pending'
          outputSignals.push({
            id: buildSignalId(mid, rawSignals.length + idx),
            market: getMarketName(s),
            direction: normalizeDirection(s.direction),
            decision: 'APPROVE',
            confidence: Math.round(s.confidence),
            price: s.price,
            edge: normalizeEdge(s.expected_value),
            status: execStatus as SignalOutput['status'],
            sourceAgent: s.source || 'unknown',
            simulated: execStatus === 'dry_run',
            timestamp: s.generated_at || s.timestamp || '',
          })
        }
      })
    }

    // Add rejected signals not in raw signals
    if (reviewResults.rejected_signals) {
      reviewResults.rejected_signals.forEach((item, idx) => {
        if (!existingMarketIds.has(item.market_id) && item.signal) {
          const s = item.signal
          const mid = item.market_id
          outputSignals.push({
            id: buildSignalId(mid, rawSignals.length + (reviewResults.approved_signals?.length ?? 0) + idx),
            market: getMarketName(s),
            direction: normalizeDirection(s.direction),
            decision: 'REJECT',
            confidence: Math.round(s.confidence),
            price: s.price,
            edge: normalizeEdge(s.expected_value),
            status: 'unknown',
            sourceAgent: s.source || 'unknown',
            simulated: false,
            timestamp: s.generated_at || s.timestamp || '',
          })
        }
      })
    }

    // Compute queue stats
    const total = outputSignals.length
    const approved = outputSignals.filter((s) => s.decision === 'APPROVE').length
    const rejected = outputSignals.filter((s) => s.decision === 'REJECT').length
    const pending = outputSignals.filter((s) => s.decision === 'PENDING').length
    const timeout = outputSignals.filter((s) => s.decision === 'TIMEOUT').length

    const updatedAt = reviewResults.timestamp || executionResults.timestamp || new Date().toISOString()

    return NextResponse.json({
      source: 'real',
      updatedAt,
      queue: { total, approved, rejected, pending, timeout },
      signals: outputSignals,
    })
  } catch (err) {
    // Fallback: return empty structure so UI doesn't crash
    console.error('[signals API] Failed to read signal data:', err)
    return NextResponse.json({
      source: 'fallback',
      updatedAt: new Date().toISOString(),
      queue: { total: 0, approved: 0, rejected: 0, pending: 0, timeout: 0 },
      signals: [],
    })
  }
}

async function readFileIfExists(filePath: string): Promise<string> {
  if (!existsSync(filePath)) {
    return ''
  }
  try {
    return await readFile(filePath, 'utf-8')
  } catch {
    return ''
  }
}
