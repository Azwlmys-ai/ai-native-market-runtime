import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'
import path from 'path'

// Phase 5 (Web)：只读暴露 Agent M 三级 risk grading（data/review_results.json）。
const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const REVIEW_FILE = path.join(DATA_DIR, 'review_results.json')

interface RawSignal {
  market_id?: string
  market_name?: string
  market?: string
  direction?: string
  position_size?: number
  confidence?: number
  expected_value?: number
  grade?: string
}

interface ReviewItem {
  market_id?: string
  market_name?: string
  decision?: string
  reason?: string
  signal?: RawSignal
  review?: { failure_probability?: number; explanation?: string }
}

interface ReviewResults {
  timestamp?: string
  total?: number
  approved?: number
  paper_probe?: number
  rejected?: number
  approved_signals?: ReviewItem[]
  probe_signals?: ReviewItem[]
  rejected_signals?: ReviewItem[]
}

interface GradeRow {
  market_id: string
  market_name: string
  direction: string
  grade: 'approve' | 'paper_probe' | 'reject'
  failure_probability: number | null
  position_size: number | null
  explanation: string
}

interface RiskGradingApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  summary: { total: number; approve: number; paper_probe: number; reject: number }
  rows: GradeRow[]
}

function safeParse<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function toRows(items: ReviewItem[] | undefined, grade: GradeRow['grade']): GradeRow[] {
  if (!items) return []
  return items.map((it) => {
    const sig = it.signal ?? {}
    return {
      market_id: String(it.market_id ?? sig.market_id ?? ''),
      market_name: it.market_name ?? sig.market_name ?? sig.market ?? 'Unknown',
      direction: sig.direction ?? '',
      grade,
      failure_probability:
        typeof it.review?.failure_probability === 'number' ? it.review.failure_probability : null,
      position_size: typeof sig.position_size === 'number' ? sig.position_size : null,
      explanation: it.review?.explanation ?? it.reason ?? '',
    }
  })
}

export async function GET(): Promise<NextResponse<RiskGradingApiResponse>> {
  try {
    if (!existsSync(REVIEW_FILE)) {
      return NextResponse.json({
        source: 'fallback',
        updatedAt: new Date().toISOString(),
        summary: { total: 0, approve: 0, paper_probe: 0, reject: 0 },
        rows: [],
      })
    }
    const raw = await readFile(REVIEW_FILE, 'utf-8')
    const rr = safeParse<ReviewResults>(raw, {})
    const rows: GradeRow[] = [
      ...toRows(rr.approved_signals, 'approve'),
      ...toRows(rr.probe_signals, 'paper_probe'),
      ...toRows(rr.rejected_signals, 'reject'),
    ]
    const summary = {
      total: rr.total ?? rows.length,
      approve: rr.approved ?? rows.filter((r) => r.grade === 'approve').length,
      paper_probe: rr.paper_probe ?? rows.filter((r) => r.grade === 'paper_probe').length,
      reject: rr.rejected ?? rows.filter((r) => r.grade === 'reject').length,
    }
    return NextResponse.json({
      source: 'real',
      updatedAt: rr.timestamp ?? new Date().toISOString(),
      summary,
      rows,
    })
  } catch (err) {
    console.error('[risk-grading API] read failed:', err)
    return NextResponse.json({
      source: 'fallback',
      updatedAt: new Date().toISOString(),
      summary: { total: 0, approve: 0, paper_probe: 0, reject: 0 },
      rows: [],
    })
  }
}
