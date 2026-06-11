'use client'

import { useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Node,
  Edge,
  MarkerType,
  NodeProps,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useRuntimeSnapshot } from '../data/runtimeState'
import {
  RuntimeAgentState,
  AgentLayer,
  LAYER_LABELS,
} from '../data/runtimeState'
import type { AgentRuntimeStatus } from '../data/types'
import type { AgentRuntimeActivity } from '../hooks/useAgentRuntimeActivity'
import AgentStatusBadge from './AgentStatusBadge'

// ── Chinese labels & workflow stages ──────────────────────

const CHINESE_LAYER_LABELS: Record<AgentLayer, string> = {
  supervisor: '编排层',
  data: '数据层',
  signal: '信号层',
  risk: '风控层',
  execution: '执行层',
  learning: '学习层',
}

const CHINESE_LAYER_DESC: Record<AgentLayer, string> = {
  supervisor: '主管 Agent 调度与决策编排',
  data: '新闻·市场·链上多源数据融合',
  signal: '信号生成、置信度计算与排序',
  risk: '头寸管理、风控规则与异常检测',
  execution: '下单、清算、资金适配与执行',
  learning: 'ML 模型更新、策略回测与优化',
}

const CHINESE_AGENT_LABELS: Record<string, string> = {
  orchestrator: '编排器',
  news_scanner: '新闻扫描',
  market_analyzer: '市场分析',
  signal_generator: '信号生成器',
  regime_detector: '市场体制识别',
  agent_m: '风控 Agent M',
  capital_adapter: '资金适配器',
  executor: '执行器',
  learner: '学习器',
}

const AGENT_WORKFLOW_STAGE: Record<string, { stage: number; total: number; label: string }> = {
  orchestrator: { stage: 1, total: 9, label: '初始信号编排' },
  news_scanner: { stage: 2, total: 9, label: '新闻采集与分析' },
  market_analyzer: { stage: 3, total: 9, label: '市场数据分析' },
  signal_generator: { stage: 4, total: 9, label: '信号生成' },
  regime_detector: { stage: 5, total: 9, label: '市场体制检测' },
  agent_m: { stage: 6, total: 9, label: '风控审核' },
  capital_adapter: { stage: 7, total: 9, label: '资金调配' },
  executor: { stage: 8, total: 9, label: '执行决策' },
  learner: { stage: 9, total: 9, label: '反馈学习' },
}

// ── Layout constants ───────────────────────────────────

const LAYER_Y: Record<AgentLayer, number> = {
  supervisor: 50,
  data: 210,
  signal: 390,
  risk: 570,
  execution: 750,
  learning: 930,
}

const LAYER_X_CENTER: Record<AgentLayer, number> = {
  supervisor: 540,
  data: 540,
  signal: 540,
  risk: 540,
  execution: 540,
  learning: 340,
}

const NODE_W = 260
const NODE_H = 112

// Static node positions within each layer
const SLOT_X: Record<string, number> = {
  // supervisor
  orchestrator: 540,
  // data layer — 2 agents side by side
  news_scanner: 310,
  market_analyzer: 770,
  // signal layer
  signal_generator: 540,
  // risk layer — 2 agents side by side
  regime_detector: 310,
  agent_m: 770,
  // execution layer — 2 agents side by side
  capital_adapter: 310,
  executor: 770,
  // learning layer
  learner: 310,
}

const LAYER_COLOR: Record<AgentLayer, string> = {
  supervisor: '#22d3ee',
  data: '#818cf8',
  signal: '#34d399',
  risk: '#f59e0b',
  execution: '#f472b6',
  learning: '#a78bfa',
}

const STATUS_COLOR: Record<string, string> = {
  running: '#3b82f6',
  completed: '#10b981',
  failed: '#ef4444',
  timeout: '#f59e0b',
  waiting: '#6366f1',
  initializing: '#a78bfa',
}

