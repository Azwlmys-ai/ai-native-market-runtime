'use client'

// Trading decision chain steps
const tradingChain = [
  {
    step: '01',
    title: '机会发现',
    agent: 'Research',
    description: '实时扫描 Polymarket + OKX 价差，毫秒级捕捉跨市场套利窗口',
    metric: '< 50ms',
    metricLabel: '扫描延迟',
  },
  {
    step: '02',
    title: '信号合成',
    agent: 'Signal',
    description: '多维度合成交易信号：价差幅度、流动性深度、历史胜率、滑点预估',
    metric: '91.3%',
    metricLabel: '信号置信度',
  },
  {
    step: '03',
    title: '风控审查',
    agent: 'Risk',
    description: '实时检查仓位限额、最大回撤、单笔止损线，超阈值自动拦截',
    metric: '< 300ms',
    metricLabel: '风控延迟',
  },
  {
    step: '04',
    title: '执行决策',
    agent: 'Execution',
    description: '生成最优下单策略，分配资金，预估滑点，模拟执行（dry-run 模式）',
    metric: '2.1min',
    metricLabel: '审核通过到执行',
  },
  {
    step: '05',
    title: '复盘学习',
    agent: 'Learning',
    description: '记录每笔交易结果，更新信号权重，优化策略参数',
    metric: '78%',
    metricLabel: '策略胜率',
  },
]

const chainOutputs = [
  { label: '机会捕获率', value: '4.2x', detail: '从人工盯盘的 19% 提升至 80%' },
  { label: '端到端延迟', value: '47→0.8s', detail: '全链路自动决策减少 98.3%' },
  { label: '误报拦截率', value: '-72%', detail: '多 Agent 交叉验证替代单一阈值' },
  { label: 'Dry-Run 记录', value: '2h/6h/14h', detail: '三次持续 dry-run 零异常退出' },
]

const scenarios = [
  {
    title: '跨市场套利发现',
    tag: '核心场景',
    tagColor: 'bg-purple-500/15 text-purple-400 border-purple-500/25',
    highlight: true,
    desc: 'Polymarket 预测市场 + OKX 现货价差实时监控，毫秒级捕捉套利窗口。',
    kpi: '机会捕获 +4.2x · 延迟 < 50ms',
    cue: '这一页用于说明：系统能捕捉人工无法看到的价格窗口——3.2 秒窗口，机器可在 <50ms 内完成扫描。',
  },
  {
    title: '多 Agent 信号审查',
    tag: '已验证',
    tagColor: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/25',
    highlight: false,
    desc: 'Research → Signal → Risk 三层级联审查，自动过滤低质量信号，减少人工复核负担。',
    kpi: '审查效率 +340% · 误报率 -72%',
    cue: '这里可以强调：金融交易场景的核心是速度+准确性——多 Agent 交叉验证替代单一规则判断。',
  },
  {
    title: '自动风控与止损',
    tag: '风控核心',
    tagColor: 'bg-amber-500/15 text-amber-400 border-amber-500/25',
    highlight: false,
    desc: '动态止损线、仓位限额、最大回撤控制——Risk Agent 实时拦截超阈值订单。',
    kpi: '风险响应 < 300ms · 回撤控制 < 5%',
    cue: '',
  },
  {
    title: 'Dry-Run 稳定性验证',
    tag: '质量保证',
    tagColor: 'bg-blue-500/15 text-blue-400 border-blue-500/25',
    highlight: false,
    desc: '2h / 6h / 14h 连续 dry-run 测试，验证系统长时间运行的稳定性和信号一致性。',
    kpi: '14h 连续运行 · 零异常退出',
    cue: '',
  },
  {
    title: '实盘前运营监控',
    tag: '安全上线',
    tagColor: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
    highlight: false,
    desc: 'Runtime Mode 实时监控全部 Agent 状态、事件流、系统健康度——实盘前的最后验证。',
    kpi: '监控覆盖率 100% · 告警 < 1s',
    cue: '',
  },
]

