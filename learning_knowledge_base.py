"""
学习成果知识库
从 Agent G 的复盘报告中提取的可操作规则
用于决策层（Agent B/K）和反对层（Agent M）
"""

import json
from pathlib import Path
from datetime import datetime

class LearningKnowledgeBase:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        
        # 加载最新学习报告
        self.learning_report = self._load_learning_report()
    
    def _load_learning_report(self):
        """加载最新学习报告"""
        report_file = self.data_dir / "learning_report.json"
        
        if not report_file.exists():
            return None
        
        try:
            with open(report_file, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def get_market_whitelist(self):
        """
        获取高胜率市场白名单
        用于决策层：优先生成这些类型的信号
        """
        return {
            "high_priority": [
                "NHL Stanley Cup",
                "NBA Finals",
                "体育冠军市场（规则清晰、长期概率极端）"
            ],
            "characteristics": [
                "规则清晰、信息结构稳定、结果可验证",
                "高流动性（订单簿深度 > $10k）",
                "极端定价区间（价格 > 0.8 或 < 0.2）",
                "时间窗口明确（非长期叙事驱动）"
            ],
            "avoid": [
                "加密空投市场",
                "娱乐八卦/名人事件",
                "地缘政治长期事件",
                "法律案件（规则模糊）"
            ]
        }
    
    def get_pricing_rules(self):
        """
        获取定价规则
        用于决策层：生成信号时的价格约束
        """
        return {
            "optimal_zones": [
                {
                    "direction": "NO",
                    "price_range": [0.85, 0.97],
                    "reason": "高价 NO 策略：卖出极低概率事件的 YES，容错高"
                },
                {
                    "direction": "YES",
                    "price_range": [0.03, 0.15],
                    "reason": "低价 YES 策略：买入被低估的事件，赔率优势明显"
                }
            ],
            "danger_zones": [
                {
                    "price_range": [0.40, 0.60],
                    "reason": "中间价位风险高：概率边际优势不足，容易被事件进展反杀",
                    "action": "需要极强的信息优势才能交易"
                }
            ],
            "ev_threshold": {
                "minimum": 0.20,  # EV > 20%
                "recommended": 0.40,  # EV > 40% 更安全
                "formula": "p > 1/(1 + price/(1-price))"
            }
        }
    
    def get_execution_rules(self):
        """
        获取执行规则
        用于反对层：审查信号时的执行风险评估
        """
        return {
            "liquidity_requirements": {
                "minimum_depth": 10000,  # $10k
                "max_slippage": 0.05,  # 5%
                "max_levels": 2,  # 最多吃 2 层订单簿
                "reason": "多层扫单导致高滑点，执行质量差"
            },
            "position_sizing": {
                "low_confidence": [25, 50],  # $25-50
                "medium_confidence": [50, 100],  # $50-100
                "high_confidence": [100, 200],  # $100-200
                "max_single_position": 200,
                "reason": "小仓位更稳健，避免情绪化加仓"
            },
            "concentration_limits": {
                "max_same_theme": 5,  # 同一主题最多 5 个仓位
                "max_correlated_exposure": 0.30,  # 相关性敞口 < 30%
                "reason": "避免在同类市场集中暴露（如 GTA VI 相关性风险）"
            }
        }
    
    def get_data_source_rules(self):
        """
        获取数据源规则
        用于决策层：评估数据源可靠性
        """
        return {
            "reliable_sources": [
                "官方赛事 API（NBA/NHL/MLB）",
                "FRED（美联储经济数据）",
                "CME FedWatch（利率期货）",
                "链上数据（Glassnode/Nansen）",
                "财报数据（公司 IR）"
            ],
            "unreliable_sources": [
                "静态赛季前体育分析（未接入实时 API）",
                "未经验证的宏观金融指标（BTC 资金费率）",
                "法律事件市场的模糊规则解释",
                "社交媒体情绪（Twitter/Reddit）"
            ],
            "verification_requirements": {
                "time_sensitive": "必须接入实时 API",
                "causal_relationship": "需要 Granger 检验或领域专家验证",
                "price_impact": "需要量化传导机制"
            }
        }
    
    def get_rejection_criteria(self):
        """
        获取拒绝标准
        用于反对层：增强审查逻辑
        """
        return {
            "auto_reject": [
                {
                    "condition": "市场类型在黑名单",
                    "blacklist": ["加密空投", "娱乐八卦", "地缘政治"],
                    "reason": "历史胜率低、信息噪音高"
                },
                {
                    "condition": "价格在危险区间且无强信息优势",
                    "range": [0.40, 0.60],
                    "reason": "中间价位风险收益比差"
                },
                {
                    "condition": "预期滑点 > 10%",
                    "reason": "执行成本过高"
                },
                {
                    "condition": "数据源不可靠",
                    "reason": "未经验证的数据源"
                }
            ],
            "warning_flags": [
                {
                    "condition": "同主题仓位 > 3",
                    "action": "降低仓位或要求更高置信度"
                },
                {
                    "condition": "流动性 < $10k",
                    "action": "限制仓位 < $50"
                },
                {
                    "condition": "时间敏感信息未实时验证",
                    "action": "要求提供实时数据源"
                }
            ]
        }
    
    def get_causal_validation_rules(self):
        """
        获取因果验证规则
        用于决策层：避免逻辑链条污染
        """
        return {
            "valid_causal_chains": [
                {
                    "from": "美联储降息",
                    "to": "风险资产上涨",
                    "mechanism": "流动性宽松 → 资金成本下降 → 估值提升",
                    "validation": "历史数据回测 + 利率传导模型"
                },
                {
                    "from": "BTC 减半",
                    "to": "BTC 价格上涨",
                    "mechanism": "供应减少 → 供需失衡 → 价格上涨",
                    "validation": "历史周期分析（样本量 >= 3）"
                }
            ],
            "invalid_causal_chains": [
                {
                    "from": "BTC 资金费率",
                    "to": "Polymarket 特定事件结果",
                    "reason": "弱相关变量，缺乏因果验证"
                },
                {
                    "from": "短期技术突破",
                    "to": "长期价格目标",
                    "reason": "期限错配，缺少中间传导机制"
                }
            ],
            "validation_methods": [
                "Granger 因果检验",
                "领域专家白名单",
                "历史事件回测（样本量 >= 10）",
                "因果图模块（DAG）"
            ]
        }
    
    def generate_decision_prompt_enhancement(self):
        """
        生成决策层 prompt 增强
        用于 Agent B/K：在生成信号时注入学习成果
        """
        whitelist = self.get_market_whitelist()
        pricing = self.get_pricing_rules()
        data_sources = self.get_data_source_rules()
        
        return f"""
## 学习成果指导（基于历史交易复盘）

### 优先市场类型
{json.dumps(whitelist['high_priority'], indent=2, ensure_ascii=False)}

### 避免市场类型
{json.dumps(whitelist['avoid'], indent=2, ensure_ascii=False)}

### 最优定价区间
- NO 方向：价格 > 0.85（高价 NO 策略）
- YES 方向：价格 < 0.15（低价 YES 策略）
- 避免：0.40-0.60 中间价位（除非有极强信息优势）

### 数据源要求
可靠来源：{', '.join(data_sources['reliable_sources'][:3])}
避免使用：{', '.join(data_sources['unreliable_sources'][:2])}

### EV 要求
- 最低 EV > 20%
- 推荐 EV > 40%
- 公式：p > 1/(1 + price/(1-price))
"""
    
    def generate_rejection_prompt_enhancement(self):
        """
        生成反对层 prompt 增强
        用于 Agent M：在审查信号时注入学习成果
        """
        execution = self.get_execution_rules()
        rejection = self.get_rejection_criteria()
        
        return f"""
## 学习成果指导（基于历史交易复盘）

### 自动拒绝条件
1. 市场类型在黑名单：加密空投、娱乐八卦、地缘政治
2. 价格在 0.40-0.60 且无强信息优势
3. 预期滑点 > 10%
4. 数据源不可靠（未经验证）

### 流动性要求
- 最低订单簿深度：$10,000
- 最大滑点：5%
- 最多吃单层数：2 层

### 仓位管理
- 低置信度：$25-50
- 中置信度：$50-100
- 高置信度：$100-200
- 同主题最多 5 个仓位

### 警告标志
- 同主题仓位 > 3：降低仓位或要求更高置信度
- 流动性 < $10k：限制仓位 < $50
- 时间敏感信息未实时验证：要求提供实时数据源
"""
    
    def export_knowledge_base(self):
        """导出完整知识库"""
        kb = {
            "timestamp": datetime.now().isoformat(),
            "version": "1.0",
            "market_whitelist": self.get_market_whitelist(),
            "pricing_rules": self.get_pricing_rules(),
            "execution_rules": self.get_execution_rules(),
            "data_source_rules": self.get_data_source_rules(),
            "rejection_criteria": self.get_rejection_criteria(),
            "causal_validation_rules": self.get_causal_validation_rules(),
            "decision_prompt_enhancement": self.generate_decision_prompt_enhancement(),
            "rejection_prompt_enhancement": self.generate_rejection_prompt_enhancement()
        }
        
        output_file = self.data_dir / "learning_knowledge_base.json"
        with open(output_file, 'w') as f:
            json.dump(kb, f, indent=2, ensure_ascii=False)
        
        return output_file

def main():
    kb = LearningKnowledgeBase()
    output_file = kb.export_knowledge_base()
    
    print("=" * 60)
    print("学习成果知识库生成完成")
    print("=" * 60)
    print(f"输出文件: {output_file}")
    print()
    
    print("📊 知识库内容:")
    print("  ✅ 市场白名单（优先/避免）")
    print("  ✅ 定价规则（最优区间/危险区间）")
    print("  ✅ 执行规则（流动性/仓位/集中度）")
    print("  ✅ 数据源规则（可靠/不可靠）")
    print("  ✅ 拒绝标准（自动拒绝/警告标志）")
    print("  ✅ 因果验证规则（有效/无效链条）")
    print()
    
    print("🔧 集成方式:")
    print("  1. 决策层（Agent B/K）：在生成信号时注入市场白名单、定价规则、数据源规则")
    print("  2. 反对层（Agent M）：在审查信号时注入执行规则、拒绝标准")
    print("  3. 自动更新：Agent G 每次复盘后自动更新知识库")

if __name__ == "__main__":
    main()
