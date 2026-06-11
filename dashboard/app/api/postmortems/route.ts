import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'
import path from 'path'

// Phase 5 (Web)：只读暴露 Agent G 逐笔复盘（data/postmortems.jsonl）。
// 与现有 dashboard 一致：Next.js 路由只读 JSON，Python 侧才写。
const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const POSTMORTEMS_FILE = path.join(DATA_DIR, 'postmortems.jsonl')

interface Postmortem {
  postmortem_uid?: string
  canonical_market_id?: string
  market_name?: string
  direction?: string
  signal_uid?: string
  hypothesis?: string
  expected_edge?: number | null
  confidence?: number | null
  realized_pnl?: number | null
  outcome?: 'win' | 'loss' | 'flat'
  failure_reason?: string
  liquidity_issue?: boolean
  timing_issue?: boolean
  model_issue?: boolean
  // Phase 3c-2：失败条件对照
  hypothesis_verdict?: 'confirmed' | 'refuted' | 'loss_unexplained' | 'no_prediction' | 'inconclusive'
  hypothesis_source?: string
  failure_conditions_review?: {
    predicted?: string[]
    had_predicted_conditions?: boolean
    materialized_count?: number
    verdict?: string
    items?: { condition: string; category: string; occurred: boolean | null; basis: string }[]
  }
  source?: string
  closed_at?: string
}

interface PostmortemsApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  summary: { total: number; win: number; loss: number; flat: number; verdicts: Record<string, number> }
  postmortems: Postmortem[]
}

function parseJsonl<T>(raw: string): T[] {
  const out: T[] = []
  for (const line of raw.split('\n')) {
    const t = line.trim()
    if (!t) continue
    try {
      out.push(JSON.parse(t) as T)
    } catch {
      // skip malformed line
    }
  }
  return out
}

export async function GET(request: Request): Promise<NextResponse<PostmortemsApiResponse>> {
  const url = new URL(request.url)
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? '50') || 50, 1), 500)

  try {
    if (!existsSync(POSTMORTEMS_FILE)) {
      return NextResponse.json({
        source: 'fallback',
        updatedAt: new Date().toISOString(),
        summary: { total: 0, win: 0, loss: 0, flat: 0, verdicts: {} },
        postmortems: [],
      })
    }
    const raw = await readFile(POSTMORTEMS_FILE, 'utf-8')
    const all = parseJsonl<Postmortem>(raw)
    const verdicts: Record<string, number> = {}
    for (const p of all) {
      const v = p.hypothesis_verdict
      if (v) verdicts[v] = (verdicts[v] ?? 0) + 1
    }
    const summary = {
      total: all.length,
      win: all.filter((p) => p.outcome === 'win').length,
      loss: all.filter((p) => p.outcome === 'loss').length,
      flat: all.filter((p) => p.outcome === 'flat').length,
      verdicts,
    }
    // 最近优先
    const postmortems = all.slice(-limit).reverse()
    return NextResponse.json({
      source: 'real',
      updatedAt: new Date().toISOString(),
      summary,
      postmortems,
    })
  } catch (err) {
    console.error('[postmortems API] read failed:', err)
    return NextResponse.json({
      source: 'fallback',
      updatedAt: new Date().toISOString(),
      summary: { total: 0, win: 0, loss: 0, flat: 0, verdicts: {} },
      postmortems: [],
    })
  }
}
