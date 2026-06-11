'use client'

import { useState, useMemo, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { mockSignals } from '../data/mockSignals'

// Legacy panel: retained while the homepage prioritizes visualization_state.
// ── Types ────────────────────────────────────────────────

type SignalDecision = 'APPROVE' | 'REJECT' | 'PENDING' | 'TIMEOUT'
type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

interface SignalsApiSignal {
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
  signals: SignalsApiSignal[]
}

// ── Config ───────────────────────────────────────────────

const POLL_INTERVAL_MS = 5000

const decisionConfig: Record<SignalDecision, { color: string; bg: string; border: string; label: string }> = {
  APPROVE:  { color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/40', label: '✓ 批准' },
  REJECT:   { color: 'text-red-400',     bg: 'bg-red-500/10',     border: 'border-red-500/40',     label: '✗ 拒绝'  },
  PENDING:  { color: 'text-blue-400',    bg: 'bg-blue-500/10',    border: 'border-blue-500/40',    label: '◌ 待定' },
  TIMEOUT:  { color: 'text-amber-400',   bg: 'bg-amber-500/10',   border: 'border-amber-500/40',   label: '⚠ 超时' },
}

const riskConfig: Record<RiskLevel, { color: string; dot: string }> = {
  LOW:      { color: 'text-emerald-400', dot: 'bg-emerald-400' },
  MEDIUM:   { color: 'text-yellow-400',  dot: 'bg-yellow-400'  },
  HIGH:     { color: 'text-orange-400',  dot: 'bg-orange-400'  },
  CRITICAL: { color: 'text-red-400',     dot: 'bg-red-400'     },
}

// ── Display Signal (same shape as original mock) ─────────

interface DisplaySignal {
  id: string
  cycleId: number
  asset: string
  direction: 'LONG' | 'SHORT'
  strategy: string
  edge: number
  confidence: number
  source: string
  generatedAt: string
  decision: SignalDecision
  riskLevel: RiskLevel
  reasoning: string
  rejectionReason?: string
  capitalAllocation?: number
  positionSize?: number
  isReal: boolean
}

// ── Helpers ─────────────────────────────────────────────

function computeRiskLevel(confidence: number): RiskLevel {
  if (confidence >= 80) return 'HIGH'
  if (confidence >= 60) return 'MEDIUM'
  return 'LOW'
}

function mapApiSignalToDisplay(s: SignalsApiSignal, idx: number): DisplaySignal {
  const rl = computeRiskLevel(s.confidence)
  const isAgentB = s.sourceAgent?.toLowerCase().includes('agent_b')

  return {
    id: s.id,
    cycleId: idx + 1,
    asset: s.market,
    direction: s.direction,
    strategy: isAgentB ? 'Agent B Signal' : 'System Signal',
    edge: s.edge,
    confidence: s.confidence,
    source: s.sourceAgent,
    generatedAt: s.timestamp,
    decision: s.decision,
    riskLevel: rl,
    reasoning: `${s.market} — edge=${s.edge} · price=${s.price} · source=${s.sourceAgent}`,
    isReal: true,
  }
}

// ── Hook: useSignalsData ─────────────────────────────────

function useSignalsData(): { data: SignalsApiResponse | null; loading: boolean; error: boolean } {
  const [data, setData] = useState<SignalsApiResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchSignals = useCallback(async () => {
    try {
      const res = await fetch('/api/signals')
      if (!res.ok) {
        setError(true)
        setLoading(false)
        return
      }
      const json: SignalsApiResponse = await res.json()
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
    fetchSignals()
    const interval = setInterval(fetchSignals, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchSignals])

  return { data, loading, error }
}

// ── Component ────────────────────────────────────────────

type Filter = 'ALL' | SignalDecision

interface Props {
  onSelectSignal?: (market: string | null) => void
  selectedSignal?: string | null
}

export default function SignalReviewPanel({ onSelectSignal, selectedSignal }: Props) {
  const [filter, setFilter] = useState<Filter>('ALL')
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data: signalsData, loading } = useSignalsData()

  // Merge real signals with mock fallback
  const signals = useMemo<DisplaySignal[]>(() => {
    if (signalsData?.signals && signalsData.signals.length > 0) {
      return signalsData.signals.map(mapApiSignalToDisplay)
    }
    // Fallback to mock when no real data
    return mockSignals.map((s) => ({ ...s, isReal: false }))
  }, [signalsData])

  const queue = signalsData?.queue ?? null
  const dataSource = signalsData?.source ?? 'fallback'

  const filtered = filter === 'ALL' ? signals : signals.filter((s) => s.decision === filter)

  return (
    <div className="flex flex-col h-full">
      {/* Real data indicator + queue stats */}
      {dataSource === 'real' && queue && (
        <div className="flex flex-wrap items-center gap-2 mb-3 text-xs font-mono">
          <span className="text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-1.5 py-0.5 rounded flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />
            REAL DATA
          </span>
          <span className="text-slate-400 bg-slate-800/60 border border-slate-700/40 px-1.5 py-0.5 rounded">
            {queue.total} 信号
          </span>
          <span className="text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-1.5 py-0.5 rounded">
            ✓{queue.approved}
          </span>
          <span className="text-red-400 bg-red-500/10 border border-red-500/30 px-1.5 py-0.5 rounded">
            ✗{queue.rejected}
          </span>
          {queue.timeout > 0 && (
            <span className="text-amber-400 bg-amber-500/10 border border-amber-500/30 px-1.5 py-0.5 rounded">
              ⚠{queue.timeout}
            </span>
          )}
        </div>
      )}

      {/* Loading indicator */}
      {loading && !signalsData && (
        <div className="text-xs font-mono text-slate-400 mb-2 animate-pulse">
          正在连接信号数据源...
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-1 mb-3 flex-wrap">
        {(['ALL', 'APPROVE', 'REJECT', 'TIMEOUT', 'PENDING'] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-2.5 py-1 text-sm font-mono rounded border transition-all ${
              filter === f
                ? 'bg-cyan-500/20 border-cyan-500/60 text-cyan-300'
                : 'bg-slate-700/60 border-slate-500/40 text-slate-300 hover:border-slate-400'
            }`}
          >
            {f}
            <span className="ml-1 text-slate-400">
              {f === 'ALL' ? signals.length : signals.filter((s) => s.decision === f).length}
            </span>
          </button>
        ))}
      </div>

      {/* Signal list */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scroll">
        <AnimatePresence>
          {filtered.map((signal) => {
            const dc = decisionConfig[signal.decision]
            const rc = riskConfig[signal.riskLevel]
            const isOpen = expanded === signal.id
            return (
              <motion.div
                key={signal.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className={`rounded-lg border ${dc.border} ${dc.bg} overflow-hidden shadow-sm ${
                  selectedSignal === signal.id ? 'ring-1 ring-cyan-500/50 shadow-[0_0_12px_rgba(34,211,238,0.15)]' : ''
                }`}
              >
                <div
                  className="p-3 cursor-pointer"
                  onClick={() => {
                    setExpanded(isOpen ? null : signal.id)
                    if (onSelectSignal) {
                      onSelectSignal(selectedSignal === signal.id ? null : signal.id)
                    }
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-bold font-mono ${dc.color}`}>{dc.label}</span>
                      <span className={`inline-flex items-center gap-1 text-xs font-mono ${rc.color}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${rc.dot}`} />
                        {signal.riskLevel}
                      </span>
                      {signal.isReal && (
                        <span className="text-xs font-mono text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 px-1.5 py-0.5 rounded flex items-center gap-1">
                          <span className="w-1 h-1 rounded-full bg-emerald-400" />
                          REAL
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-400 font-mono">C#{signal.cycleId}</span>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <p className="text-base text-white font-semibold leading-tight truncate max-w-[220px]">
                      {signal.asset}
                    </p>
                    <span
                      className={`text-sm font-mono px-2 py-0.5 rounded ${
                        signal.direction === 'LONG'
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      {signal.direction}
                    </span>
                  </div>
                  <div className="flex gap-3 mt-1.5 text-xs text-slate-300 font-mono flex-wrap">
                    <span>
                      edge:{' '}
                      <span className="text-cyan-400">+{signal.edge}%</span>
                    </span>
                    <span>
                      conf:{' '}
                      <span className="text-slate-100">{signal.confidence}%</span>
                    </span>
                    {signal.isReal && (
                      <span className="text-cyan-400/70">
                        src: {signal.source.length > 16
                          ? signal.source.slice(0, 14) + '…'
                          : signal.source}
                      </span>
                    )}
                  </div>
                </div>

                <AnimatePresence>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-slate-600/40 px-3 py-2.5 space-y-2"
                    >
                      <p className="text-sm text-slate-200 leading-relaxed">
                        <span className="text-slate-400 font-mono">推理: </span>
                        {signal.reasoning}
                      </p>
                      {signal.rejectionReason && (
                        <p className="text-sm text-red-200 leading-relaxed">
                          <span className="text-slate-400 font-mono">拒绝原因: </span>
                          {signal.rejectionReason}
                        </p>
                      )}
                      {signal.capitalAllocation && signal.capitalAllocation > 0 && (
                        <p className="text-sm text-emerald-300 font-mono">
                          资金: ${signal.capitalAllocation.toLocaleString()} · 数量:{' '}
                          {signal.positionSize}
                        </p>
                      )}
                      <p className="text-xs text-slate-400 font-mono">策略: {signal.strategy}</p>
                      {signal.isReal && (
                        <p className="text-xs text-emerald-300 font-mono">
                          ✅ 来自真实 review/execution 数据源
                        </p>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
