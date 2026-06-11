'use client'

import { useState, useEffect, useCallback } from 'react'

// ── Types (mirror API response) ───────────────────────────

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

export interface MultiMarketData {
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

// ── Hook ──────────────────────────────────────────────────

const POLL_INTERVAL_MS = 30_000

export function useMultiMarketData(): {
  data: MultiMarketData | null
  loading: boolean
  error: boolean
} {
  const [data, setData] = useState<MultiMarketData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('/api/multi-market')
      if (!res.ok) {
        setError(true)
        return
      }
      const json: MultiMarketData = await res.json()
      setData(json)
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- polling pattern
    fetchData()
    const id = setInterval(fetchData, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [fetchData])

  return { data, loading, error }
}
