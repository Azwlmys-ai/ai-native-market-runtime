'use client'

import { useMultiMarketData } from '../hooks/useMultiMarketData'
import type { CryptoAsset, EquityAsset, VolatilityAsset, CorrelationPair, MacroRegime } from '../hooks/useMultiMarketData'

// ── Helpers ───────────────────────────────────────────────

function fmtPrice(n: number | null): string {
  if (n === null) return '—'
  if (n >= 10_000) return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
  if (n >= 100) return `$${n.toFixed(2)}`
  return `$${n.toFixed(3)}`
}

function fmtPct(n: number | null): string {
  if (n === null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function fmtFunding(r: number | null): string {
  if (r === null) return '—'
  const pct = r * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(4)}%`
}

function fmtVol(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

function fmtTs(ts: string | null | undefined): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts.slice(11, 16)
  }
}

// ── Sub-components ────────────────────────────────────────

function SectionHeader({ label, ts }: { label: string; ts?: string | null }) {
  return (
    <div className="flex items-center justify-between mb-2">
      <span className="text-xs font-bold font-mono text-slate-200 uppercase tracking-wider">{label}</span>
      {ts && (
        <span className="text-xs font-mono text-slate-400">{fmtTs(ts)}</span>
      )}
    </div>
  )
}

function RegimeCard({ regime }: { regime: MacroRegime }) {
  const isRange = regime.regime === 'range'
  const confColor =
    regime.confidence >= 70 ? 'text-emerald-400' :
    regime.confidence >= 40 ? 'text-amber-400' : 'text-slate-400'

  return (
    <div className="bg-slate-700/55 border border-slate-500/40 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className={`text-sm font-bold font-mono uppercase tracking-wider ${isRange ? 'text-amber-300' : 'text-cyan-300'}`}>
          {regime.regime.toUpperCase()}
        </span>
        <span className={`text-xs font-mono ${confColor}`}>
          {regime.confidence}% 置信
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        <span className="text-xs font-mono text-slate-300">BTC 趋势</span>
        <span className="text-xs font-mono text-slate-100 text-right">{regime.btcTrend}</span>
        <span className="text-xs font-mono text-slate-300">资金信号</span>
        <span className="text-xs font-mono text-slate-100 text-right">{regime.fundingSignal}</span>
        <span className="text-xs font-mono text-slate-300">市场活跃度</span>
        <span className="text-xs font-mono text-slate-100 text-right">{regime.marketActivity}</span>
        <span className="text-xs font-mono text-slate-300">风险容忍</span>
        <span className="text-xs font-mono text-slate-100 text-right">{regime.riskTolerance}</span>
      </div>
    </div>
  )
}

function CryptoRow({ asset }: { asset: CryptoAsset }) {
  const fundingPositive = (asset.fundingRate ?? 0) >= 0
  const basisSign = asset.basis !== null ? (asset.basis >= 0 ? '+' : '') : ''

  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-600/30 last:border-0">
      <div className="w-10 flex-shrink-0">
        <span className="text-sm font-bold font-mono text-white">{asset.symbol}</span>
      </div>
      <div className="flex-1 text-right">
        <div className="text-sm font-mono text-white">{fmtPrice(asset.spotPrice)}</div>
        <div className="text-xs font-mono text-slate-300">
          基差{' '}
          <span className={asset.basis !== null && asset.basis >= 0 ? 'text-emerald-400' : 'text-red-400'}>
            {asset.basis !== null ? `${basisSign}${asset.basis.toFixed(1)}` : '—'}
          </span>
        </div>
      </div>
      <div className="w-20 text-right flex-shrink-0 pl-2">
        <div className={`text-xs font-mono ${fundingPositive ? 'text-emerald-300' : 'text-red-300'}`}>
          {fmtFunding(asset.fundingRate)}
        </div>
        <div className="text-xs font-mono text-slate-400">资金费率</div>
      </div>
    </div>
  )
}

function EquityRow({ asset }: { asset: EquityAsset }) {
  const up = asset.changePct >= 0
  return (
    <div className="flex items-center justify-between py-1 border-b border-slate-600/30 last:border-0">
      <span className="text-sm font-bold font-mono text-slate-100 w-12 flex-shrink-0">{asset.symbol}</span>
      <span className="text-sm font-mono text-white flex-1 text-right">{fmtPrice(asset.price)}</span>
      <span className={`text-xs font-mono w-16 text-right flex-shrink-0 ${up ? 'text-emerald-300' : 'text-red-300'}`}>
        {fmtPct(asset.changePct)}
      </span>
    </div>
  )
}

function VolRow({ asset }: { asset: VolatilityAsset }) {
  const volHigh = asset.volAnnualized > 0.2
  const volColor = volHigh ? 'text-amber-400' : 'text-slate-300'
  const ddColor = asset.maxDrawdown !== null && asset.maxDrawdown < -0.2 ? 'text-red-400' : 'text-slate-400'

  return (
    <div className="flex items-center justify-between py-1 border-b border-slate-600/30 last:border-0">
      <span className="text-xs font-mono text-slate-200 w-20 flex-shrink-0 truncate">{asset.label}</span>
      <span className={`text-xs font-mono flex-1 text-right ${volColor}`}>
        {fmtVol(asset.volAnnualized)} vol
      </span>
      {asset.maxDrawdown !== null && (
        <span className={`text-xs font-mono w-16 text-right flex-shrink-0 ${ddColor}`}>
          DD {(asset.maxDrawdown * 100).toFixed(1)}%
        </span>
      )}
    </div>
  )
}

function CorrRow({ pair }: { pair: CorrelationPair }) {
  const r = pair.pearson
  const barWidth = Math.abs(r) * 100
  const barColor = r > 0.7 ? 'bg-cyan-500' : r > 0.4 ? 'bg-amber-500' : r > 0 ? 'bg-slate-500' : 'bg-red-500'

  return (
    <div className="flex items-center gap-2 py-1">
      <span className="text-xs font-mono text-slate-300 w-24 flex-shrink-0 truncate">
        {pair.a}/{pair.b}
      </span>
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full`} style={{ width: `${barWidth}%` }} />
      </div>
      <span className={`text-xs font-mono w-10 text-right flex-shrink-0 ${r > 0.7 ? 'text-cyan-300' : r > 0.4 ? 'text-amber-300' : r < 0 ? 'text-red-300' : 'text-slate-300'}`}>
        {r.toFixed(2)}
      </span>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[40, 32, 48, 36].map((h, i) => (
        <div key={i} className="bg-slate-800/50 rounded-lg" style={{ height: h }} />
      ))}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────