// Real activity status colors (idle/running/warning/error)
const REAL_STATUS_COLOR: Record<string, string> = {
  idle: '#475569',
  running: '#3b82f6',
  warning: '#f59e0b',
  error: '#ef4444',
}

const REAL_STATUS_LABEL: Record<string, string> = {
  idle: '空闲',
  running: '活跃',
  warning: '预警',
  error: '故障',
}

// ── Layer edges (static) ────────────────────────────────

const LAYER_EDGES = [
  { id: 'e-spv-data', source: 'orchestrator', target: 'news_scanner' },
  { id: 'e-spv-mkt', source: 'orchestrator', target: 'market_analyzer' },
  { id: 'e-spv-reg', source: 'orchestrator', target: 'regime_detector' },
  { id: 'e-news-sig', source: 'news_scanner', target: 'signal_generator' },
  { id: 'e-mkt-sig', source: 'market_analyzer', target: 'signal_generator' },
  { id: 'e-sig-m', source: 'signal_generator', target: 'agent_m' },
  { id: 'e-reg-cap', source: 'regime_detector', target: 'capital_adapter' },
  { id: 'e-m-cap', source: 'agent_m', target: 'capital_adapter' },
  { id: 'e-cap-exec', source: 'capital_adapter', target: 'executor' },
]

// ── Custom Agent Node ───────────────────────────────────

interface AgentNodeData {
  agent: RuntimeAgentState
  runtimeState?: AgentRuntimeStatus
  realActivity?: AgentRuntimeActivity
  activitySource?: 'real' | 'fallback'
  selected: boolean
  onSelect: (id: string | null) => void
  dimmed?: boolean
}

interface LayerLabelNodeData {
  layer: AgentLayer
  collapsed: boolean
  onToggleLayer?: (layer: AgentLayer) => void
}

