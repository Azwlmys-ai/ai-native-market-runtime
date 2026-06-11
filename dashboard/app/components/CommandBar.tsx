'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Terminal, CornerDownLeft, X, ChevronRight } from 'lucide-react'

// ── Command System ──────────────────────────────────────

export interface CommandResult {
  type: 'filter' | 'focus' | 'expand' | 'highlight' | 'info' | 'error'
  payload: {
    agentFilter?: string[]           // agent IDs to show
    marketFocus?: string             // market slug
    layerExpand?: string             // layer to expand
    highlightPath?: string[]         // agent IDs to highlight
    message?: string                 // info/error message
  }
}

export interface CommandBarProps {
  onCommand: (result: CommandResult) => void
  agentIds: string[]
  layers: string[]
}

interface HistoryEntry {
  command: string
  ts: number
  result: CommandResult
}

// ── Command parser (rule-based, no LLM) ─────────────────

function parseCommand(input: string, agentIds: string[], layers: string[]): CommandResult {
  const trimmed = input.trim().toLowerCase()

  // ── show failed agents ──
  if (/show\s+failed\s+agents?/.test(trimmed)) {
    return {
      type: 'filter',
      payload: { agentFilter: ['agent_m', 'capital_adapter'], message: '⛔ 显示失败/超时 Agent' },
    }
  }

  // ── show all agents ──
  if (/show\s+all\s+agents?|reset\s+view|clear\s+filter/.test(trimmed)) {
    return {
      type: 'filter',
      payload: { agentFilter: [], message: '◈ 显示所有 Agent' },
    }
  }

  // ── show running agents ──
  if (/show\s+(running|active)\s+agents?/.test(trimmed)) {
    return {
      type: 'filter',
      payload: { agentFilter: ['orchestrator', 'news_scanner', 'market_analyzer', 'signal_generator', 'learner'], message: '▶ 显示运行中 Agent' },
    }
  }

  // ── focus <market> ──
  const focusMatch = trimmed.match(/focus\s+([a-zA-Z0-9\-_]+)/)
  if (focusMatch) {
    return {
      type: 'focus',
      payload: { marketFocus: focusMatch[1], message: `◎ 聚焦市场: ${focusMatch[1]}` },
    }
  }

  // ── expand <layer> ──
  const expandMatch = trimmed.match(/(?:expand|open|show)\s+(analysis|data|decision|execution|learning|risk|supervisor|signal)\s*(layer)?/)
  if (expandMatch) {
    const layerMap: Record<string, string> = {
      analysis: 'signal',
      decision: 'risk',
      supervisor: 'supervisor',
      data: 'data',
      signal: 'signal',
      risk: 'risk',
      execution: 'execution',
      learning: 'learning',
    }
    const layer = layerMap[expandMatch[1]]
    if (layer && layers.includes(layer)) {
      return {
        type: 'expand',
        payload: { layerExpand: layer, message: `▼ 展开 ${layer.toUpperCase()} Layer` },
      }
    }
    return { type: 'error', payload: { message: `✕ 未知 Layer: ${expandMatch[1]}` } }
  }

  // ── collapse <layer> ──
  const collapseMatch = trimmed.match(/(?:collapse|close|hide)\s+(analysis|data|decision|execution|learning|risk|supervisor|signal)\s*(layer)?/)
  if (collapseMatch) {
    const layerMap: Record<string, string> = {
      analysis: 'signal',
      decision: 'risk',
      supervisor: 'supervisor',
      data: 'data',
      signal: 'signal',
      risk: 'risk',
      execution: 'execution',
      learning: 'learning',
    }
    const layer = layerMap[collapseMatch[1]]
    if (layer && layers.includes(layer)) {
      return {
        type: 'expand',
        payload: { layerExpand: layer, message: `▲ 折叠 ${layer.toUpperCase()} Layer` },
      }
    }
    return { type: 'error', payload: { message: `✕ 未知 Layer: ${collapseMatch[1]}` } }
  }

  // ── show execution path ──
  if (/show\s+execution\s+path|exec\s+path|execution\s+flow/.test(trimmed)) {
    return {
      type: 'highlight',
      payload: {
        highlightPath: ['orchestrator', 'signal_generator', 'agent_m', 'capital_adapter', 'executor'],
        message: '◆ 高亮执行路径: Orchestrator → Signal → Risk → Capital → Executor',
      },
    }
  }

  // ── why reject signals ──
  if (/why\s+reject\s+signals?|rejection\s+reason/.test(trimmed)) {
    return {
      type: 'info',
      payload: {
        message:
          '📋 拒绝原因: Agent M 超时(30s) → 安全降级 → 全部拒绝。风险限额检查未通过。',
      },
    }
  }

  // ── show risk layer ──
  if (/show\s+risk\s+layer|risk\s+view/.test(trimmed)) {
    return {
      type: 'expand',
      payload: { layerExpand: 'risk', message: '▼ 展开 RISK Layer (Regime Detector + Agent M)' },
    }
  }

  // ── help ──
  if (/help|\?/.test(trimmed)) {
    return {
      type: 'info',
      payload: {
        message:
          '命令: show failed agents | show all agents | focus <market> | expand <layer> | show execution path | why reject signals | help',
      },
    }
  }

  // ── Unknown ──
  return {
    type: 'error',
    payload: { message: `✕ 未知命令: "${input.trim()}"。输入 "help" 查看可用命令。` },
  }
}