export default function ExecutiveScenarios() {
  return (
    <div className="flex-shrink-0 px-6 py-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[9px] font-mono text-purple-400 bg-purple-500/10 border border-purple-500/20 px-1.5 py-0.5 rounded">
          交易系统能力
        </span>
        <span className="text-[11px] font-mono text-slate-500">
          Polymarket 跨市场套利 · 多 Agent 协同 · 全链路风控
        </span>
      </div>

      {/* Scenario Cards Grid */}
      <div className="grid grid-cols-5 gap-3 mb-4">
        {scenarios.map((scenario) => (
          <div
            key={scenario.title}
            className={`rounded-lg border p-3 backdrop-blur-sm flex flex-col
              ${scenario.highlight
                ? 'border-purple-500/30 bg-purple-500/5 ring-1 ring-purple-500/10'
                : 'border-white/[0.04] bg-slate-900/20'
              }`}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${scenario.tagColor}`}
              >
                {scenario.tag}
              </span>
            </div>
            <span className="text-[11px] font-bold font-mono text-slate-300 mb-1">
              {scenario.title}
            </span>
            <p className="text-[9px] font-mono text-slate-500 leading-relaxed mb-2 flex-1">
              {scenario.desc}
            </p>
            <div className="border-t border-white/[0.04] pt-1.5">
              <p className="text-[9px] font-bold font-mono text-slate-400">{scenario.kpi}</p>
            </div>
            {scenario.cue && (
              <div className="mt-2 pt-1.5 border-t border-white/[0.03]">
                <p className="text-[8px] font-mono text-slate-700 italic leading-snug">
                  💬 {scenario.cue}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Trading Decision Chain Deep Dive */}
      <div className="rounded-xl border border-purple-500/25 bg-purple-500/3 p-5 backdrop-blur-sm">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-[10px] font-bold font-mono text-purple-400 uppercase tracking-widest">
            🔬 交易决策链路深挖：从价差到执行
          </span>
          <span className="text-[9px] font-mono text-purple-500/60 border border-purple-500/20 px-1.5 py-0.5 rounded">
            全链路自动化
          </span>
        </div>

        {/* 5-Step Chain */}
        <div className="relative mb-5">
          {/* Connecting line */}
          <div className="absolute top-8 left-8 right-8 h-[1px] bg-gradient-to-r from-purple-500/30 via-fuchsia-500/20 to-pink-500/30" />

          <div className="relative grid grid-cols-5 gap-3">
            {tradingChain.map((item, idx) => (
              <div key={item.step} className="flex flex-col items-center">
                {/* Step Circle */}
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center text-[11px] font-bold font-mono border-2 mb-2
                    ${idx === 0 ? 'bg-purple-500/20 border-purple-400 text-purple-400' : ''}
                    ${idx === 1 ? 'bg-fuchsia-500/20 border-fuchsia-400 text-fuchsia-400' : ''}
                    ${idx === 2 ? 'bg-pink-500/20 border-pink-400 text-pink-400' : ''}
                    ${idx === 3 ? 'bg-rose-500/20 border-rose-400 text-rose-400' : ''}
                    ${idx === 4 ? 'bg-amber-500/20 border-amber-400 text-amber-400' : ''}
                  `}
                >
                  {item.step}
                </div>

                {/* Content */}
                <div className="text-center flex-1">
                  <p className="text-[10px] font-bold font-mono text-slate-300 mb-0.5">{item.title}</p>
                  <p className="text-[8px] font-mono text-purple-400/80 mb-1">
                    {item.agent}
                  </p>
                  <p className="text-[8px] font-mono text-slate-600 leading-relaxed mb-1.5">
                    {item.description}
                  </p>
                  <p className="text-sm font-bold font-mono text-slate-200">{item.metric}</p>
                  <p className="text-[8px] font-mono text-slate-600">{item.metricLabel}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Chain Output Grid */}
        <div className="grid grid-cols-4 gap-3 border-t border-purple-500/15 pt-4">
          {chainOutputs.map((output) => (
            <div
              key={output.label}
              className="rounded-lg bg-slate-900/40 border border-white/[0.04] p-3 text-center"
            >
              <p className="text-[9px] font-mono text-slate-500 mb-1">{output.label}</p>
              <p className="text-base font-bold font-mono text-purple-400">{output.value}</p>
              <p className="text-[8px] font-mono text-slate-600 mt-0.5">{output.detail}</p>
            </div>
          ))}
        </div>

        {/* Dry-Run Verification Note */}
        <div className="mt-4 flex items-center gap-3 bg-purple-500/10 rounded-lg border border-purple-500/20 px-4 py-2">
          <span className="text-[9px] font-mono text-purple-400 whitespace-nowrap">Dry-Run 验证</span>
          <div className="flex items-center gap-4 text-[9px] font-mono">
            <span className="text-slate-400">
              2h dry-run ≈ <span className="text-emerald-400 font-bold">¥12K</span> 机会价值识别
            </span>
            <span className="text-slate-400">
              6h dry-run ≈ <span className="text-emerald-400 font-bold">¥38K</span> 累积套利机会
            </span>
            <span className="text-slate-400">
              14h dry-run ≈ <span className="text-emerald-400 font-bold">¥96K</span> 全天候价值捕获
            </span>
          </div>
        </div>

        {/* Presentation Cue */}
        <div className="mt-3">
          <p className="text-[8px] font-mono text-slate-700 italic leading-snug">
            💬 这里可以对老板说：交易决策全链路已跑通从机会发现到复盘学习的完整闭环，
            同一套架构只需更换数据源即可扩展到其他交易市场——架构已具备跨市场迁移能力。
          </p>
        </div>
      </div>
    </div>
  )
}