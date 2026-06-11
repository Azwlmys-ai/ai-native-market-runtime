import { NextResponse } from 'next/server'
import { existsSync } from 'fs'
import path from 'path'

// Canonical 持仓视图（VNext 里程碑尾巴 #4）：
// 直读 data/runtime.db 的 paper_positions 表（已按 canonical_market_id 去重，~22 行），
// 而非膨胀的裸 paper_portfolio.json（2000+ 条）。
// 与 dashboard 其余路由不同，本路由用 better-sqlite3 直读影子 DB（用户已确认选型）。
// DB 是「可重建旁路」，故任何缺失（模块未装 / 库不存在 / 表缺失）一律优雅 fallback，UI 不崩。
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const DB_PATH = path.join(DATA_DIR, 'runtime.db')

interface Position {
  position_uid: string
  canonical_market_id: string | null
  market_id: string | null
  market_slug: string | null
  market_name: string | null
  direction: string | null
  status: 'open' | 'closed' | string | null
  entry_price: number | null
  exit_price: number | null
  position_size: number | null
  notional_usd: number | null
  realized_pnl: number | null
  close_reason: string | null
  dry_run: number | null
  synthetic: number | null
  opened_at: string | null
  closed_at: string | null
  updated_at: string | null
}

interface PositionsSummary {
  total: number
  open: number
  closed: number
  openNotional: number
  realizedPnl: number
  dryRun: number
}

interface PositionsApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  summary: PositionsSummary
  positions: Position[]
  note?: string
}

const EMPTY_SUMMARY: PositionsSummary = {
  total: 0,
  open: 0,
  closed: 0,
  openNotional: 0,
  realizedPnl: 0,
  dryRun: 0,
}

function fallback(note: string): NextResponse<PositionsApiResponse> {
  return NextResponse.json({
    source: 'fallback',
    updatedAt: new Date().toISOString(),
    summary: EMPTY_SUMMARY,
    positions: [],
    note,
  })
}

function num(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

export async function GET(request: Request): Promise<NextResponse<PositionsApiResponse>> {
  const url = new URL(request.url)
  const statusFilter = url.searchParams.get('status') // 'open' | 'closed' | null
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? '500') || 500, 1), 5000)

  if (!existsSync(DB_PATH)) {
    return fallback('runtime.db 不存在（影子库未生成；PA_SHADOW_DB=1 跑一轮或 runtime.ingest 重建）')
  }

  let db: { prepare: (sql: string) => { all: (...a: unknown[]) => unknown[] }; close: () => void } | null = null
  try {
    const { default: Database } = await import('better-sqlite3')
    db = new Database(DB_PATH, { readonly: true, fileMustExist: true })

    const where =
      statusFilter === 'open' || statusFilter === 'closed' ? 'WHERE status = ?' : ''
    const params = where ? [statusFilter, limit] : [limit]
    const rows = db!
      .prepare(
        `SELECT position_uid, canonical_market_id, market_id, market_slug, market_name,
                direction, status, entry_price, exit_price, position_size, notional_usd,
                realized_pnl, close_reason, dry_run, synthetic, opened_at, closed_at, updated_at
         FROM paper_positions
         ${where}
         ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, datetime(opened_at) DESC
         LIMIT ?`,
      )
      .all(...params) as Position[]

    // summary 始终基于全量（不受 status 过滤影响），单独查一次
    const allForSummary =
      where === ''
        ? rows
        : (db!
            .prepare(
              `SELECT status, notional_usd, realized_pnl, dry_run FROM paper_positions`,
            )
            .all() as Pick<Position, 'status' | 'notional_usd' | 'realized_pnl' | 'dry_run'>[])

    const summary: PositionsSummary = {
      total: allForSummary.length,
      open: allForSummary.filter((p) => p.status === 'open').length,
      closed: allForSummary.filter((p) => p.status === 'closed').length,
      openNotional: allForSummary
        .filter((p) => p.status === 'open')
        .reduce((s, p) => s + num(p.notional_usd), 0),
      realizedPnl: allForSummary
        .filter((p) => p.status === 'closed')
        .reduce((s, p) => s + num(p.realized_pnl), 0),
      dryRun: allForSummary.filter((p) => num(p.dry_run) === 1).length,
    }

    return NextResponse.json({
      source: 'real',
      updatedAt: new Date().toISOString(),
      summary,
      positions: rows,
    })
  } catch (err) {
    console.error('[positions API] read failed:', err)
    return fallback(err instanceof Error ? err.message : 'read failed')
  } finally {
    try {
      db?.close()
    } catch {
      // ignore
    }
  }
}
