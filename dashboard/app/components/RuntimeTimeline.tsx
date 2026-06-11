'use client'

import type { RuntimeTimeline, RuntimeTimelineStep, TimelineStepStatus } from '../data/types'

const STATUS_CLASS: Record<TimelineStepStatus, string> = {
  pending: 'border-slate-600 text-slate-500',
  active: 'border-blue-400 text-blue-400',
  success: 'border-green-400 text-green-400',
  failed: 'border-red-400 text-red-400',
}

const STATUS_DOT: Record<TimelineStepStatus, string> = {
  pending: 'bg-slate-600',
  active: 'bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.6)]',
  success: 'bg-green-400',
  failed: 'bg-red-400',
}

function StepIcon({ type }: { type: RuntimeTimelineStep['type'] }) {
  switch (type) {
    case 'signal':
      return <span className="text-[9px]">⚡</span>
    case 'review':
      return <span className="text-[9px]">🔍</span>
    case 'approval':
      return <span className="text-[9px]">✓</span>
    case 'execution':
      return <span className="text-[9px]">▶</span>
    case 'close':
      return <span className="text-[9px]">🔒</span>
  }
}

function StepRow({ step, isLast }: { step: RuntimeTimelineStep; isLast: boolean }) {
  const dotClass = STATUS_DOT[step.status]
  const borderClass = STATUS_CLASS[step.status]

  return (
    <div className="flex items-start gap-2 min-h-0">
      {/* Vertical line + dot column */}
      <div className="flex flex-col items-center flex-shrink-0" style={{ width: 16 }}>
        <div
          className={`w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`}
          style={{ marginTop: 1 }}
        />
        {!isLast && (
          <div className={`w-px flex-1 min-h-[12px] ${step.status === 'pending' ? 'bg-slate-700' : step.status === 'active' ? 'bg-blue-400/40' : 'bg-slate-600'}`} />
        )}
      </div>

      {/* Step content */}
      <div className={`flex-1 min-w-0 pb-2 ${isLast ? '' : ''}`}>
        <div className="flex items-center gap-1.5">
          <StepIcon type={step.type} />
          <span className={`text-[9px] font-mono font-bold ${borderClass.split(' ').pop()}`}>
            {step.label}
          </span>
          {step.agent && (
            <span className="text-[8px] font-mono text-slate-600 ml-auto truncate">
              {step.agent}
            </span>
          )}
        </div>
        {step.message && (
          <p className="text-[8px] font-mono text-slate-600 truncate mt-0.5 ml-4">
            {step.message}
          </p>
        )}
        {step.ts && (
          <p className="text-[7px] font-mono text-slate-700 mt-0.5 ml-4">
            {step.ts}
          </p>
        )}
      </div>
    </div>
  )
}

function TimelineCard({ timeline }: { timeline: RuntimeTimeline }) {
  return (
    <div className="border border-slate-700/40 rounded bg-slate-900/60 p-2.5 mb-2">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {timeline.market && (
            <span className="text-[10px] font-mono font-bold text-cyan-400 truncate">
              {timeline.market}
            </span>
          )}
          {!timeline.market && (
            <span className="text-[10px] font-mono text-slate-500">—</span>
          )}
        </div>
        <span className="text-[8px] font-mono text-slate-600 flex-shrink-0">
          {timeline.createdAt}
        </span>
      </div>

      {/* Steps */}
      <div className="space-y-0">
        {timeline.steps.map((step, i) => (
          <StepRow key={step.id} step={step} isLast={i === timeline.steps.length - 1} />
        ))}
      </div>
    </div>
  )
}

interface Props {
  timelines: RuntimeTimeline[]
}

export default function RuntimeTimelineView({ timelines }: Props) {
  if (timelines.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-[10px] font-mono text-slate-600">
          等待运行时事件...
        </span>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* Compact header */}
      <div className="flex items-center justify-between mb-2 flex-shrink-0">
        <h2 className="text-[10px] font-bold font-mono text-slate-400 uppercase tracking-widest">
          运行时执行时间轴
        </h2>
        <span className="text-[8px] font-mono text-red-400 bg-red-500/10 border border-red-500/20 px-1 py-0 rounded">
          只读
        </span>
      </div>

      {/* Scrollable timeline list */}
      <div className="flex-1 overflow-y-auto min-h-0 pr-0.5">
        {timelines.map((tl) => (
          <TimelineCard key={tl.id} timeline={tl} />
        ))}
      </div>
    </div>
  )
}