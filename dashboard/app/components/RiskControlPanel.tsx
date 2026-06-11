'use client'

import { useRuntimeSnapshot } from '../data/runtimeState'
import { mockRiskState, mockCapitalAllocations } from '../data/mockRisk'

export default function RiskControlPanel() {
  const snapshot = useRuntimeSnapshot()
  const liveRegime = snapshot.metrics.riskRegime
  const r = mockRiskState

  return (
    <div className="space-y-3 text-xs font-mono">
      {/* Regime — live from runtime */}
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5">
        <p className="text-slate-400 uppercase tracking-widest text-xs mb-1">市场状态</p>
        <p className="text-amber-400 font-bold text-sm">{liveRegime}</p>
        <div className="flex justify-between mt-1 text-slate-400">
          <span>置信度: {r.regimeConfidence}%</span>
          <span>系数: ×{r.regimeScalar}</span>
        </div>
      </div>

      {/* Capital */}
      <div className="bg-slate-800/50 border border-white/[0.04] rounded-lg p-2.5">
        <p className="text-slate-400 uppercase tracking-widest text-xs mb-1.5">资金</p>
        <div className="space-y-1 text-slate-300">
          <div className="flex justify-between"><span>总额</span><span className="text-white">${r.totalCapital.toLocaleString()}</span></div>
          <div className="flex justify-between"><span>已部署</span><span className="text-slate-300">${r.deployedCapital.toLocaleString()}</span></div>
          <div className="flex justify-between"><span>储备金</span><span className="text-emerald-400 font-semibold">${r.reserveCash.toLocaleString()}</span></div>
          <div className="flex justify-between"><span>capital_adapter</span>
            <span className="text-amber-400">⚠ TIMEOUT</span>
          </div>
        </div>
      </div>

      {/* Exposure */}
      <div className="bg-slate-800/50 border border-white/[0.04] rounded-lg p-2.5">
        <p className="text-slate-400 uppercase tracking-widest text-xs mb-1.5">敞口</p>
        <div className="space-y-1">
          <div className="flex justify-between text-slate-400">
            <span>BTC</span><span className="text-slate-600">$0</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>ETH</span><span className="text-slate-600">$0</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>SOL</span><span className="text-slate-600">$0</span>
          </div>
          <div className="flex justify-between text-slate-300 mt-1 border-t border-slate-700 pt-1">
            <span>合计</span><span className="text-slate-600">$0</span>
          </div>
        </div>
      </div>

      {/* Capital Allocations */}
      <div>
        <p className="text-slate-400 uppercase tracking-widest text-xs mb-1.5">分配 (模拟运行)</p>
        <div className="space-y-1">
          {mockCapitalAllocations.slice(-5).map((a, i) => (
            <div key={i} className={`flex items-center justify-between rounded px-2 py-1 ${
              a.status === 'EXECUTED_DRY' ? 'bg-emerald-500/10 text-emerald-400' :
              a.status === 'TIMEOUT' ? 'bg-amber-500/10 text-amber-400' :
              'bg-slate-700/30 text-slate-500'
            }`}>
              <span>C#{a.cycleId} {a.asset.split(' ')[0]}</span>
              <span>{a.status === 'EXECUTED_DRY' ? `$${a.allocationUSD}` : a.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}