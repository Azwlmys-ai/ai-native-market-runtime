'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

export type DemoPreset = 'executive' | 'operations' | 'incident-replay'

interface DemoModeControllerProps {
  agentIds: string[]
  selectedId: string | null
  onSelectAgent: (id: string | null) => void
  /** Current demo preset — display only */
  preset?: DemoPreset
}

const CYCLE_INTERVAL_MS = 8000

const PRESET_LABELS: Record<DemoPreset, string> = {
  executive: '高管演示',
  operations: '运营监控',
  'incident-replay': '事故复盘',
}

const PRESET_COLORS: Record<DemoPreset, string> = {
  executive: '#22d3ee',
  operations: '#34d399',
  'incident-replay': '#f59e0b',
}

const PRESET_DESCRIPTIONS: Record<DemoPreset, string> = {
  executive: '面向高管·投资人·客户：展示 AI 协同价值、商业 KPI 与企业自动化能力',
  operations: '面向运维团队：展示实时 Agent 工作流、日志、风控决策与系统健康',
  'incident-replay': '面向事后复盘：展示 AI 自动发现、隔离与恢复事故的全过程',
}

export default function DemoModeController({
  agentIds,
  selectedId,
  onSelectAgent,
  preset = 'executive',
}: DemoModeControllerProps) {
  const [demoOn, setDemoOn] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(-1)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastUserSelectRef = useRef<string | null>(null)

  const stopDemo = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    setDemoOn(false)
  }, [])

  const toggleDemo = useCallback(() => {
    if (demoOn) {
      stopDemo()
    } else {
      lastUserSelectRef.current = selectedId
      setDemoOn(true)
    }
  }, [demoOn, stopDemo, selectedId])

  // Demo cycle effect
  useEffect(() => {
    if (!demoOn || agentIds.length === 0) return

    const startIndex = agentIds.indexOf(selectedId ?? '')
    const idx = startIndex >= 0 ? startIndex : 0

    timerRef.current = setInterval(() => {
      setCurrentIndex((prev) => {
        if (prev === -1) return idx
        const next = (prev + 1) % agentIds.length
        return next
      })
    }, CYCLE_INTERVAL_MS)

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [demoOn, agentIds, selectedId])

  // Apply selection whenever currentIndex changes
  useEffect(() => {
    if (!demoOn || agentIds.length === 0) return
    const targetId = agentIds[currentIndex] ?? null
    if (targetId !== selectedId) {
      onSelectAgent(targetId)
    }
  }, [demoOn, currentIndex, agentIds, selectedId, onSelectAgent])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const currentAgent = agentIds[currentIndex] ?? '—'
  const progressPct = ((currentIndex + 1) / agentIds.length) * 100

  return (
    <div className="h-full flex flex-col min-h-0 text-[10px] font-mono">
      {/* Preset display — read-only, not interactive */}
      <div className="flex-shrink-0 mb-3">
        <div className="flex items-center gap-1.5 mb-1.5">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider">演示模式</div>
          <span className="text-[7px] font-mono text-slate-600 border border-slate-700/40 px-1 py-0 rounded">只读</span>
        </div>
        <div className="flex flex-col gap-1">
          {(Object.keys(PRESET_LABELS) as DemoPreset[]).map((p) => {
            const isActive = preset === p
            return (
              <div
                key={p}
                className={`text-left px-2 py-1.5 rounded border ${
                  isActive
                    ? 'border-cyan-500/60 bg-cyan-500/10'
                    : 'border-slate-700/40 bg-slate-900/50'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <div
                    className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor: PRESET_COLORS[p],
                      boxShadow: isActive ? `0 0 6px ${PRESET_COLORS[p]}80` : 'none',
                    }}
                  />
                  <span
                    className="text-[10px] font-bold"
                    style={{ color: isActive ? PRESET_COLORS[p] : '#94a3b8' }}
                  >
                    {PRESET_LABELS[p]}
                  </span>
                  {isActive && (
                    <span className="ml-auto text-[7px] px-1 py-0 rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/20">
                      当前
                    </span>
                  )}
                </div>
                {isActive && (
                  <p className="text-[8px] text-slate-500 mt-0.5 leading-snug">
                    {PRESET_DESCRIPTIONS[p]}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-slate-700/30 my-2 flex-shrink-0" />

      {/* Toggle */}
      <div className="flex-shrink-0 flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-slate-500 uppercase tracking-wider">Agent 轮播</span>
          {demoOn && (
            <span className="text-[8px] text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-1 rounded">
              激活
            </span>
          )}
        </div>
        <button
          onClick={toggleDemo}
          className={`
            relative w-10 h-5 rounded-full transition-colors duration-200 flex-shrink-0
            ${demoOn ? 'bg-cyan-500/40' : 'bg-slate-700'}
            border ${demoOn ? 'border-cyan-500/40' : 'border-slate-600'}
          `}
          aria-label={demoOn ? '停止轮播' : '开始轮播'}
        >
          <div
            className={`
              absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all duration-200
              ${demoOn ? 'left-[22px] bg-cyan-400' : 'left-0.5 bg-slate-400'}
            `}
          />
        </button>
      </div>

      {/* Status when ON */}
      {demoOn && (
        <>
          <div className="flex-shrink-0 space-y-2 mb-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-500">焦点</span>
              <span className="text-cyan-400 font-bold truncate ml-2">{currentAgent}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">周期</span>
              <span className="text-slate-400">
                {currentIndex + 1} / {agentIds.length}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">间隔</span>
              <span className="text-slate-600">{CYCLE_INTERVAL_MS / 1000}s</span>
            </div>
          </div>

          <div className="flex-shrink-0 mt-auto">
            <div className="flex justify-between text-[8px] text-slate-600 mb-1">
              <span>进度</span>
              <span>{Math.round(progressPct)}%</span>
            </div>
            <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-cyan-500/60 rounded-full transition-all duration-500 ease-linear"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        </>
      )}

      {!demoOn && (
        <div className="flex-shrink-0 flex-1 flex flex-col justify-end">
          <p className="text-[9px] text-slate-600 leading-relaxed">
            每 {CYCLE_INTERVAL_MS / 1000} 秒自动切换 Agent 焦点。高亮活跃 Agent 的拓扑节点、时间轴和事件。
          </p>
        </div>
      )}
    </div>
  )
}
