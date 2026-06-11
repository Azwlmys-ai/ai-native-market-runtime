// ── Mock Runtime Stream Generator ───────────────────────
// Periodically generates realistic runtime events and
// pushes them through the shared RuntimeBus.
// Supports start()/stop() — no setInterval leaks.
// Easily replaceable with real WebSocket/SSE later.

import { runtimeBus } from './runtimeBus'
import type { RuntimeStreamEvent } from '@/app/types/runtime'

// ── Agent pool ──────────────────────────────────────────

const AGENT_POOL = [
  { id: 'orchestrator', name: 'Orchestrator' },
  { id: 'news_scanner', name: 'News Scanner' },
  { id: 'market_analyzer', name: 'Market Analyzer' },
  { id: 'signal_generator', name: 'Signal Generator' },
  { id: 'regime_detector', name: 'Regime Detector' },
  { id: 'agent_m', name: 'Agent M' },
  { id: 'capital_adapter', name: 'Capital Adapter' },
  { id: 'executor', name: 'Executor' },
]

const MARKETS = [
  'will-eth-reach-3k-by-july',
  'btc-above-70k-this-week',
  'fed-cut-rates-jun',
  'sol-break-200',
  'us-election-2024',
]

const DIRECTIONS: Array<'LONG' | 'SHORT'> = ['LONG', 'SHORT']

// ── Generator state ─────────────────────────────────────

let intervalId: ReturnType<typeof setInterval> | null = null
let signalCounter = 0
let taskCounter = 0
let cycleId = 1

function id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

// ── Event factories ─────────────────────────────────────

function createTaskStarted(): RuntimeStreamEvent {
  taskCounter++
  const agent = pick(AGENT_POOL)
  const taskId = `task-${taskCounter}`
  return {
    id: id('ts'),
    timestamp: Date.now(),
    sourceAgent: agent.id,
    type: 'task.started',
    payload: {
      taskId,
      message: `${agent.name} — 开始执行任务 #${taskId}`,
    },
  }
}

function createTaskCompleted(): RuntimeStreamEvent {
  const agent = pick(AGENT_POOL)
  const taskId = `task-${taskCounter}`
  const duration = Math.floor(Math.random() * 8000) + 500
  return {
    id: id('tc'),
    timestamp: Date.now(),
    sourceAgent: agent.id,
    type: 'task.completed',
    payload: {
      taskId,
      message: `${agent.name} — 任务完成，耗时 ${duration}ms`,
      durationMs: duration,
    },
  }
}

function createTaskFailed(): RuntimeStreamEvent {
  const agent = pick(AGENT_POOL)
  const taskId = `task-${taskCounter}`
  const duration = Math.floor(Math.random() * 30000) + 1000
  return {
    id: id('tf'),
    timestamp: Date.now(),
    sourceAgent: agent.id,
    type: 'task.failed',
    payload: {
      taskId,
      message: `${agent.name} — 任务失败（超时 ${duration}ms）`,
      durationMs: duration,
      error: 'timeout exceeded',
    },
  }
}

function createSignalCreated(): RuntimeStreamEvent {
  signalCounter++
  const signalId = `SIG-${String(signalCounter).padStart(4, '0')}`
  const direction = pick(DIRECTIONS)
  const confidence = Math.round((Math.random() * 30 + 60) * 100) / 100
  const edge = Math.round((Math.random() * 8 + 1) * 100) / 100
  const marketId = pick(MARKETS)

  return {
    id: id('sc'),
    timestamp: Date.now(),
    sourceAgent: 'signal_generator',
    type: 'signal.created',
    payload: {
      signalId,
      marketId,
      direction,
      confidence,
      edge,
      message: `创建信号 ${signalId} — ${marketId} ${direction === 'LONG' ? '做多' : '做空'} edge=+${edge}% conf=${confidence}`,
    },
  }
}

function createSignalApproved(): RuntimeStreamEvent {
  const signalId = `SIG-${String(Math.max(1, signalCounter)).padStart(4, '0')}`
  const reviewer = 'agent_m'
  const marketId = pick(MARKETS)
  return {
    id: id('sa'),
    timestamp: Date.now(),
    sourceAgent: reviewer,
    type: 'signal.approved',
    payload: {
      signalId,
      marketId,
      reviewer: 'Agent M',
      message: `信号 ${signalId} 已批准 — Agent M 风险审核通过`,
    },
  }
}

