import { readFile } from 'node:fs/promises'
import { NextResponse } from 'next/server'

const VISUALIZATION_STATE_FILE =
  '/Users/libo/.hermes/polymarket_arbitrage/data/visualization_state.json'

interface VisualizationStateResponse {
  ok: boolean
  source: 'visualization_state'
  updatedAt: string | null
  state: Record<string, unknown>
}

function getUpdatedAt(state: Record<string, unknown>): string | null {
  const timestamp = state.timestamp
  return typeof timestamp === 'string' && timestamp.length > 0 ? timestamp : null
}

export async function GET(): Promise<NextResponse<VisualizationStateResponse>> {
  try {
    const raw = await readFile(VISUALIZATION_STATE_FILE, 'utf-8')
    const parsed = JSON.parse(raw)
    const state = parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {}

    return NextResponse.json({
      ok: true,
      source: 'visualization_state',
      updatedAt: getUpdatedAt(state),
      state,
    })
  } catch {
    return NextResponse.json({
      ok: false,
      source: 'visualization_state',
      updatedAt: null,
      state: {},
    }, { status: 200 })
  }
}