function AgentNodeCard({ data }: NodeProps) {
  const d = data as unknown as AgentNodeData
  const { agent, runtimeState, realActivity, activitySource, selected, dimmed } = d

  // ── Determine display values ──────────────────────
  // When real activity is available, use it to override status + metrics
  const isReal = activitySource === 'real' && !!realActivity
  const realStatus = realActivity?.status ?? 'idle'

  // Status dot color: real activity takes priority
  const dotColor = isReal
    ? (REAL_STATUS_COLOR[realStatus] ?? '#475569')
    : (STATUS_COLOR[agent.status] ?? '#94a3b8')

  // Task display: real currentTask takes priority
  const displayTask = isReal && realActivity.currentTask
    ? realActivity.currentTask
    : undefined

  // Metrics row: real data or mock fallback
  const metricsDisplay = isReal
    ? {
        success: realActivity.successCount,
        failure: realActivity.failureCount,
        latency: realActivity.avgLatencyMs,
        throughput: realActivity.throughput,
      }
    : {
        tokens: agent.tokensUsed,
        latency: agent.latencyMs,
        rate: agent.successRate,
      }

  const chineseName = CHINESE_AGENT_LABELS[agent.id]
  const stage = AGENT_WORKFLOW_STAGE[agent.id]

  return (
    <div
      className={`
        relative rounded-lg border px-3 py-2.5 cursor-pointer transition-all duration-200
        ${selected ? 'border-cyan-400/70 bg-cyan-500/18 shadow-[0_0_12px_rgba(6,182,212,0.25)]' : 'border-slate-500/60 bg-slate-700/95'}
        ${dimmed ? 'opacity-30 scale-95' : 'opacity-100 scale-100'}
        hover:border-cyan-500/40 hover:bg-slate-700/80
      `}
      style={{ width: NODE_W, minHeight: NODE_H }}
      onClick={() => d.onSelect(d.agent.id)}
      title={chineseName ? `${chineseName} — ${stage?.label ?? ''}` : undefined}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-600 !w-2 !h-2 !border-slate-900" />
      <Handle type="source" position={Position.Bottom} className="!bg-slate-600 !w-2 !h-2 !border-slate-900" />

      {/* Status dot */}
      <div className="absolute top-2 right-2">
        <div
          className="w-2 h-2 rounded-full"
          style={{
            backgroundColor: dotColor,
            boxShadow: `0 0 6px ${dotColor}80`,
          }}
        />
      </div>

      {/* Agent name + Chinese label */}
      <div className="flex items-baseline gap-1 pr-4">
        <span className="text-sm font-bold font-mono text-slate-100 truncate">
          {agent.name}
        </span>
        {chineseName && (
          <span className="text-xs font-mono text-slate-200 truncate flex-shrink-0">
            {chineseName}
          </span>
        )}
      </div>

      {/* Workflow stage badge */}
      {stage && (
        <div className="absolute top-2 left-2">
          <span className="text-xs font-mono px-1.5 py-0.5 rounded leading-none border border-slate-500/60 bg-slate-600/90 text-slate-100"
            title={`工作流步骤 ${stage.stage}/${stage.total}: ${stage.label}`}
          >
            {stage.stage}/{stage.total}
          </span>
        </div>
      )}

      {/* Layer badge + real activity indicator */}
      <div className="flex items-center gap-1 mt-1">
        <span className="text-xs font-mono text-slate-200 uppercase">
          {LAYER_LABELS[agent.layer]}
        </span>
        {isReal && (
          <span className="text-xs font-mono font-bold px-1.5 py-0.5 rounded leading-none"
            style={{
              backgroundColor: REAL_STATUS_COLOR[realStatus] + '20',
              color: REAL_STATUS_COLOR[realStatus],
            }}
          >
            {REAL_STATUS_LABEL[realStatus] ?? realStatus.toUpperCase()}
          </span>
        )}
      </div>

      {/* Runtime state badge (only when no real activity) */}
      {!isReal && runtimeState && (
        <div className="mt-1">
          <AgentStatusBadge
            state={runtimeState.state}
            message={runtimeState.message}
          />
        </div>
      )}

      {/* Real activity task (when available) */}
      {displayTask && (
        <div className="mt-1 text-xs font-mono text-slate-100 truncate">
          {displayTask}
        </div>
      )}

      {/* Metrics row */}
      <div className="flex items-center gap-2 mt-1.5 text-xs font-mono text-slate-300">
        {isReal ? (
          <>
            <span title="成功 / 失败">
              <span className="text-emerald-400">{metricsDisplay.success ?? 0}</span>
              <span className="text-slate-600">/</span>
              <span className="text-red-400">{metricsDisplay.failure ?? 0}</span>
            </span>
            <span title="平均延迟">{metricsDisplay.latency ?? 0}ms</span>
            <span title="吞吐量">{metricsDisplay.throughput ?? 0}/s</span>
          </>
        ) : (
          <>
            <span>{(metricsDisplay as { tokens: number }).tokens}T</span>
            <span>{(metricsDisplay as { latency: number }).latency}ms</span>
            <span>{(metricsDisplay as { rate: number }).rate}%</span>
          </>
        )}
      </div>
    </div>
  )
}

function LayerLabelNode({ data }: NodeProps) {
  const d = data as unknown as LayerLabelNodeData
  const color = LAYER_COLOR[d.layer]

  return (
    <button
      type="button"
      className="flex items-center gap-2 rounded-md px-2 py-1 cursor-pointer transition-opacity hover:bg-slate-700/40"
      style={{ color, opacity: d.collapsed ? 0.35 : 0.82 }}
      onClick={() => d.onToggleLayer?.(d.layer)}
      title={CHINESE_LAYER_DESC[d.layer]}
    >
      <span
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ background: color, boxShadow: `0 0 8px ${color}80` }}
      />
      <span className={`text-sm font-mono font-bold uppercase whitespace-nowrap ${d.collapsed ? 'line-through' : ''}`}>
        {CHINESE_LAYER_LABELS[d.layer]}
      </span>
      {d.collapsed && <span className="text-sm font-mono text-slate-200">+</span>}
    </button>
  )
}