function createSignalRejected(): RuntimeStreamEvent {
  const signalId = `SIG-${String(Math.max(1, signalCounter)).padStart(4, '0')}`
  const reviewer = 'agent_m'
  const reasons = [
    '超过风险限额',
    '波动率状态不匹配',
    '置信度不足',
    '与趋势信号冲突',
  ]
  const reason = pick(reasons)
  return {
    id: id('sr'),
    timestamp: Date.now(),
    sourceAgent: reviewer,
    type: 'signal.rejected',
    payload: {
      signalId,
      marketId: pick(MARKETS),
      reviewer: 'Agent M',
      reason,
      message: `信号 ${signalId} 已拒绝 — ${reason}`,
    },
  }
}

function createRuntimeWarning(): RuntimeStreamEvent {
  const agents = ['news_scanner', 'market_analyzer', 'regime_detector']
  const source = pick(agents)
  const warnings = [
    '数据源延迟 > 5s',
    '模型置信度波动',
    '订单簿深度不足',
    '风控系数已调整',
  ]
  return {
    id: id('rw'),
    timestamp: Date.now(),
    sourceAgent: source,
    type: 'runtime.warning',
    payload: {
      severity: 'warning',
      message: pick(warnings),
      source,
    },
  }
}

function createRuntimeError(): RuntimeStreamEvent {
  const agents = ['executor', 'capital_adapter', 'orchestrator']
  const source = pick(agents)
  return {
    id: id('re'),
    timestamp: Date.now(),
    sourceAgent: source,
    type: 'runtime.error',
    payload: {
      severity: 'error',
      message: `消息队列积压 — 连接超时`,
      source,
      details: 'Connection timeout after 30s',
    },
  }
}

function createAgentOnline(): RuntimeStreamEvent {
  const agent = pick(AGENT_POOL)
  return {
    id: id('ao'),
    timestamp: Date.now(),
    sourceAgent: agent.id,
    type: 'agent.online',
    payload: {
      agentId: agent.id,
      agentName: agent.name,
    },
  }
}

function createAgentOffline(): RuntimeStreamEvent {
  const agent = pick(AGENT_POOL)
  const reasons = ['心跳超时', '手动下线', '资源不足']
  return {
    id: id('af'),
    timestamp: Date.now(),
    sourceAgent: agent.id,
    type: 'agent.offline',
    payload: {
      agentId: agent.id,
      agentName: agent.name,
      reason: pick(reasons),
    },
  }
}

function createAgentBusy(): RuntimeStreamEvent {
  const agent = pick(AGENT_POOL)
  const taskId = `task-${taskCounter}`
  return {
    id: id('ab'),
    timestamp: Date.now(),
    sourceAgent: agent.id,
    type: 'agent.busy',
    payload: {
      agentId: agent.id,
      agentName: agent.name,
      taskId,
      message: `${agent.name} 正在处理周期 C#${cycleId}`,
    },
  }
}

// ── Weighted event generator ────────────────────────────

type EventFactory = () => RuntimeStreamEvent

const WEIGHTED_EVENTS: Array<{ weight: number; fn: EventFactory }> = [
  { weight: 15, fn: createTaskStarted },
  { weight: 12, fn: createTaskCompleted },
  { weight: 3, fn: createTaskFailed },
  { weight: 10, fn: createSignalCreated },
  { weight: 6, fn: createSignalApproved },
  { weight: 4, fn: createSignalRejected },
  { weight: 5, fn: createRuntimeWarning },
  { weight: 2, fn: createRuntimeError },
  { weight: 3, fn: createAgentOnline },
  { weight: 2, fn: createAgentOffline },
  { weight: 8, fn: createAgentBusy },
]

const TOTAL_WEIGHT = WEIGHTED_EVENTS.reduce((sum, e) => sum + e.weight, 0)

function randomEvent(): RuntimeStreamEvent {
  let roll = Math.random() * TOTAL_WEIGHT
  for (const { weight, fn } of WEIGHTED_EVENTS) {
    roll -= weight
    if (roll <= 0) return fn()
  }
  return createTaskStarted()
}

// ── Tick ────────────────────────────────────────────────

function tick() {
  cycleId++
  // Emit 1-3 events per tick for realism
  const count = Math.random() < 0.2 ? 3 : Math.random() < 0.5 ? 2 : 1
  for (let i = 0; i < count; i++) {
    runtimeBus.emit(randomEvent())
  }
}

// ── Public API ──────────────────────────────────────────

export function startMockStream(intervalMs = 2500): () => void {
  if (intervalId) return stopMockStream

  // Emit initial seed events so dashboard isn't empty
  for (let i = 0; i < 5; i++) {
    runtimeBus.emit(createAgentOnline())
  }
  runtimeBus.emit(createTaskStarted())
  runtimeBus.emit(createSignalCreated())

  intervalId = setInterval(tick, intervalMs)
  return stopMockStream
}

export function stopMockStream() {
  if (intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
}

export function isMockStreamRunning(): boolean {
  return intervalId !== null
}