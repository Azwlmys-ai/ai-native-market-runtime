'use client'

import { useMemo } from 'react'
import type { DataTruthMeta, DataTruthLevel } from '../types/dataTruth'

// ── Types ─────────────────────────────────────────────────

interface Props {
  meta: DataTruthMeta
  sseConnected?: boolean
  compact?: boolean
}

// ── Color & Label Maps ────────────────────────────────────

const LEVEL_CONFIG: Record<DataTruthLevel, {
  color: string
  border: string
  bg: string
  glow: string
  label: string
  labelShort: string
}> = {
  REAL: {
    color: 'text-emerald-400',
    border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/10',
    glow: 'shadow-[0_0_8px_rgba(52,211,153,0.25)]',
    label: 'REAL DATA',
    labelShort: 'REAL',
  },
  DERIVED: {
    color: 'text-cyan-400',
    border: 'border-cyan-500/30',
    bg: 'bg-cyan-500/10',
    glow: 'shadow-[0_0_8px_rgba(34,211,238,0.25)]',
    label: 'DERIVED INSIGHT',
    labelShort: 'DERIVED',
  },
  FALLBACK: {
    color: 'text-amber-400',
    border: 'border-amber-500/30',
    bg: 'bg-amber-500/10',
    glow: 'shadow-[0_0_8px_rgba(251,191,36,0.25)]',
    label: 'FALLBACK MODE',
    labelShort: 'FALLBACK',
  },
  DEMO: {
    color: 'text-violet-400',
    border: 'border-violet-500/30',
    bg: 'bg-violet-500/10',
    glow: 'shadow-[0_0_8px_rgba(167,139,250,0.25)]',
    label: 'DEMO DATA',
    labelShort: 'DEMO',
  },
  EMPTY: {
    color: 'text-slate-500',
    border: 'border-slate-600/30',
    bg: 'bg-slate-500/5',
    glow: '',
    label: 'NO LIVE DATA',
    labelShort: 'EMPTY',
  },
}

// ── Freshness helpers ─────────────────────────────────────

function formatFreshness(ms: number | undefined): string {
  if (ms == null) return ''
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 60000)}m`
}

function freshnessStatus(ms: number | undefined): { label: string; color: string } {
  if (ms == null) return { label: '', color: '' }
  if (ms <= 30000) return { label: 'LIVE', color: 'text-emerald-400' }
  if (ms <= 90000) return { label: 'STALE', color: 'text-amber-400' }
  return { label: 'CRITICAL', color: 'text-red-400' }
}

// ── Component ─────────────────────────────────────────────

export default function DataTruthBadge({ meta, sseConnected, compact = false }: Props) {
  const config = LEVEL_CONFIG[meta.level]
  const freshness = freshnessStatus(meta.freshnessMs)
  const freshnessStr = formatFreshness(meta.freshnessMs)

  const pulseClass = useMemo(() => {
    if (meta.level === 'REAL' && sseConnected && !meta.stale) return 'animate-pulse'
    if (meta.level === 'FALLBACK' || meta.degraded) return 'animate-pulse'
    return ''
  }, [meta.level, sseConnected, meta.stale, meta.degraded])

  if (compact) {
    return (
      <div
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[8px] font-mono font-bold ${
          config.color
        } ${config.border} ${config.bg} ${config.glow} ${pulseClass}`}
        title={`来源: ${meta.source}${meta.freshnessMs != null ? ` · 新鲜度: ${freshnessStr}` : ''}${meta.degraded ? ' · 降级模式' : ''}`}
      >
        <div className={`w-1 h-1 rounded-full ${config.color.replace('text-', 'bg-')}`} />
        {config.labelShort}
      </div>
    )
  }

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1.5 rounded-full border text-[10px] font-mono font-bold ${
        config.color
      } ${config.border} ${config.bg} ${config.glow} ${pulseClass} transition-all duration-500`}
      title={`来源: ${meta.source}${meta.freshnessMs != null ? ` · 新鲜度: ${freshnessStr}` : ''}${meta.degraded ? ' · 降级模式' : ''}${sseConnected === false ? ' · SSE 已断开' : ''}`}
    >
      <div className={`w-2 h-2 rounded-full ${config.color.replace('text-', 'bg-')} ${
        meta.level === 'REAL' && sseConnected ? 'animate-pulse' : ''
      }`} />
      <span>{config.label}</span>
      {freshnessStr && (
        <>
          <span className="text-slate-600">·</span>
          <span className={freshness.color}>{freshnessStr}</span>
          <span className={`text-[9px] ${freshness.color}`}>{freshness.label}</span>
        </>
      )}
      {meta.degraded && (
        <>
          <span className="text-slate-600">·</span>
          <span className="text-amber-400">{sseConnected === false ? 'SSE OFF' : 'DEGRADED'}</span>
        </>
      )}
    </div>
  )
}

// ── Hook: derive DataTruthMeta from runtime state ──────────

export interface TruthDerivationInput {
  sseConnected: boolean
  lastEventTimestamp: number | undefined
  demoMode: boolean
  source: string
  isEmpty: boolean
}

export function deriveTruthMeta(input: TruthDerivationInput, now: number): DataTruthMeta {
  const freshnessMs = input.lastEventTimestamp ? now - input.lastEventTimestamp : undefined
  const stale = freshnessMs != null && freshnessMs > 30000
  const degraded = !input.sseConnected || (freshnessMs != null && freshnessMs > 90000)

  if (input.isEmpty) {
    return {
      level: 'EMPTY',
      source: input.source,
      updatedAt: input.lastEventTimestamp,
      freshnessMs,
      stale: true,
      degraded: true,
    }
  }

  if (input.demoMode) {
    return {
      level: 'DEMO',
      source: input.source,
      updatedAt: input.lastEventTimestamp,
      freshnessMs,
      stale,
      degraded,
    }
  }

  // If SSE is connected and freshness is under 10s, it's REAL
  if (input.sseConnected && freshnessMs != null && freshnessMs < 10000) {
    return {
      level: 'REAL',
      source: input.source,
      updatedAt: input.lastEventTimestamp,
      freshnessMs,
      stale: false,
      degraded: false,
    }
  }

  // If SSE is disconnected or freshness > 30s, it's FALLBACK
  if (!input.sseConnected || (freshnessMs != null && freshnessMs > 90000)) {
    return {
      level: 'FALLBACK',
      source: !input.sseConnected
        ? `${input.source} · 系统已切换至冗余数据通道`
        : input.source,
      updatedAt: input.lastEventTimestamp,
      freshnessMs,
      stale,
      degraded,
    }
  }

  // Default: DERIVED from recent data
  return {
    level: 'DERIVED',
    source: input.source,
    updatedAt: input.lastEventTimestamp,
    freshnessMs,
    stale,
    degraded,
  }
}