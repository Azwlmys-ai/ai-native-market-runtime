'use client'

const phases = [
  {
    id: '01',
    title: '交易痛点',
    shortTitle: '痛点',
    description:
      'Polymarket + OKX 跨市场套利靠人工盯盘，价差窗口平均仅 3.2 秒，人工无法及时捕捉；信号审查依赖经验判断，高频机会大量流失。',
    metric: '3.2s',
    metricLabel: '平均价差窗口',
    cue: '这一页回答"为什么要投"——把老板拉进真实的量化交易运营痛点场景。',
  },
  {
    id: '02',
    title: 'Agent 编排',
    shortTitle: '编排',
    description:
      '研究 → 信号 → 风控 → 执行 → 学习，五大 Agent 层级自动化交易决策全链路，每个 Agent 对应一个专业岗位。',
    metric: '5 层',
    metricLabel: '智能体层级',
    cue: '这里强调：不是单一 AI 策略，而是多 Agent 分工协作——Research 挖机会、Risk 控风险、Execution 管理订单。',
  },
  {
    id: '03',
    title: '自动决策',
    shortTitle: '决策',
    description:
      '高频价差扫描、多维度信号合成、实时风控拦截、自动下单——从发现价差到执行决策全链路无人干预。',
    metric: '< 800ms',
    metricLabel: '端到端延迟',
    cue: '关键数字：从价差发现到风控决策，全程机器人完成，交易员只需确认关键参数。',
  },
  {
    id: '04',
    title: '可量化收益',
    shortTitle: '收益',
    description:
      '机会捕获率 +4.2x，信号审查效率 +320%，人工盯盘成本 -68%，全年净节省运营成本 ¥2.5M+。',
    metric: '+4.2x',
    metricLabel: '机会捕获率提升',
    cue: '所有数字均有 dry-run 数据和 Runtime 模式支撑，可以现场切换到 Runtime 模式验证系统在跑。',
  },
  {
    id: '05',
    title: '可复制场景',
    shortTitle: '复制',
    description:
      'Polymarket 套利验证成熟后，同一架构可快速扩展到跨 CEX/DEX 套利、期货基差套利、跨链 MEV 等多场景。',
    metric: '5+',
    metricLabel: '可扩展场景',
    cue: '这里可以对老板说：系统架构具备跨市场迁移能力——Polymarket 跑通了，OKX 现货/合约只是换数据源。',
  },
]

export default function ExecutiveNarrativeStrip() {
  return (
    <div className="flex-shrink-0 px-6 py-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[9px] font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-1.5 py-0.5 rounded">
          演示叙事线
        </span>
        <span className="text-[11px] font-mono text-slate-500">
          问题 → 方案 → 价值 → 场景 → ROI — 5 分钟汇报结构
        </span>
      </div>

      {/* Narrative Progress Bar */}
      <div className="relative mb-4">
        <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-gradient-to-r from-cyan-500/40 via-purple-500/30 to-emerald-500/40 -translate-y-1/2" />
        <div className="relative flex justify-between">
          {phases.map((phase, idx) => (
            <div key={phase.id} className="flex flex-col items-center gap-1.5">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold font-mono border-2
                  ${idx === 0 ? 'bg-cyan-500/20 border-cyan-400 text-cyan-400' : ''}
                  ${idx === 1 ? 'bg-blue-500/20 border-blue-400 text-blue-400' : ''}
                  ${idx === 2 ? 'bg-purple-500/20 border-purple-400 text-purple-400' : ''}
                  ${idx === 3 ? 'bg-emerald-500/20 border-emerald-400 text-emerald-400' : ''}
                  ${idx === 4 ? 'bg-amber-500/20 border-amber-400 text-amber-400' : ''}
                `}
              >
                {phase.id}
              </div>
              <span className="text-[9px] font-mono text-slate-500 text-center leading-tight">
                {phase.shortTitle}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Detail Cards Grid */}
      <div className="grid grid-cols-5 gap-3">
        {phases.map((phase, idx) => {
          const borders = [
            'border-cyan-500/20',
            'border-blue-500/20',
            'border-purple-500/20',
            'border-emerald-500/20',
            'border-amber-500/20',
          ]
          const metricColors = [
            'text-cyan-400',
            'text-blue-400',
            'text-purple-400',
            'text-emerald-400',
            'text-amber-400',
          ]
          const bgColors = [
            'bg-cyan-500/3',
            'bg-blue-500/3',
            'bg-purple-500/3',
            'bg-emerald-500/3',
            'bg-amber-500/3',
          ]

          return (
            <div
              key={phase.id}
              className={`rounded-lg border ${borders[idx]} ${bgColors[idx]} p-3 flex flex-col backdrop-blur-sm`}
            >
              <span className="text-[10px] font-bold font-mono text-slate-300 mb-1">{phase.title}</span>
              <p className="text-[9px] font-mono text-slate-500 leading-relaxed mb-2 flex-1">
                {phase.description}
              </p>
              <div className="border-t border-white/[0.04] pt-1.5">
                <p className={`text-lg font-bold font-mono ${metricColors[idx]}`}>{phase.metric}</p>
                <p className="text-[8px] font-mono text-slate-600">{phase.metricLabel}</p>
              </div>
              {/* Presentation Cue */}
              <div className="mt-2 pt-1.5 border-t border-white/[0.03]">
                <p className="text-[8px] font-mono text-slate-700 italic leading-snug">
                  💬 {phase.cue}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}