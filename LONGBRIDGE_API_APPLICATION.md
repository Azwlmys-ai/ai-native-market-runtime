# 长桥 API 申请详细步骤

## 📋 前提条件
- 需要有长桥证券账户（如果没有，需要先开户）
- 开户链接: https://longbridgeapp.com/

## 🚀 申请步骤

### 步骤 1: 访问开发者中心
1. 打开浏览器，访问: https://open.longbridgeapp.com/
2. 点击右上角 "登录" 按钮
3. 使用你的长桥账号登录（手机号 + 验证码 或 邮箱 + 密码）

### 步骤 2: 创建应用
1. 登录后，进入 "控制台" (Console)
2. 点击 "创建应用" 或 "Create Application"
3. 填写应用信息:
   - **应用名称**: Polymarket Arbitrage System
   - **应用类型**: 个人应用
   - **应用描述**: 跨平台套利交易系统，用于 Polymarket 与传统市场的价格对比和套利
   - **回调地址**: http://localhost:8080 (可选)

### 步骤 3: 获取 API 凭证
创建应用后，系统会自动生成:
- **App Key**: 类似 `lb_xxxxxxxxxxxxxxxx`
- **App Secret**: 类似 `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
- **Access Token**: 类似 `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

⚠️ **重要**: 请妥善保存这些凭证，特别是 App Secret 和 Access Token，它们只会显示一次！

### 步骤 4: 配置权限
1. 在应用详情页，找到 "权限配置"
2. 勾选以下权限:
   - ✅ 行情数据 (Quote Data)
   - ✅ 交易接口 (Trading API) - 如果需要自动交易
   - ✅ 账户信息 (Account Info)
   - ✅ 历史数据 (Historical Data)

### 步骤 5: 测试连接
获取凭证后，将以下信息发送给我:
```
App Key: lb_xxxxxxxxxxxxxxxx
App Secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Access Token: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

我会帮你:
1. 配置到系统中
2. 测试 API 连接
3. 验证数据采集功能
4. 集成到 Orchestrator

## 📞 遇到问题？

### 问题 1: 没有长桥账户
**解决方案**: 
1. 访问 https://longbridgeapp.com/
2. 点击 "立即开户"
3. 准备材料: 身份证、银行卡、手机号
4. 完成开户流程（约 10-15 分钟）
5. 入金（建议 $1,000+）

### 问题 2: 找不到开发者中心
**解决方案**:
- 直接访问: https://open.longbridgeapp.com/
- 或在长桥 APP 内: 我的 → 更多 → OpenAPI

### 问题 3: 创建应用失败
**解决方案**:
- 确认账户已完成实名认证
- 确认账户状态正常（未被冻结）
- 联系长桥客服: support@longbridgeapp.com

### 问题 4: API 权限不足
**解决方案**:
- 在应用详情页重新勾选权限
- 部分权限可能需要账户达到一定资产规模
- 联系客服申请开通

## 📚 参考资料
- 官方文档: https://open.longbridgeapp.com/docs
- Python SDK: https://github.com/longbridgeapp/openapi-sdk
- API 示例: https://open.longbridgeapp.com/docs/getting-started

## ⏱️ 预计时间
- 有账户: 5-10 分钟
- 无账户: 需要先开户（1-2 天）

---
准备好凭证后，直接发送给我，格式如下:

```
App Key: lb_xxxxxxxxxxxxxxxx
App Secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Access Token: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

我会立即帮你配置和测试！
