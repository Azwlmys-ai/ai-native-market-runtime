#!/usr/bin/env python3
"""Telegram bot 自检 + 发测试消息（在主机 Mac 上跑，纯 stdlib，无依赖）。

用法：
    # 方式 A：命令行传参
    python3 scripts/telegram_test.py <BOT_TOKEN> <CHAT_ID>

    # 方式 B：环境变量（与项目 system_config.json 约定一致）
    export TELEGRAM_BOT_TOKEN=xxxx:yyyy
    export TELEGRAM_CHAT_ID=6970547741
    python3 scripts/telegram_test.py

依次做 4 件事并打印清晰诊断：
  1) getMe        —— 验证 token 本身有效（拿到 bot 用户名）
  2) getUpdates   —— 看你是否给 bot 发过消息（bot 不能主动私聊从未联系过它的人）
  3) sendMessage  —— 真正发一条测试消息到 CHAT_ID，失败时打印 Telegram 原始报错
  4) 结论 + 排查建议
"""

from __future__ import annotations  # 主机 venv 是 3.9：让注解惰性求值，避免 PEP 604 报错

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


def _make_ssl_context(insecure: bool):
    """构造 SSL 上下文：默认安全；优先用 certifi 的 CA 包（修最常见的 macOS 缺证书问题）；
    --insecure 时完全跳过校验（仅用于确认 token/chat_id 是否正确）。"""
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    # 优先用 SSL_CERT_FILE（如把系统钥匙串导出的 PEM 指过来，含代理根证书）
    cafile = os.environ.get("SSL_CERT_FILE")
    if cafile and os.path.exists(cafile):
        return ssl.create_default_context(cafile=cafile)
    try:
        import certifi  # 退回 certifi 的 CA 包
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _api(token: str, method: str, params: dict | None = None,
         ssl_ctx: ssl.SSLContext | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    try:
        with urllib.request.urlopen(url, data=data, timeout=20, context=ssl_ctx) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Telegram 会在 HTTP 4xx body 里给出 description，读出来
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "error_code": e.code, "description": str(e)}
    except ssl.SSLError as e:
        return {"ok": False, "ssl_error": True,
                "description": f"SSL 校验失败: {e}"}
    except Exception as e:  # 网络层错误
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg or "self-signed" in msg or "self signed" in msg:
            return {"ok": False, "ssl_error": True,
                    "description": f"SSL 校验失败: {type(e).__name__}: {e}"}
        return {"ok": False, "description": f"network error: {type(e).__name__}: {e}"}


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--insecure"]
    insecure = "--insecure" in sys.argv or os.environ.get("TG_INSECURE") == "1"
    token = (args[0] if len(args) > 0 else os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = (args[1] if len(args) > 1 else os.environ.get("TELEGRAM_CHAT_ID", "")).strip()

    if not token or not chat_id:
        print("❌ 缺少 token 或 chat_id。\n   用法: python3 scripts/telegram_test.py <BOT_TOKEN> <CHAT_ID> [--insecure]\n"
              "   或 export TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 后直接跑。")
        return 2

    ctx = _make_ssl_context(insecure)

    print("=" * 56)
    print("Telegram bot 自检" + ("  [--insecure: 跳过证书校验]" if insecure else ""))
    print("=" * 56)

    # 1) getMe
    me = _api(token, "getMe", ssl_ctx=ctx)
    if not me.get("ok"):
        if me.get("ssl_error"):
            print(f"❌ [1/3] getMe 失败：SSL 证书校验失败（不是 token 问题）。\n   返回: {me.get('description')}")
            print("\n结论：你这台 Mac 的 Python 无法验证 api.telegram.org 的证书——通常是：")
            print("  (a) 你在用 VPN/代理访问 Telegram，代理做了 TLS 拦截、塞了自签根证书；或")
            print("  (b) 这个 Python 没装 CA 根证书包（python.org 版常见）。")
            print("⚠️  真正发消息的 Hermes 网关大概率用同一个 Python，会撞同样的错——这八成就是 bot 用不了的根因。")
            print("\n下一步（按顺序试）：")
            print("  1) 先确认 token/chat_id 是对的：本脚本加 --insecure 跑一遍（绕过证书校验只为验证）：")
            print("       python3 scripts/telegram_test.py <TOKEN> <CHAT_ID> --insecure")
            print("     若 --insecure 能发出消息 → 凭证没问题，纯粹是本机 SSL/代理配置。")
            print("  2) 装 CA 证书包：python3 -m pip install --upgrade certifi  （本脚本会自动用它）")
            print("     python.org 版 Python 还可双击运行 /Applications/Python\\ 3.x/Install\\ Certificates.command")
            print("  3) 若是代理 TLS 拦截：把代理的根证书导入系统钥匙串，或让网关走不拦截 TLS 的代理模式。")
            return 1
        print(f"❌ [1/3] getMe 失败：token 无效或网络不通。\n   返回: {me.get('description')}")
        print("\n结论：token 本身有问题（或这台机器连不上 api.telegram.org）。")
        print("排查：去 BotFather 确认 token；token 形如 123456:AAE...；必要时 /revoke 重置。")
        return 1
    u = me.get("result", {})
    print(f"✅ [1/3] getMe OK —— bot @{u.get('username')} (id={u.get('id')}, name={u.get('first_name')})")

    # 2) getUpdates —— 检查用户是否给 bot 发过消息
    upd = _api(token, "getUpdates", {"limit": "5"}, ssl_ctx=ctx)
    seen_chats = set()
    if upd.get("ok"):
        for it in upd.get("result", []):
            msg = it.get("message") or it.get("edited_message") or {}
            ch = msg.get("chat", {})
            if ch.get("id") is not None:
                seen_chats.add(str(ch["id"]))
    if seen_chats:
        print(f"✅ [2/3] getUpdates —— 最近与 bot 有过对话的 chat_id: {sorted(seen_chats)}")
        if str(chat_id) not in seen_chats:
            print(f"   ⚠️  你传入的 chat_id={chat_id} 不在其中——可能填错了。"
                  f" 正确的应是上面列出的某个。")
    else:
        print("⚠️  [2/3] getUpdates 没看到任何对话记录。")
        print("   这是 bot 发不出消息最常见的原因：**Telegram bot 不能主动私聊从未联系过它的人**。")
        print("   解决：用你的 Telegram 账号打开这个 bot，点 Start（或发任意一条消息），再重跑本脚本。")
        print("   （注：getUpdates 只保留最近的更新；若你很久前发过、且开了 webhook，这里也可能为空。）")

    # 3) sendMessage —— 真正发测试消息
    text = ("✅ Polymarket 套利系统 · Telegram 自检测试消息\n"
            "如果你收到这条，说明 token + chat_id 都正常，bot 可用。")
    res = _api(token, "sendMessage", {"chat_id": chat_id, "text": text}, ssl_ctx=ctx)
    if res.get("ok"):
        print(f"✅ [3/3] sendMessage 成功！已发到 chat_id={chat_id}，去 Telegram 查收。")
        print("\n结论：bot 凭证完全正常。若平时仍收不到，问题在 Hermes 网关（见下）。")
        return 0

    code = res.get("error_code")
    desc = res.get("description", "")
    print(f"❌ [3/3] sendMessage 失败：error_code={code}  description={desc}")
    print("\n常见原因对照：")
    if code == 403:
        print("   • 403 'bot can't initiate conversation' → 你还没给 bot 发过 /start。先在 Telegram 里 Start 这个 bot。")
        print("   • 403 'bot was blocked by the user' → 你把 bot 拉黑了，去解除。")
    elif code == 400 and "chat not found" in desc.lower():
        print("   • 'chat not found' → chat_id 填错了。用上面 [2/3] 列出的 chat_id，或给 bot 发条消息后看 getUpdates。")
    elif code == 401:
        print("   • 401 Unauthorized → token 失效，去 BotFather /revoke 重置。")
    else:
        print("   • 见上面 description 的原文。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
