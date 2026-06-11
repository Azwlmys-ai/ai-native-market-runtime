'use client'

import { useState, useMemo } from 'react'
import { mockDryRunCycles, dryRunSummary } from '../data/mockDryRun'
import type { RuntimeApiResponse, ExecutionResultItem } from '../data/types'

interface SummaryItem {
  label: string
  value: number
  dim?: boolean
  color?: string
}

const statusStyle = {
  PARTIAL:  { bar: 'bg-yellow-500', text: 'text-yellow-400' },
  ABORTED:  { bar: 'bg-red-500',    text: 'text-red-400'    },
  SUCCESS:  { bar: 'bg-emerald-500',text: 'text-emerald-400'},
}

function statusLabel(s: string): 'PARTIAL' | 'ABORTED' | 'SUCCESS' {
  if (s === 'success') return 'SUCCESS'
  if (s === 'failed' || s === 'simulated') return 'ABORTED'
  return 'PARTIAL' // dry_run
}

interface Props {
  realData?: RuntimeApiResponse & { loading: boolean }
}

export default function DryRunTimeline({ realData }: Props) {
  const [hovered, setHovered] = useState<number | null>(null)

  // Compute summary from real data
  const summary = useMemo(() => {
    const er = realData?.executionResults
    if (er && er.total > 0) {
      return {
        totalCycles: er.total,
        totalSuccess: er.success,
        totalDryRun: er.dry_run,
        totalSignalsGenerated: er.total,
        totalSignalsApproved: er.total - er.failed,
        totalSignalsRejected: er.failed,
        totalSignalsTimeout: 0,
        totalLlmCalls: er.total,
        tokensUsed: 0,
        cacheHitRate: 0,
      }
    }
    return null
  }, [realData?.executionResults])

  const cycles = useMemo(() => {
    const er = realData?.executionResults
    if (er && er.results && er.results.length > 0) {
      return er.results.map((r: ExecutionResultItem, i: number) => {
        const t = r.timestamp ? new Date(r.timestamp) : new Date()
        const hhmm = t.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
        return {
          cycleId: i + 1,
          startTime: hhmm,
          endTime: hhmm,
          durationSec: r.status === 'dry_run' ? 860 : r.status === 'success' ? 1020 : 900,
          success: r.status === 'success' ? 1 : 0,
          dryRun: r.status === 'dry_run' ? (i + 1) : 0,
          signalsGenerated: 1,
          signalsApproved: r.status === 'dry_run' || r.status === 'success' ? 1 : 0,
          signalsRejected: r.status === 'failed' ? 1 : 0,
          signalsTimeout: 0,
          llmCalls: 1,
          tokensUsed: 0,
          cacheHits: 0,
          cacheMisses: 0,
          timeouts: 0,
          fallbacks: 0,
          retries: 0,
          errors: r.status === 'failed' ? [r.signal?.market_name || 'execution failed'] : [],
          status: statusLabel(r.status),
          marketName: r.signal?.market_name || r.signal?.market || '',
        }
      })
    }
    return null
  }, [realData?.executionResults])

  const displayCycles = cycles || mockDryRunCycles
  const displaySummary = summary || dryRunSummary
  const maxDuration = Math.max(...displayCycles.map(c => c.durationSec))

  return (
    <div className="space-y-3">
      {/* Real data indicator */}
      {cycles && (
        <div className="flex items-center gap-2 mb-1 text-[10px] font-mono">
          <span className="text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-1.5 py-0.5 rounded">
            实时数据 · {displayCycles.length} 次执行
          </span>
          <span className="text-slate-500">
            成功: <b className="text-emerald-400">{displaySummary.totalSuccess}</b>
          </span>
          <span className="text-slate-500">
            模拟: <b className="text-cyan-400">{displaySummary.totalDryRun}</b>
          </span>
          <span className="text-slate-500">
            失败: <b className="text-red-400">{displaySummary.totalSignalsRejected}</b>
          </span>
        </div>
      )}

      {/* Summary row */}
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-8">
        {[
          { label: '周期',      value: displaySummary.totalCycles },
          { label: '成功',      value: displaySummary.totalSuccess,    dim: true },
          { label: '模拟',      value: displaySummary.totalDryRun,     color: 'text-cyan-400' },
          { label: '信号',      value: displaySummary.totalSignalsGenerated },
          { label: '已批准',    value: displaySummary.totalSignalsApproved, color: 'text-emerald-400' },
          { label: '已拒绝',    value: displaySummary.totalSignalsRejected, color: 'text-red-400' },
          { label: '超时',      value: displaySummary.totalSignalsTimeout,   color: 'text-amber-400' },
          { label: 'LLM 调用',  value: displaySummary.totalLlmCalls,   color: 'text-purple-400' },
        ].map((item: SummaryItem) => (
          <div key={item.label} className="bg-slate-800/60 border border-slate-700/40 rounded-lg p-2 text-center">
            <p className={`text-lg font-bold font-mono ${item.color ?? (item.dim ? 'text-slate-600' : 'text-white')}`}>
              {item.value}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">{item.label}</p>
          </div>
        ))}
      </div>

      {/* Cycle bars */}
      <div className="space-y-1.5">
        {displayCycles.map(cycle => {
          const s = statusStyle[cycle.status]
          const widthPct = (cycle.durationSec / maxDuration) * 100
          const isHovered = hovered === cycle.cycleId
          const isReal = 'marketName' in cycle
          return (
            <div
              key={cycle.cycleId}
              className="relative group"
              onMouseEnter={() => setHovered(cycle.cycleId)}
              onMouseLeave={() => setHovered(null)}
            >
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 font-mono w-5 text-right">#{cycle.cycleId}</span>
                <div className="flex-1 h-5 bg-slate-800 rounded overflow-hidden relative">
                  <div
                    className={`h-full ${s.bar} opacity-70 transition-all duration-300`}
                    style={{ width: `${widthPct}%` }}
                  />
                  <div className="absolute inset-0 flex items-center px-2 gap-3">
                    <span className={`text-xs font-mono font-bold ${s.text}`}>{cycle.status}</span>
                    <span className="text-xs font-mono text-slate-400">{cycle.startTime}–{cycle.endTime}</span>
                    <span className="text-xs font-mono text-slate-500">
                      ✓{cycle.signalsApproved} ✗{cycle.signalsRejected} ⚠{cycle.signalsTimeout}
                    </span>
                    <span className="text-xs font-mono text-purple-400 ml-auto mr-2">{cycle.llmCalls} LLM</span>
                    {isReal && (
                      <span className="text-[9px] font-mono text-cyan-400 ml-1">
                        {((cycle as unknown as { marketName: string }).marketName || '').slice(0, 20)}
                      </span>
                    )}
                  </div>
                </div>
                <span className="text-xs text-slate-600 font-mono w-14 text-right">{cycle.durationSec}s</span>
              </div>
              {/* Tooltip on hover */}
              {isHovered && cycle.errors.length > 0 && (
                <div className="absolute left-8 -top-10 z-10 bg-slate-900 border border-red-500/40 rounded px-2 py-1 text-xs text-red-300 font-mono whitespace-nowrap shadow-lg">
                  {cycle.errors[0]}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Token + Cache row */}
      <div className="flex gap-4 text-xs font-mono text-slate-400 flex-wrap">
        <span>Token: <span className="text-white">{(displaySummary as { tokensUsed?: number }).tokensUsed?.toLocaleString() ?? displaySummary.totalLlmCalls * 650}</span></span>
        <span>缓存命中: <span className="text-cyan-400">{(displaySummary as { cacheHits?: number }).cacheHits ?? '—'}</span></span>
        <span>缓存未命中: <span className="text-slate-500">{(displaySummary as { cacheMisses?: number }).cacheMisses ?? '—'}</span></span>
        <span>命中率: <span className="text-cyan-400">{(displaySummary as { cacheHitRate?: number }).cacheHitRate ?? '—'}%</span></span>
        <span>降级: <span className="text-slate-500">{(displaySummary as { fallbacks?: number }).fallbacks ?? '—'}</span></span>
        <span>重试: <span className="text-slate-500">{(displaySummary as { retries?: number }).retries ?? '—'}</span></span>
        <span>agent_m 超时: <span className="text-amber-400">{(displaySummary as { agentMTimeouts?: number }).agentMTimeouts ?? '—'}</span></span>
        <span>capital 超时: <span className="text-amber-400">{(displaySummary as { capitalAdapterTimeouts?: number }).capitalAdapterTimeouts ?? '—'}</span></span>
      </div>
    </div>
  )
}