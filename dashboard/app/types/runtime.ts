// ── Runtime Streaming Event Types ───────────────────────
// Discriminated union for all runtime events.
// Designed to be smoothly replaceable with WebSocket later.

// ── Base ────────────────────────────────────────────────

export interface RuntimeEventBase {
  id: string
  timestamp: number
  sourceAgent: string
}

// ── Task Events ─────────────────────────────────────────

export interface TaskStartedPayload {
  taskId: string
  message: string
}

export interface TaskCompletedPayload {
  taskId: string
  message: string
  durationMs: number
}

export interface TaskFailedPayload {
  taskId: string
  message: string
  durationMs: number
  error?: string
}

export type TaskStartedEvent = RuntimeEventBase & {
  type: 'task.started'
  payload: TaskStartedPayload
}

export type TaskCompletedEvent = RuntimeEventBase & {
  type: 'task.completed'
  payload: TaskCompletedPayload
}

export type TaskFailedEvent = RuntimeEventBase & {
  type: 'task.failed'
  payload: TaskFailedPayload
}

// ── Signal Lifecycle Events ─────────────────────────────

export interface SignalCreatedPayload {
  signalId: string
  marketId?: string
  direction: 'LONG' | 'SHORT'
  confidence: number
  edge: number
  message: string
}

export interface SignalApprovedPayload {
  signalId: string
  marketId?: string
  reviewer: string
  message: string
}

export interface SignalRejectedPayload {
  signalId: string
  marketId?: string
  reviewer: string
  reason: string
  message: string
}

export type SignalCreatedEvent = RuntimeEventBase & {
  type: 'signal.created'
  payload: SignalCreatedPayload
}

export type SignalApprovedEvent = RuntimeEventBase & {
  type: 'signal.approved'
  payload: SignalApprovedPayload
}

export type SignalRejectedEvent = RuntimeEventBase & {
  type: 'signal.rejected'
  payload: SignalRejectedPayload
}

// ── Runtime Status Events ───────────────────────────────

export interface RuntimeWarningPayload {
  severity: 'warning'
  message: string
  source: string
}

export interface RuntimeErrorPayload {
  severity: 'error'
  message: string
  source: string
  details?: string
}

export type RuntimeWarningEvent = RuntimeEventBase & {
  type: 'runtime.warning'
  payload: RuntimeWarningPayload
}

export type RuntimeErrorEvent = RuntimeEventBase & {
  type: 'runtime.error'
  payload: RuntimeErrorPayload
}

// ── Agent Lifecycle Events ──────────────────────────────

export interface AgentOnlinePayload {
  agentId: string
  agentName: string
}

export interface AgentOfflinePayload {
  agentId: string
  agentName: string
  reason?: string
}

export interface AgentBusyPayload {
  agentId: string
  agentName: string
  taskId: string
  message: string
}

export type AgentOnlineEvent = RuntimeEventBase & {
  type: 'agent.online'
  payload: AgentOnlinePayload
}

export type AgentOfflineEvent = RuntimeEventBase & {
  type: 'agent.offline'
  payload: AgentOfflinePayload
}

export type AgentBusyEvent = RuntimeEventBase & {
  type: 'agent.busy'
  payload: AgentBusyPayload
}

// ── Discriminated Union ─────────────────────────────────

export type RuntimeStreamEvent =
  | TaskStartedEvent
  | TaskCompletedEvent
  | TaskFailedEvent
  | SignalCreatedEvent
  | SignalApprovedEvent
  | SignalRejectedEvent
  | RuntimeWarningEvent
  | RuntimeErrorEvent
  | AgentOnlineEvent
  | AgentOfflineEvent
  | AgentBusyEvent

export type RuntimeEventType = RuntimeStreamEvent['type']

// ── Signal Lifecycle State Machine ──────────────────────

export type SignalLifecycleState =
  | 'created'
  | 'reviewing'
  | 'approved'
  | 'rejected'
  | 'executed'
  | 'timeout'

export interface SignalLifecycleRecord {
  signalId: string
  state: SignalLifecycleState
  marketId?: string
  direction: 'LONG' | 'SHORT'
  confidence: number
  edge: number
  createdAt: number
  reviewer?: string
  rejectionReason?: string
  executedAt?: number
}