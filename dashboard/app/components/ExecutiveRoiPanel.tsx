'use client'

export default function ExecutiveRoiPanel() {
  return (
    <div className="flex-shrink-0 px-6 py-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded">
          投资回报
        </span>
        <span className="text-[11px] font-mono text-slate-500">
          基于 Polymarket 跨市场套利系统的投入产出简化模型
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Current Cost */}
        <div className="space-y-3">
          <div className="rounded-lg border border-red-500/15 bg-red-500/3 p-4 backdrop-blur-sm">
            <p className="text-[9px] font-mono text-red-400/70 uppercase tracking-widest mb-3">
              ▼ 当前年度运营成本
            </p>

            <RoiLine
              label="人工盯盘成本"
              value="¥960,000"
              detail="5 人 × 3 班制 × ¥64K 年薪"
              color="red"
            />
            <RoiLine
              label="机会漏失损失"
              value="¥3,200,000"
              detail="价差窗口 3.2s，人工捕获率仅 19%"
              color="red"
            />
            <RoiLine
              label="风控延迟损失"
              value="¥480,000"
              detail="人工审核平均延迟 47s"
              color="red"
            />

            <div className="mt-3 pt-2 border-t border-red-500/15">
              <RoiLine
                label="当前年度总成本"
                value="¥4,640,000"
                detail=""
                color="red"
                bold
              />
            </div>
          </div>

          <div className="rounded-lg border border-slate-500/15 bg-slate-500/3 p-4 backdrop-blur-sm">
            <p className="text-[9px] font-mono text-slate-400/70 uppercase tracking-widest mb-3">
              ▼ 系统建设与运维
            </p>

            <RoiLine
              label="Agent 系统建设"
              value="¥400,000"
              detail="一次性部署 + 数据源接入"
              color="slate"
            />
            <RoiLine
              label="年度运维费用"
              value="¥200,000"
              detail="云资源 + 模型调用 + 数据订阅"
              color="slate"
            />

            <div className="mt-3 pt-2 border-t border-slate-500/15">
              <RoiLine
                label="年度总投入"
                value="¥600,000"
                detail="首年含建设费用"
                color="slate"
                bold
              />
            </div>
          </div>
        </div>

        {/* Savings */}
        <div className="rounded-lg border border-emerald-500/15 bg-emerald-500/3 p-4 backdrop-blur-sm">
          <p className="text-[9px] font-mono text-emerald-400/70 uppercase tracking-widest mb-3">
            ▲ 自动化节省
          </p>

          <RoiLine
            label="人工盯盘缩减"
            value="¥672,000"
            detail="盯盘人力下降 70%"
            color="emerald"
          />
          <RoiLine
            label="机会捕获增量"
            value="¥2,624,000"
            detail="捕获率 19%→80%，年增收"
            color="emerald"
          />
          <RoiLine
            label="风控响应加速"
            value="¥360,000"
            detail="延迟从 47s 降至 <800ms"
            color="emerald"
          />

          <div className="mt-4 pt-3 border-t border-emerald-500/15">
            <RoiLine
              label="年度总节省"
              value="¥3,656,000"
              detail=""
              color="emerald"
              bold
              large
            />
          </div>

          <div className="mt-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3">
            <p className="text-[8px] font-mono text-emerald-400/70 uppercase tracking-wider mb-1">
              净收益计算
            </p>
            <p className="text-[9px] font-mono text-slate-500 leading-relaxed">
              ¥3,656,000 (节省) - ¥600,000 (投入) ={' '}
              <span className="text-emerald-400 font-bold text-sm">
                ¥3,056,000
              </span>
            </p>
            <p className="text-[8px] font-mono text-slate-600 mt-1">
              ROI: 509% · 投资回收期: 约 2.4 个月
            </p>
          </div>
        </div>

        {/* Key Metrics Card */}
        <div className="space-y-3">
          <div className="rounded-lg border border-cyan-500/15 bg-cyan-500/3 p-4 backdrop-blur-sm flex-1">
            <p className="text-[9px] font-mono text-cyan-400/70 uppercase tracking-widest mb-4">
              核心指标摘要
            </p>
            <div className="space-y-3">
              <MetricSummary
                label="投资回收期"
                value="2.4 个月"
                subtitle="首年含一次性建设成本"
                good
              />
              <MetricSummary
                label="第一年 ROI"
                value="509%"
                subtitle="含部署+运维全成本"
                good
              />
              <MetricSummary
                label="年度净节省"
                value="¥3.06M"
                subtitle="机会捕获增量 + 人力节省"
                good
              />
              <MetricSummary
                label="人力释放"
                value="3.5 FTE"
                subtitle="可转向策略研发与风险建模"
                good
              />
              <MetricSummary
                label="5 年累计净现值"
                value="¥14.1M"
                subtitle="保守折现率 8%"
                good
              />
            </div>
          </div>

          {/* Presentation Cue */}
          <div className="rounded-lg border border-white/[0.03] bg-slate-900/20 p-3">
            <p className="text-[8px] font-mono text-slate-700 italic leading-snug">
              💬 这一页用于说明：系统不是成本中心，而是利润中心——投入 ¥60 万/年，节省 ¥306 万/年，
              2.4 个月回本。从人工盯盘的 19% 机会捕获率提升到 80%，每 1 元的系统投入产出 5.1 元的收益。
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function RoiLine({
  label,
  value,
  detail,
  color,
  bold,
  large,
}: {
  label: string
  value: string
  detail: string
  color: string
  bold?: boolean
  large?: boolean
}) {
  const colorMap: Record<string, string> = {
    red: 'text-red-400/90',
    emerald: 'text-emerald-400/90',
    slate: 'text-slate-400/90',
  }

  return (
    <div className="flex justify-between items-baseline py-1">
      <div className="flex flex-col">
        <span
          className={`text-[10px] font-mono ${bold ? 'text-slate-300 font-bold' : 'text-slate-500'}`}
        >
          {label}
        </span>
        {detail && (
          <span className="text-[8px] font-mono text-slate-700">{detail}</span>
        )}
      </div>
      <span
        className={`font-mono ${colorMap[color] ?? 'text-slate-400'} ${large ? 'text-base' : 'text-[11px]'} ${bold ? 'font-bold' : ''}`}
      >
        {value}
      </span>
    </div>
  )
}

function MetricSummary({
  label,
  value,
  subtitle,
  good,
}: {
  label: string
  value: string
  subtitle: string
  good?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between">
      <div>
        <span className="text-[10px] font-mono text-slate-400">{label}</span>
        <p className="text-[8px] font-mono text-slate-600 mt-0.5">{subtitle}</p>
      </div>
      <span className={`text-sm font-bold font-mono ${good ? 'text-emerald-400' : 'text-slate-400'}`}>
        {value}
      </span>
    </div>
  )
}