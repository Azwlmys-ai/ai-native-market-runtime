import { NextResponse } from 'next/server'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'

function readJson<T>(filename: string): T | null {
  try {
    return JSON.parse(readFileSync(join(DATA_DIR, filename), 'utf-8')) as T
  } catch {
    return null
  }
}

// ── Raw types from polymarket_arbitrage data files ────────

interface OkxAsset {
  spot?: { symbol: string; last_price: number; volume_24h: number }
  perpetual?: { symbol: string; last_price: number }
  funding?: { funding_rate: number; funding_rate_8h: number }
}

interface OkxData {
  timestamp: string
  btc?: OkxAsset
  eth?: OkxAsset
  sol?: OkxAsset
  bnb?: OkxAsset
}

interface FinnhubStock {
  symbol: string
  price: number
  change: number
  change_percent: number
  high: number
  low: number
  volume?: number
  timestamp: string
}

interface FinnhubData {
  status: string
  source: string
  stocks: FinnhubStock[]
  timestamp: string
}

interface RegimeData {
  regime: string
  confidence: number
  indicators: {
    btc_trend: string
    funding_rate_signal: string
    market_activity: string
  }
  strategy_adjustment: {
    position_size_multiplier: number
    risk_tolerance: string
  }
  reason: string
  timestamp: string
}

interface VolEntry {
  volatility_daily: number
  volatility_annualized: number
  periods: number
  status: string
}

interface CorrelationEntry {
  a: string
  b: string
  pearson: number
}

interface MaxDrawdownMap {
  [key: string]: number
}

interface RiskData {
  timestamp: string
  data_available: boolean
  volatility: Record<string, VolEntry>
  correlations: CorrelationEntry[]
  max_drawdown: MaxDrawdownMap
}

// ── Output types ──────────────────────────────────────────

export interface CryptoAsset {
  symbol: string
  spotPrice: number | null
  perpPrice: number | null
  fundingRate: number | null
  fundingRate8h: number | null
  basis: number | null
}

export interface EquityAsset {
  symbol: string
  price: number
  change: number
  changePct: number
  high: number
  low: number
}

export interface MacroRegime {
  regime: string
  confidence: number
  btcTrend: string
  fundingSignal: string
  marketActivity: string
  riskTolerance: string
  positionSizeMultiplier: number
  reason: string
  timestamp: string
}

export interface VolatilityAsset {
  asset: string
  label: string
  category: string
  volDaily: number
  volAnnualized: number
  maxDrawdown: number | null
  periods: number
}

export interface CorrelationPair {
  a: string
  b: string
  pearson: number
}

export interface MultiMarketResponse {
  source: 'real'
  updatedAt: string
  cryptoUpdatedAt: string | null
  equityUpdatedAt: string | null
  regimeUpdatedAt: string | null
  riskUpdatedAt: string | null
  crypto: CryptoAsset[]
  equity: EquityAsset[]
  macroRegime: MacroRegime | null
  volatility: VolatilityAsset[]
  correlations: CorrelationPair[]
}

// ── Label map for asset keys ──────────────────────────────

const ASSET_LABELS: Record<string, { label: string; category: string }> = {
  'okx:BTC-USDT':          { label: 'BTC',          category: 'crypto' },
  'okx:ETH-USDT':          { label: 'ETH',          category: 'crypto' },
  'okx:SOL-USDT':          { label: 'SOL',          category: 'crypto' },
  'okx:BNB-USDT':          { label: 'BNB',          category: 'crypto' },
  'us:ARKK':               { label: 'ARKK',         category: 'equity' },
  'us:CRSP':               { label: 'CRSP',         category: 'equity' },
  'us:TSLA':               { label: 'TSLA',         category: 'equity' },
  'commodities:gold':      { label: 'Gold',         category: 'commodity' },
  'commodities:silver':    { label: 'Silver',       category: 'commodity' },
  'commodities:oil_wti':   { label: 'Oil WTI',      category: 'commodity' },
  'commodities:oil_brent': { label: 'Oil Brent',    category: 'commodity' },
  'commodities:natural_gas':{ label: 'Nat Gas',     category: 'commodity' },
  'commodities:copper':    { label: 'Copper',       category: 'commodity' },
}

