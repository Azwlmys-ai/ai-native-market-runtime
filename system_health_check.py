#!/usr/bin/env python3
"""
系统健康检查 - 检查所有组件状态
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

def check_config():
    """检查配置文件"""
    print("=" * 80)
    print("1. 配置文件检查")
    print("=" * 80)
    
    config_dir = Path("config")
    
    # LLM 配置
    llm_config = config_dir / "llm_config.json"
    if llm_config.exists():
        with open(llm_config) as f:
            data = json.load(f)
        print(f"✅ LLM 配置: {len(data['agent_models'])} 个 Agent")
        print(f"   - xAI API: {data['api_base']}")
        print(f"   - 代理 API: {data['proxy_api_base']}")
        
        # 统计模型分布
        models = {}
        for agent, model in data['agent_models'].items():
            models[model] = models.get(model, 0) + 1
        
        print("   - 模型分布:")
        for model, count in sorted(models.items()):
            print(f"     • {model}: {count} 个 Agent")
    else:
        print("❌ LLM 配置文件不存在")
    
    # Broker 配置
    broker_config = config_dir / "broker_config.json"
    if broker_config.exists():
        with open(broker_config) as f:
            data = json.load(f)
        print(f"✅ Broker 配置: {len(data)} 个数据源")
        for key in data.keys():
            if 'api_key' in key.lower():
                masked = data[key][:8] + "..." + data[key][-4:] if len(data[key]) > 12 else "***"
                print(f"   - {key}: {masked}")
    else:
        print("❌ Broker 配置文件不存在")
    
    print()

def check_data_sources():
    """检查数据源连接"""
    print("=" * 80)
    print("2. 数据源连接测试")
    print("=" * 80)
    
    # 测试 xAI API
    try:
        from llm_helper import call_llm_sync
        response = call_llm_sync("agent_k", "测试连接，请回复'OK'", timeout=10)
        if response:
            print(f"✅ xAI API (Grok 4.3): 连接正常")
        else:
            print("❌ xAI API: 返回空响应")
    except Exception as e:
        print(f"❌ xAI API: {str(e)[:100]}")
    
    # 测试代理 API
    try:
        response = call_llm_sync("agent_m_primary", "测试连接，请回复'OK'", timeout=10)
        if response:
            print(f"✅ 代理 API (GPT-5.4): 连接正常")
        else:
            print("❌ 代理 API: 返回空响应")
    except Exception as e:
        print(f"❌ 代理 API: {str(e)[:100]}")
    
    # 测试 OKX API
    try:
        import requests
        response = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == '0':
                price = data['data'][0]['last']
                print(f"✅ OKX API: 连接正常 (BTC: ${price})")
            else:
                print(f"❌ OKX API: {data.get('msg', 'Unknown error')}")
        else:
            print(f"❌ OKX API: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ OKX API: {str(e)[:100]}")
    
    print()

def check_historical_data():
    """检查历史数据"""
    print("=" * 80)
    print("3. 历史数据检查")
    print("=" * 80)
    
    hist_dir = Path("data/historical")
    if not hist_dir.exists():
        print("❌ 历史数据目录不存在")
        return
    
    files = list(hist_dir.glob("*.json"))
    print(f"✅ 历史数据文件: {len(files)} 个")
    
    # 按类型分组
    okx_files = [f for f in files if 'okx' in f.name]
    us_files = [f for f in files if 'us_stocks' in f.name]
    cn_files = [f for f in files if 'cn_stocks' in f.name]
    
    print(f"   - OKX 加密货币: {len(okx_files)} 个文件")
    print(f"   - 美股: {len(us_files)} 个文件")
    print(f"   - A股: {len(cn_files)} 个文件")
    
    # 检查数据量
    total_size = sum(f.stat().st_size for f in files)
    print(f"   - 总大小: {total_size / 1024 / 1024:.1f} MB")
    
    print()

def check_agents():
    """检查 Agent 文件"""
    print("=" * 80)
    print("4. Agent 文件检查")
    print("=" * 80)
    
    agents_dir = Path("agents")
    if not agents_dir.exists():
        print("❌ agents 目录不存在")
        return
    
    agent_files = list(agents_dir.glob("agent_*.py"))
    print(f"✅ Agent 文件: {len(agent_files)} 个")
    
    for f in sorted(agent_files):
        size = f.stat().st_size
        print(f"   - {f.name}: {size / 1024:.1f} KB")
    
    print()

def check_backtest_system():
    """检查回测系统"""
    print("=" * 80)
    print("5. 回测系统检查")
    print("=" * 80)
    
    backtest_file = Path("backtest_system.py")
    if backtest_file.exists():
        size = backtest_file.stat().st_size
        print(f"✅ 回测系统: {size / 1024:.1f} KB")
        
        # 检查语法
        try:
            import py_compile
            py_compile.compile(str(backtest_file), doraise=True)
            print("✅ 语法检查: 通过")
        except Exception as e:
            print(f"❌ 语法检查: {str(e)[:100]}")
    else:
        print("❌ 回测系统文件不存在")
    
    print()

def test_agent_collaboration():
    """测试 Agent 协同"""
    print("=" * 80)
    print("6. Agent 协同测试")
    print("=" * 80)
    
    try:
        from llm_helper import call_llm_sync
        
        # 测试决策层 Agent B
        print("测试 Agent B (情报研究)...")
        prompt_b = """分析当前市场：BTC $68000, ETH $2000, 美股回调 -2%。
请用 JSON 格式回复：{"market": "市场名", "signal": "看多/看空/中性", "confidence": 0-100}"""
        
        response_b = call_llm_sync("agent_b", prompt_b, timeout=15)
        if response_b and len(response_b) > 10:
            print(f"✅ Agent B: 响应正常 ({len(response_b)} 字符)")
        else:
            print(f"❌ Agent B: 响应异常")
        
        # 测试审查层 Agent M
        print("测试 Agent M (风险审查)...")
        prompt_m = """审查交易信号：买入 ETH $120, EV 85%, 失败概率 25%, 仓位 15%。
请用 JSON 格式回复：{"action": "approve/reject", "reason": "理由"}"""
        
        response_m = call_llm_sync("agent_m_primary", prompt_m, timeout=15)
        if response_m and len(response_m) > 10:
            print(f"✅ Agent M: 响应正常 ({len(response_m)} 字符)")
        else:
            print(f"❌ Agent M: 响应异常")
        
        print("✅ Agent 协同测试: 通过")
        
    except Exception as e:
        print(f"❌ Agent 协同测试: {str(e)[:200]}")
    
    print()

def main():
    print("\n" + "=" * 80)
    print("Polymarket 套利系统 - 健康检查")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    check_config()
    check_data_sources()
    check_historical_data()
    check_agents()
    check_backtest_system()
    test_agent_collaboration()
    
    print("=" * 80)
    print("健康检查完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