// ── Component ────────────────────────────────────────────

export default function CommandBar({ onCommand, agentIds, layers }: CommandBarProps) {
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [historyIdx, setHistoryIdx] = useState(-1)
  const [focused, setFocused] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Auto-scroll history
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [history])

  const handleSubmit = useCallback(() => {
    const text = input.trim()
    if (!text) return

    const result = parseCommand(text, agentIds, layers)
    setHistory((prev) => [...prev.slice(-49), { command: text, ts: Date.now(), result }])
    onCommand(result)
    setInput('')
    setHistoryIdx(-1)
    setSuggestions([])
  }, [input, agentIds, layers, onCommand])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        handleSubmit()
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        const newIdx = historyIdx + 1 < history.length ? historyIdx + 1 : historyIdx
        if (newIdx >= 0 && history[history.length - 1 - newIdx]) {
          setHistoryIdx(newIdx)
          setInput(history[history.length - 1 - newIdx].command)
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        if (historyIdx <= 0) {
          setHistoryIdx(-1)
          setInput('')
          return
        }
        const newIdx = historyIdx - 1
        setHistoryIdx(newIdx)
        setInput(history[history.length - 1 - newIdx]?.command ?? '')
      } else if (e.key === 'Escape') {
        setInput('')
        setSuggestions([])
        inputRef.current?.blur()
      }
    },
    [historyIdx, history, handleSubmit],
  )

  const handleInputChange = useCallback(
    (value: string) => {
      setInput(value)
      setHistoryIdx(-1)

      if (value.trim().length > 0) {
        const cmds = [
          'show failed agents',
          'show all agents',
          'show running agents',
          'focus btc',
          'focus eth',
          'expand analysis layer',
          'expand risk layer',
          'show execution path',
          'why reject signals',
          'help',
        ]
        const lower = value.toLowerCase()
        setSuggestions(cmds.filter((c) => c.startsWith(lower) && c !== lower))
      } else {
        setSuggestions([])
      }
    },
    [],
  )

  return (
    <div className="flex flex-col min-h-0">
      {/* Input area */}
      <div
        className={`
          flex items-center gap-2 px-3 py-2 border rounded-lg transition-all duration-200
          bg-slate-900/80
          ${focused ? 'border-cyan-500/50 shadow-[0_0_12px_rgba(6,182,212,0.15)]' : 'border-slate-700/60'}
        `}
      >
        <Terminal
          className={`w-3.5 h-3.5 flex-shrink-0 ${focused ? 'text-cyan-400' : 'text-slate-600'}`}
        />
        <div className="flex-1 flex items-center min-w-0">
          <span className="text-[9px] font-mono text-slate-600 mr-1 flex-shrink-0 select-none">
            {'>'}
          </span>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="输入命令… (help 查看可用命令)"
            className="flex-1 bg-transparent text-[11px] font-mono text-slate-200 placeholder-slate-600 outline-none min-w-0"
            spellCheck={false}
            autoComplete="off"
          />
          {input && (
            <button
              onClick={() => {
                setInput('')
                setSuggestions([])
              }}
              className="p-0.5 hover:bg-slate-800 rounded flex-shrink-0"
            >
              <X className="w-3 h-3 text-slate-600" />
            </button>
          )}
        </div>
        <button
          onClick={handleSubmit}
          disabled={!input.trim()}
          className="p-1 rounded hover:bg-slate-800 disabled:opacity-30 flex-shrink-0"
        >
          <CornerDownLeft className="w-3 h-3 text-slate-500" />
        </button>
      </div>

      {/* Suggestions */}
      {suggestions.length > 0 && input.trim() && (
        <div className="mt-1 bg-slate-900/90 border border-slate-700/40 rounded-md overflow-hidden">
          {suggestions.slice(0, 5).map((s) => (
            <button
              key={s}
              className="w-full text-left px-3 py-1.5 text-[10px] font-mono text-slate-400 hover:bg-slate-800/60 hover:text-cyan-400 transition-colors flex items-center gap-2"
              onMouseDown={(e) => {
                e.preventDefault()
                setInput(s)
                setSuggestions([])
                // Auto-submit on click
                setTimeout(() => handleSubmit(), 0)
              }}
            >
              <ChevronRight className="w-2.5 h-2.5 flex-shrink-0" />
              {s}
            </button>
          ))}
        </div>
      )}

      {/* History */}
      {history.length > 0 && (
        <div
          ref={listRef}
          className="mt-1.5 max-h-24 overflow-y-auto space-y-0.5 pr-0.5"
        >
          {history.slice().reverse().map((entry, i) => (
            <div
              key={`${entry.ts}-${i}`}
              className="flex items-start gap-1.5 text-[9px] font-mono animate-in fade-in slide-in-from-left-1"
            >
              <span className="text-cyan-500 flex-shrink-0 mt-px">{'>'}</span>
              <span className="text-slate-300 break-all">{entry.command}</span>
              {entry.result.payload.message && (
                <span
                  className={`ml-auto flex-shrink-0 truncate max-w-[40%] ${
                    entry.result.type === 'error'
                      ? 'text-red-400'
                      : 'text-emerald-400/70'
                  }`}
                >
                  {entry.result.payload.message}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}