const nodeTypes = { agentNode: AgentNodeCard, layerLabel: LayerLabelNode }

// ── Props ───────────────────────────────────────────────

interface Props {
  selectedId: string | null
  onSelectAgent: (id: string | null) => void
  agentStates: AgentRuntimeStatus[]
  agentActivity?: AgentRuntimeActivity[]
  activitySource?: 'real' | 'fallback'
  collapsedLayers?: Set<AgentLayer>
  highlightedAgentIds?: Set<string>
  filterAgentIds?: string[] | null
  onToggleLayer?: (layer: AgentLayer) => void
  expanded?: boolean
  onRequestExpand?: () => void
  onRequestClose?: () => void
}

// ── Main Component ──────────────────────────────────────

export default function AgentTopology({
  selectedId,
  onSelectAgent,
  agentStates,
  agentActivity,
  activitySource,
  collapsedLayers = new Set(),
  highlightedAgentIds = new Set(),
  filterAgentIds = null,
  onToggleLayer,
  expanded = false,
  onRequestExpand,
  onRequestClose,
}: Props) {
  const snapshot = useRuntimeSnapshot()
  const agents = snapshot.agents

  // Build a lookup map for O(1) access
  const stateMap = useMemo(() => {
    const map = new Map<string, AgentRuntimeStatus>()
    for (const s of agentStates) map.set(s.agent, s)
    return map
  }, [agentStates])

  // Build activity lookup map from real data
  const activityMap = useMemo(() => {
    if (!agentActivity || agentActivity.length === 0) return null
    const map = new Map<string, AgentRuntimeActivity>()
    for (const a of agentActivity) map.set(a.id, a)
    return map
  }, [agentActivity])

  // Determine which agents are visible after applying filters
  const visibleAgentIds = useMemo(() => {
    // 1. Start with filterAgentIds if set (null = show all)
    const visible = filterAgentIds !== null
      ? new Set(filterAgentIds)
      : new Set(agents.map(a => a.id))

    // 2. Remove agents whose layer is collapsed
    if (collapsedLayers.size > 0) {
      for (const agent of agents) {
        if (collapsedLayers.has(agent.layer)) {
          visible.delete(agent.id)
        }
      }
    }

    return visible
  }, [agents, filterAgentIds, collapsedLayers])

  // Determine which agents should be dimmed (not in highlight set when highlight is active)
  const hasActiveHighlight = highlightedAgentIds.size > 0

  // Build nodes with fixed positions
  const allNodes = useMemo<Node[]>(
    () =>
      agents.map((agent) => {
        const visible = visibleAgentIds.has(agent.id)
        const dimmed = hasActiveHighlight && !highlightedAgentIds.has(agent.id)
        return {
          id: agent.id,
          type: 'agentNode',
          position: {
            x: (SLOT_X[agent.id] ?? LAYER_X_CENTER[agent.layer]) - NODE_W / 2,
            y: LAYER_Y[agent.layer],
          },
          hidden: !visible,
          data: {
            agent,
            runtimeState: stateMap.get(agent.id),
            realActivity: activityMap?.get(agent.id),
            activitySource,
            selected: selectedId === agent.id,
            onSelect: onSelectAgent,
            dimmed,
          } satisfies AgentNodeData,
          draggable: false,
          selectable: false,
          reconnectable: false as boolean,
        }
      }),
    [agents, stateMap, activityMap, activitySource, selectedId, onSelectAgent, visibleAgentIds, hasActiveHighlight, highlightedAgentIds],
  )

  // Build edges — only show edges where both ends are visible
  const edges = useMemo<Edge[]>(
    () =>
      LAYER_EDGES
        .filter((e) => visibleAgentIds.has(e.source) && visibleAgentIds.has(e.target))
        .map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          animated: true,
          style: {
            stroke: '#475569',
            strokeWidth: 1.5,
            strokeDasharray: '4 2',
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 10,
            height: 10,
            color: '#64748b',
          },
        })),
    [visibleAgentIds],
  )

  const layerLabelNodes = useMemo<Node[]>(
    () =>
      (['supervisor', 'data', 'signal', 'risk', 'execution', 'learning'] as AgentLayer[]).map((layer) => ({
        id: `layer-${layer}`,
        type: 'layerLabel',
        position: {
          x: expanded ? 10 : 0,
          y: LAYER_Y[layer] + NODE_H / 2 - 18,
        },
        data: {
          layer,
          collapsed: collapsedLayers.has(layer),
          onToggleLayer,
        } satisfies LayerLabelNodeData,
        draggable: false,
        selectable: false,
      })),
    [collapsedLayers, expanded, onToggleLayer],
  )

  const flowNodes = useMemo<Node[]>(() => [...layerLabelNodes, ...allNodes], [layerLabelNodes, allNodes])

  // Build expanded layout nodes with wider spacing
  const expandedNodes = useMemo<Node[]>(() => {
    if (!expanded) return flowNodes

    const scaleX = 1.35
    const scaleY = 1.4
    const offsetX = 80

    return flowNodes.map((n) => ({
      ...n,
      position: {
        x: n.type === 'layerLabel' ? n.position.x : (n.position.x + NODE_W / 2) * scaleX - NODE_W / 2 + offsetX,
        y: n.position.y * scaleY + 60,
      },
    }))
  }, [expanded, flowNodes])

  const displayNodes = expanded ? expandedNodes : flowNodes

  return (
    <div className="w-full h-full min-h-[500px] relative">
      {/* Header bar with expand/close buttons */}
      <div className="absolute top-2 right-2 z-20 flex items-center gap-1.5">
        {!expanded && onRequestExpand && (
          <button
            onClick={onRequestExpand}
            className="text-xs font-mono font-bold px-3 py-1.5 rounded-lg border border-cyan-400/50 bg-cyan-500/15 text-cyan-200 hover:bg-cyan-500/25 hover:border-cyan-400/70 transition-all shadow-[0_0_8px_rgba(6,182,212,0.15)]"
          >
            全屏拓扑
          </button>
        )}
        {expanded && onRequestClose && (
          <button
            onClick={onRequestClose}
            className="text-[11px] font-mono font-bold px-3 py-1.5 rounded-lg border border-slate-500/40 bg-slate-800/80 text-slate-300 hover:bg-slate-700/80 hover:border-slate-400/60 transition-all"
          >
            退出全屏
          </button>
        )}
      </div>

      {/* Title in expanded mode */}
      {expanded && (
        <div className="absolute top-2 left-4 z-20">
          <span className="text-sm font-bold font-mono text-cyan-300 bg-cyan-500/10 border border-cyan-500/30 px-3 py-1 rounded-lg">
            Agent Command Map
          </span>
        </div>
      )}

      <ReactFlow
        nodes={displayNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: expanded ? 0.12 : 0.18 }}
        defaultViewport={expanded ? { x: 0, y: 0, zoom: 0.65 } : { x: 0, y: 0, zoom: 0.7 }}
        minZoom={expanded ? 0.2 : 0.25}
        maxZoom={expanded ? 2.0 : 1.5}
        panOnDrag
        zoomOnScroll
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
        className="w-full h-full bg-[#16284d]"
        style={{ width: '100%', height: '100%' }}
      >
        <Background color="#334155" gap={20} size={1} />
        <Controls
          className="!bg-slate-700 !border-slate-500 !rounded-md"
          style={{
            '--xy-controls-button-background-color': '#334155',
            '--xy-controls-button-background-color-hover': '#475569',
            '--xy-controls-button-border': '1px solid #64748b',
          } as React.CSSProperties}
        />
      </ReactFlow>

    </div>
  )
}
