import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'
import path from 'path'

// Phase 5 (Web)：只读暴露 Agent B 研究假设（data/hypotheses.jsonl）。
const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const HYPOTHESES_FILE = path.join(DATA_DIR, 'hypotheses.jsonl')

interface Hypothesis {
  hypothesis_uid?: string
  signal_uid?: string
  canonical_market_id?: string
  market_name?: string
  direction?: string
  confidence?: number | null
  expected_edge?: number | null
  holding_horizon_days?: number | null
  thesis?: string
  risk_summary?: string
  failure_conditions?: string | string[]
  source?: 'derived' | 'agent_b'
  cycle_id?: string
}

interface HypothesesApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  summary: { total: number; agent_b: number; derived: number }
  hypotheses: Hypothesis[]
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

export async function GET(request: Request): Promise<NextResponse<HypothesesApiResponse>> {
  const url = new URL(request.url)
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? '50') || 50, 1), 500)

  try {
    if (!existsSync(HYPOTHESES_FILE)) {
      return NextResponse.json({
        source: 'fallback',
        updatedAt: new Date().toISOString(),
        summary: { total: 0, agent_b: 0, derived: 0 },
        hypotheses: [],
      })
    }
    const raw = await readFile(HYPOTHESES_FILE, 'utf-8')
    const all = parseJsonl<Hypothesis>(raw)
    const summary = {
      total: all.length,
      agent_b: all.filter((h) => h.source === 'agent_b').length,
      derived: all.filter((h) => h.source === 'derived').length,
    }
    const hypotheses = all.slice(-limit).reverse()
    return NextResponse.json({
      source: 'real',
      updatedAt: new Date().toISOString(),
      summary,
      hypotheses,
    })
  } catch (err) {
    console.error('[hypotheses API] read failed:', err)
    return NextResponse.json({
      source: 'fallback',
      updatedAt: new Date().toISOString(),
      summary: { total: 0, agent_b: 0, derived: 0 },
      hypotheses: [],
    })
  }
}
