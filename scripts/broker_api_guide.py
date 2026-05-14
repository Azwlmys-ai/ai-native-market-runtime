#!/usr/bin/env python3
"""
Broker API Application Guide - 券商 API 申请指南
老虎证券、长桥、富途 API 申请流程和配置模板
"""

import json
from datetime import datetime

def generate_tiger_guide():
    """老虎证券 API 申请指南"""
    return {
        'broker': '老虎证券 (Tiger Brokers)',
        'api_name': 'Tiger Open API',
        'official_site': 'https://www.tigerbrokers.com.sg/openapi',
        'documentation': 'https://quant.itigerup.com/openapi/zh/python/overview/introduction.html',
        
        'requirements': {
            'account': '需要开通老虎证券账户',
            'deposit': '建议入金 $3,000+ (美股交易门槛)',
            'api_permission': '需要在 APP 中申请 API 权限',
            'approval_time': '1-3 个工作日'
        },
        
        'application_steps': [
            '1. 下载老虎证券 APP，完成开户和入金',
            '2. APP 内: 我的 → 设置 → API 管理 → 申请 API 权限',
            '3. 填写申请表单（用途: 量化交易）',
            '4. 等待审核通过（1-3 个工作日）',
            '5. 获取 API Key 和 Secret',
            '6. 安装 Python SDK: pip install tigeropen'
        ],
        
        'api_capabilities': [
            '✅ 美股实时行情（Level 1）',
            '✅ 期权链数据',
            '✅ 下单交易（股票、期权）',
            '✅ 账户资产查询',
            '✅ 历史数据回测',
            '⚠️  港股行情需要额外订阅'
        ],
        
        'pricing': {
            'api_fee': '免费',
            'market_data': 'Level 1 免费，Level 2 需付费订阅',
            'trading_commission': '美股 $0.0039/股（最低 $0.99/笔）'
        },
        
        'config_template': {
            'tiger_id': 'YOUR_TIGER_ID',
            'account': 'YOUR_ACCOUNT_ID',
            'private_key': 'YOUR_PRIVATE_KEY_PATH',
            'tiger_public_key': 'TIGER_PUBLIC_KEY_PATH',
            'language': 'zh_CN',
            'timezone': 'Asia/Shanghai'
        }
    }

def generate_longbridge_guide():
    """长桥 API 申请指南"""
    return {
        'broker': '长桥 (Longbridge)',
        'api_name': 'Longbridge OpenAPI',
        'official_site': 'https://open.longbridgeapp.com/',
        'documentation': 'https://open.longbridgeapp.com/docs',
        
        'requirements': {
            'account': '需要开通长桥证券账户',
            'deposit': '港股/美股账户均可，建议入金 $1,000+',
            'api_permission': '在官网申请 OpenAPI 权限',
            'approval_time': '即时开通'
        },
        
        'application_steps': [
            '1. 访问 https://open.longbridgeapp.com/',
            '2. 使用长桥账号登录',
            '3. 进入开发者中心 → 创建应用',
            '4. 填写应用信息（名称、用途）',
            '5. 获取 App Key、App Secret、Access Token',
            '6. 安装 Python SDK: pip install longbridge'
        ],
        
        'api_capabilities': [
            '✅ 港股实时行情',
            '✅ 美股实时行情',
            '✅ A股行情（需要额外权限）',
            '✅ 下单交易（股票、期权、窝轮）',
            '✅ 账户资产查询',
            '✅ 历史数据查询',
            '✅ Webhook 推送'
        ],
        
        'pricing': {
            'api_fee': '免费',
            'market_data': '基础行情免费，Level 2 需付费',
            'trading_commission': '港股 0.03%，美股 $0.0049/股'
        },
        
        'config_template': {
            'app_key': 'YOUR_APP_KEY',
            'app_secret': 'YOUR_APP_SECRET',
            'access_token': 'YOUR_ACCESS_TOKEN',
            'http_url': 'https://openapi.longbridgeapp.com',
            'quote_ws_url': 'wss://openapi-quote.longbridgeapp.com'
        }
    }

def generate_futu_guide():
    """富途 API 申请指南"""
    return {
        'broker': '富途 (Futu)',
        'api_name': 'Futu OpenAPI',
        'official_site': 'https://openapi.futunn.com/',
        'documentation': 'https://openapi.futunn.com/futu-api-doc/',
        
        'requirements': {
            'account': '需要开通富途牛牛账户',
            'deposit': '港股/美股账户，建议入金 $3,000+',
            'api_permission': '需要在 APP 中开通 OpenAPI 权限',
            'approval_time': '即时开通'
        },
        
        'application_steps': [
            '1. 下载富途牛牛 APP，完成开户和入金',
            '2. APP 内: 交易 → 设置 → OpenAPI',
            '3. 开通 OpenAPI 权限（需要签署协议）',
            '4. 下载 FutuOpenD 客户端（本地网关）',
            '5. 配置 FutuOpenD 连接参数',
            '6. 安装 Python SDK: pip install futu-api'
        ],
        
        'api_capabilities': [
            '✅ 港股实时行情',
            '✅ 美股实时行情',
            '✅ A股行情',
            '✅ 期权链数据',
            '✅ 窝轮、牛熊证数据',
            '✅ 下单交易（股票、期权、窝轮）',
            '✅ 账户资产查询',
            '✅ 历史数据回测'
        ],
        
        'pricing': {
            'api_fee': '免费',
            'market_data': 'Level 1 免费，Level 2 需付费订阅',
            'trading_commission': '港股 0.03%，美股 $0.0049/股',
            'note': '需要运行本地 FutuOpenD 网关'
        },
        
        'config_template': {
            'host': '127.0.0.1',
            'port': 11111,
            'security_firm': 'FUTUSECURITIES',
            'filter_trdmarket': 'HK',
            'rsa_file': 'YOUR_RSA_KEY_PATH'
        }
    }

