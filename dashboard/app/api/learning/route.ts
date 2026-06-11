import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'
import path from 'path'

// Phase 3e–3i (Web)：只读暴露 Learning Runtime 研究/学习产物。
// 与现有 dashboard 一致：Next.js 路由只读 JSON 事实源，Python 侧才写。
// 产物：model_effectiveness / rule_effectiveness / correlation_signals /
//       regime_states / volatility_states / sizing_suggestions
const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'

async function readJson<T>(file: string): Promise<T | null> {
  const p = path.join(DATA_DIR, file)
  if (!existsSync(p)) return null
  try {
    return JSON.parse(await readFile(p, 'utf-8')) as T
  } catch {
    return null
  }
}

interface EffEntry {
  key?: string
  n_trades?: number
  n_win?: number
  win_rate?: number | null
  total_realized_pnl?: number | null
  effectiveness?: string
}
interface RuleWeightEntry {
  key?: string
  effectiveness?: string
  weight?: number
  recommendation?: string
}
interface CorrelationCandidate {
  source_markets?: string[]
  pair_type?: string
  anchor_asset?: string | null
  confidence?: number
  data_sufficiency?: string
  tier?: string
  evidence?: { zscore?: number; corr?: number; half_life?: number | null }
}
interface RegimeEntry {
  series_id?: string
  series_kind?: string | null
  current_regime?: string
  regime_shift?: boolean
  news_driven?: boolean
  regime_confident?: boolean
  confidence?: number
}
interface VolatilityEntry {
  series_id?: string
  risk_state?: string
  clustering?: boolean
  vol_spike?: boolean
  confidence?: number
}
interface SizingEntry {
  market_id?: string
  sized_fraction?: number
  kelly_fraction?: number
  markowitz_weight?: number
}

export interface LearningApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  modelEffectiveness: {
    present: boolean
    generatedAt?: string
    nPostmortems?: number
    byModel: EffEntry[]
  }
  ruleWeights: {
    present: boolean
    enforced?: boolean
    nRules?: number
    retireCandidates: string[]
    downWeighted: string[]
    entries: RuleWeightEntry[]
  }
  cointegration: {
    present: boolean
    enforced?: boolean
    nCandidates?: number
    nPmPm?: number
    nPmAsset?: number
    candidates: CorrelationCandidate[]
  }
  regimes: {
    present: boolean
    nRegimes?: number
    nTurbulent?: number
    nShift?: number
    entries: RegimeEntry[]
  }
  volatility: {
    present: boolean
    nStates?: number
    nElevated?: number
    nClustering?: number
    entries: VolatilityEntry[]
  }
  sizing: {
    present: boolean
    enforced?: boolean
    nSuggestions?: number
    entries: SizingEntry[]
  }
}

export async function GET(): Promise<NextResponse<LearningApiResponse>> {
  const TOP = 12
  const fallback: LearningApiResponse = {
    source: 'fallback',
    updatedAt: new Date().toISOString(),
    modelEffectiveness: { present: false, byModel: [] },
    ruleWeights: { present: false, retireCandidates: [], downWeighted: [], entries: [] },
    cointegration: { present: false, candidates: [] },
    regimes: { present: false, entries: [] },
    volatility: { present: false, entries: [] },
    sizing: { present: false, entries: [] },
  }

  try {
    const [me, rw, co, rg, vo, sz] = await Promise.all([
      readJson<{ generated_at?: string; n_postmortems?: number; by_model?: EffEntry[] }>('model_effectiveness.json'),
      readJson<{ enforced?: boolean; by_rule?: RuleWeightEntry[]; summary?: { n_rules?: number; retire_candidates?: string[]; down_weighted?: string[] } }>('rule_effectiveness.json'),
      readJson<{ enforced?: boolean; n_candidates?: number; n_candidates_pm_pm?: number; n_candidates_pm_asset?: number; candidates?: CorrelationCandidate[] }>('correlation_signals.json'),
      readJson<{ n_regimes?: number; n_turbulent?: number; n_regime_shift?: number; regimes?: RegimeEntry[] }>('regime_states.json'),
      readJson<{ n_states?: number; n_elevated?: number; n_clustering?: number; states?: VolatilityEntry[] }>('volatility_states.json'),
      readJson<{ enforced?: boolean; n_suggestions?: number; suggestions?: SizingEntry[] }>('sizing_suggestions.json'),
    ])

    const res: LearningApiResponse = {
      source: 'real',
      updatedAt: new Date().toISOString(),
      modelEffectiveness: {
        present: !!me,
        generatedAt: me?.generated_at,
        nPostmortems: me?.n_postmortems,
        byModel: (me?.by_model ?? []).slice(0, TOP),
      },
      ruleWeights: {
        present: !!rw,
        enforced: rw?.enforced,
        nRules: rw?.summary?.n_rules,
        retireCandidates: rw?.summary?.retire_candidates ?? [],
        downWeighted: rw?.summary?.down_weighted ?? [],
        entries: (rw?.by_rule ?? []).slice(0, TOP),
      },
      cointegration: {
        present: !!co,
        enforced: co?.enforced,
        nCandidates: co?.n_candidates,
        nPmPm: co?.n_candidates_pm_pm,
        nPmAsset: co?.n_candidates_pm_asset,
        candidates: (co?.candidates ?? []).slice(0, TOP),
      },
      regimes: {
        present: !!rg,
        nRegimes: rg?.n_regimes,
        nTurbulent: rg?.n_turbulent,
        nShift: rg?.n_regime_shift,
        entries: (rg?.regimes ?? []).slice(0, TOP),
      },
      volatility: {
        present: !!vo,
        nStates: vo?.n_states,
        nElevated: vo?.n_elevated,
        nClustering: vo?.n_clustering,
        entries: (vo?.states ?? []).slice(0, TOP),
      },
      sizing: {
        present: !!sz,
        enforced: sz?.enforced,
        nSuggestions: sz?.n_suggestions,
        entries: (sz?.suggestions ?? []).slice(0, TOP),
      },
    }
    return NextResponse.json(res)
  } catch (err) {
    console.error('[learning API] read failed:', err)
    return NextResponse.json(fallback)
  }
}