export default function MarketDataPanel() {
  const { data, loading, error } = useMultiMarketData()

  if (loading && !data) return <Skeleton />

  if (error && !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-xs font-mono text-red-300">数据读取失败</span>
      </div>
    )
  }

  const commodityVol = data?.volatility.filter((v) => v.category === 'commodity') ?? []
  const cryptoVol = data?.volatility.filter((v) => v.category === 'crypto') ?? []

  return (
    <div className="space-y-4 h-full overflow-y-auto pr-1 text-sm">
      {/* REAL DATA badge */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold font-mono text-emerald-300 bg-emerald-500/15 border border-emerald-400/40 px-2 py-0.5 rounded uppercase tracking-wider">
          REAL DATA
        </span>
        <span className="text-xs font-mono text-slate-400">{fmtTs(data?.updatedAt)}</span>
      </div>

      {/* ── REGIME ───────────────────────── */}
      <div>
        <SectionHeader label="市场体制" ts={data?.regimeUpdatedAt} />
        {data?.macroRegime ? (
          <RegimeCard regime={data.macroRegime} />
        ) : (
          <span className="text-xs font-mono text-slate-400">Regime 数据不可用</span>
        )}
      </div>

      {/* ── CRYPTO ───────────────────────── */}
      <div>
        <SectionHeader label="CRYPTO · OKX" ts={data?.cryptoUpdatedAt} />
        <div className="bg-slate-700/45 border border-slate-500/35 rounded-lg px-3 py-2">
          {data?.crypto.map((a) => (
            <CryptoRow key={a.symbol} asset={a} />
          ))}
          {!data?.crypto.length && (
            <span className="text-xs font-mono text-slate-400">暂无 OKX 数据</span>
          )}
        </div>
      </div>

      {/* ── EQUITY ───────────────────────── */}
      <div>
        <SectionHeader label="EQUITY · Finnhub" ts={data?.equityUpdatedAt} />
        <div className="bg-slate-700/45 border border-slate-500/35 rounded-lg px-3 py-2">
          {data?.equity.map((a) => (
            <EquityRow key={a.symbol} asset={a} />
          ))}
          {!data?.equity.length && (
            <span className="text-xs font-mono text-slate-400">暂无股票数据</span>
          )}
        </div>
        <p className="text-xs font-mono text-slate-400 mt-1">前一日收盘 (Finnhub)</p>
      </div>

      {/* ── COMMODITY VOL ────────────────── */}
      {commodityVol.length > 0 && (
        <div>
          <SectionHeader label="COMMODITY · 波动率" ts={data?.riskUpdatedAt} />
          <div className="bg-slate-700/45 border border-slate-500/35 rounded-lg px-3 py-2">
            {commodityVol.map((v) => (
              <VolRow key={v.asset} asset={v} />
            ))}
          </div>
          <p className="text-xs font-mono text-slate-400 mt-1">历史 OHLCV 计算，无实时价</p>
        </div>
      )}

      {/* ── CRYPTO VOL ───────────────────── */}
      {cryptoVol.length > 0 && (
        <div>
          <SectionHeader label="CRYPTO · 波动率" ts={data?.riskUpdatedAt} />
          <div className="bg-slate-700/45 border border-slate-500/35 rounded-lg px-3 py-2">
            {cryptoVol.map((v) => (
              <VolRow key={v.asset} asset={v} />
            ))}
          </div>
        </div>
      )}

      {/* ── CORRELATIONS ─────────────────── */}
      {(data?.correlations.length ?? 0) > 0 && (
        <div>
          <SectionHeader label="跨市场相关性" ts={data?.riskUpdatedAt} />
          <div className="bg-slate-700/45 border border-slate-500/35 rounded-lg px-3 py-2">
            {data?.correlations.map((c, i) => (
              <CorrRow key={i} pair={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