def generate_ib_guide():
    """盈透证券 API 申请指南"""
    return {
        'broker': '盈透证券 (Interactive Brokers)',
        'api_name': 'IB API / TWS API',
        'official_site': 'https://www.interactivebrokers.com/',
        'documentation': 'https://interactivebrokers.github.io/tws-api/',
        
        'requirements': {
            'account': '需要开通盈透证券账户',
            'deposit': '最低入金 $10,000（机构账户）或 $0（个人账户）',
            'api_permission': 'API 权限默认开通',
            'approval_time': '账户开通后即可使用'
        },
        
        'application_steps': [
            '1. 访问 https://www.interactivebrokers.com/ 开户',
            '2. 完成身份验证和入金',
            '3. 下载 TWS (Trader Workstation) 或 IB Gateway',
            '4. 在 TWS 中启用 API 连接（配置 → API → 启用 ActiveX 和 Socket 客户端）',
            '5. 设置 Socket 端口（默认 7497 实盘，7496 模拟盘）',
            '6. 安装 Python SDK: pip install ibapi'
        ],
        
        'api_capabilities': [
            '✅ 全球股票实时行情',
            '✅ 期权链数据（全市场）',
            '✅ 期货合约',
            '✅ 外汇汇率',
            '✅ 债券、基金',
            '✅ 下单交易（全品种）',
            '✅ 账户资产查询',
            '✅ 历史数据回测',
            '✅ 算法交易'
        ],
        
        'pricing': {
            'api_fee': '免费',
            'market_data': '实时行情需要订阅（$1-10/月/交易所）',
            'trading_commission': '美股 $0.0035/股（最低 $0.35/笔），期权 $0.65/张',
            'note': '需要运行本地 TWS 或 IB Gateway'
        },
        
        'config_template': {
            'host': '127.0.0.1',
            'port': 7497,  # 实盘: 7497, 模拟盘: 7496
            'client_id': 1,
            'account': 'YOUR_ACCOUNT_ID'
        }
    }

def main():
    print("📋 券商 API 申请指南")
    print("="*60)
    
    guides = {
        'tiger': generate_tiger_guide(),
        'longbridge': generate_longbridge_guide(),
        'futu': generate_futu_guide(),
        'ib': generate_ib_guide()
    }
    
    # 保存完整指南
    output = {
        'timestamp': datetime.now().isoformat(),
        'guides': guides,
        'recommendation': {
            'easiest': 'Longbridge（即时开通，无需审核）',
            'most_powerful': 'Interactive Brokers（全球市场覆盖）',
            'best_for_hk_us': 'Futu（港美股行情丰富）',
            'best_for_options': 'Tiger Brokers（期权交易友好）'
        }
    }
    
    with open('data/broker_api_guide.json', 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print("\n✅ 完整指南保存到 data/broker_api_guide.json")
    
    # 打印摘要
    print("\n" + "="*60)
    print("📊 券商 API 对比:")
    
    for key, guide in guides.items():
        print(f"\n🏦 {guide['broker']}")
        print(f"   官网: {guide['official_site']}")
        print(f"   审核时间: {guide['requirements']['approval_time']}")
        print(f"   API 费用: {guide['pricing']['api_fee']}")
        print(f"   推荐入金: {guide['requirements']['deposit']}")
    
    print("\n" + "="*60)
    print("💡 推荐方案:")
    print("\n1. 立即申请: Longbridge（即时开通，无需等待）")
    print("   - 访问: https://open.longbridgeapp.com/")
    print("   - 用途: 港股/美股行情 + 交易")
    print("\n2. 同步申请: Tiger Brokers（1-3 天审核）")
    print("   - 访问: https://www.tigerbrokers.com.sg/openapi")
    print("   - 用途: 美股期权交易")
    print("\n3. 长期规划: Interactive Brokers（全球市场）")
    print("   - 访问: https://www.interactivebrokers.com/")
    print("   - 用途: 跨市场套利、期权策略")
    
    print("\n" + "="*60)
    print("📝 下一步行动:")
    print("\n1. 访问 Longbridge 官网，创建开发者应用")
    print("2. 获取 App Key、App Secret、Access Token")
    print("3. 将配置保存到 config/broker_config.json")
    print("4. 运行测试脚本验证连接")

if __name__ == '__main__':
    main()
