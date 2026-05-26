#!/usr/bin/env python3
"""
LLM Smoke Check — minimal connectivity test for the configured provider.
timeout <= 20s, minimal prompt, immediate exit.
Never prints full API key.
"""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_helper import load_llm_config, get_client

SMOKE_TIMEOUT = 15  # seconds
SMOKE_PROMPT = "Say hello."


def mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    return key[:6] + "..." + key[-4:] if len(key) > 10 else "***"


def main():
    config_path = Path(__file__).parent.parent / "config" / "llm_config.json"
    print(f"[smoke] config path: {config_path}")

    config = load_llm_config()
    agent_models = config.get("agent_models", {})
    if not agent_models:
        print("[smoke] FAIL: agent_models is empty")
        sys.exit(1)

    # Pick first agent_id
    agent_id = next(iter(agent_models))
    model = agent_models[agent_id]
    api_base = config.get("proxy_api_base") or config.get("api_base", "unknown")
    api_key_raw = config.get("proxy_api_key") or config.get("api_key", "")

    print(f"[smoke] provider    : deepseek.com (direct)")
    print(f"[smoke] base_url    : {api_base}")
    print(f"[smoke] model       : {model}")
    print(f"[smoke] api_key     : {mask_key(api_key_raw)}")
    print(f"[smoke] agent_id    : {agent_id}")
    print(f"[smoke] timeout     : {SMOKE_TIMEOUT}s")
    print(f"[smoke] prompt      : {SMOKE_PROMPT}")

    try:
        client = get_client(model, config, timeout=SMOKE_TIMEOUT)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": SMOKE_PROMPT}],
            max_tokens=10,
            temperature=0.0,
        )
        content = response.choices[0].message.content.strip()
        print(f"[smoke] result      : SUCCESS")
        print(f"[smoke] response    : {content[:80]}")
        sys.exit(0)
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)[:200]
        print(f"[smoke] result      : FAIL")
        print(f"[smoke] error_type  : {error_type}")
        print(f"[smoke] error_msg   : {error_msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()