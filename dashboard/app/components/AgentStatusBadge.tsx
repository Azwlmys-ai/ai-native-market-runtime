'use client'

import type { AgentRuntimeState } from '@/app/data/types'

interface Props {
  state: AgentRuntimeState
  message?: string
}

const STATE_COLORS: Record<AgentRuntimeState, { bg: string; text: string; border: string; label: string }> = {
  IDLE: { bg: '#1e293b', text: '#94a3b8', border: '#334155', label: '空闲' },
  SCANNING: { bg: '#1e3a5f', text: '#60a5fa', border: '#2563eb', label: '扫描' },
  SIGNAL_CREATED: { bg: '#312e81', text: '#a5b4fc', border: '#6366f1', label: '信号' },
  WAITING_REVIEW: { bg: '#422006', text: '#fbbf24', border: '#d97706', label: '审核' },
  APPROVED: { bg: '#052e16', text: '#4ade80', border: '#16a34a', label: '✓ 通过' },
  REJECTED: { bg: '#450a0a', text: '#fca5a5', border: '#dc2626', label: '✗ 拒绝' },
  DRY_RUN: { bg: '#164e63', text: '#22d3ee', border: '#0891b2', label: '模拟' },
  EXECUTING: { bg: '#4a044e', text: '#e879f9', border: '#c026d3', label: '执行' },
  POSITION_OPEN: { bg: '#14532d', text: '#86efac', border: '#22c55e', label: '持仓' },
  POSITION_CLOSED: { bg: '#1e293b', text: '#64748b', border: '#475569', label: '已平' },
  WARNING: { bg: '#422006', text: '#fbbf24', border: '#d97706', label: '⚠ 警告' },
  ERROR: { bg: '#450a0a', text: '#fca5a5', border: '#dc2626', label: '❌ 错误' },
}

export default function AgentStatusBadge({ state, message }: Props) {
  const c = STATE_COLORS[state]

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded px-1.5 py-0.5"
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
      }}
      title={message ?? undefined}
    >
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: c.text }}
      />
      <span
        className="text-[9px] font-mono font-bold leading-none"
        style={{ color: c.text }}
      >
        {c.label}
      </span>
    </div>
  )
}