// ── Equity symbols to surface (highest signal value) ─────

const EQUITY_PRIORITY = ['NVDA', 'TSLA', 'MSFT', 'COIN', 'MSTR', 'META', 'AAPL', 'GOOGL', 'AMZN', 'TTWO']

export async function GET() {
  const okx = readJson<OkxData>('okx_data.json')
  const finnhub = readJson<FinnhubData>('finnhub_data.json')
  const regime = readJson<RegimeData>('market_regime.json')
  const risk = readJson<RiskData>('risk_snapshot.json')

  // ── CRYPTO ──────────────────────────────────────────────
  const cryptoKeys: Array<keyof OkxData & ('btc' | 'eth' | 'sol' | 'bnb')> = ['btc', 'eth', 'sol', 'bnb']
  const crypto: CryptoAsset[] = cryptoKeys.map((key) => {
    const d = okx?.[key]
    const spot = d?.spot?.last_price ?? null
    const perp = d?.perpetual?.last_price ?? null
    return {
      symbol: key.toUpperCase(),
      spotPrice: spot,
      perpPrice: perp,
      fundingRate: d?.funding?.funding_rate ?? null,
      fundingRate8h: d?.funding?.funding_rate_8h ?? null,
      basis: spot !== null && perp !== null ? perp - spot : null,
    }
  })

  // ── EQUITY ──────────────────────────────────────────────
  const stockMap = new Map<string, FinnhubStock>()
  for (const s of finnhub?.stocks ?? []) {
    stockMap.set(s.symbol, s)
  }

  const equity: EquityAsset[] = EQUITY_PRIORITY
    .map((sym) => {
      const s = stockMap.get(sym)
      if (!s) return null
      return {
        symbol: s.symbol,
        price: s.price,
        change: s.change,
        changePct: s.change_percent,
        high: s.high,
        low: s.low,
      }
    })
    .filter((x): x is EquityAsset => x !== null)
    .slice(0, 7)

  // ── MACRO REGIME ────────────────────────────────────────
  const macroRegime: MacroRegime | null = regime
    ? {
        regime: regime.regime,
        confidence: regime.confidence,
        btcTrend: regime.indicators?.btc_trend ?? '—',
        fundingSignal: regime.indicators?.funding_rate_signal ?? '—',
        marketActivity: regime.indicators?.market_activity ?? '—',
        riskTolerance: regime.strategy_adjustment?.risk_tolerance ?? '—',
        positionSizeMultiplier: regime.strategy_adjustment?.position_size_multiplier ?? 1,
        reason: regime.reason ?? '',
        timestamp: regime.timestamp,
      }
    : null

  // ── VOLATILITY ──────────────────────────────────────────
  const volatility: VolatilityAsset[] = Object.entries(risk?.volatility ?? {})
    .map(([key, val]) => {
      const meta = ASSET_LABELS[key] ?? { label: key, category: 'other' }
      return {
        asset: key,
        label: meta.label,
        category: meta.category,
        volDaily: val.volatility_daily,
        volAnnualized: val.volatility_annualized,
        maxDrawdown: risk?.max_drawdown?.[key] ?? null,
        periods: val.periods,
      }
    })

  // ── CORRELATIONS ────────────────────────────────────────
  const correlations: CorrelationPair[] = (risk?.correlations ?? [])
    .slice(0, 8)
    .map((c) => ({
      a: ASSET_LABELS[c.a]?.label ?? c.a.split(':')[1] ?? c.a,
      b: ASSET_LABELS[c.b]?.label ?? c.b.split(':')[1] ?? c.b,
      pearson: c.pearson,
    }))

  const result: MultiMarketResponse = {
    source: 'real',
    updatedAt: new Date().toISOString(),
    cryptoUpdatedAt: okx?.timestamp ?? null,
    equityUpdatedAt: finnhub?.timestamp ?? null,
    regimeUpdatedAt: regime?.timestamp ?? null,
    riskUpdatedAt: risk?.timestamp ?? null,
    crypto,
    equity,
    macroRegime,
    volatility,
    correlations,
  }

  return NextResponse.json(result)
}
