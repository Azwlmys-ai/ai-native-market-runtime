"""
LLM 统一调用接口
所有 Agent 必须使用此模块调用 LLM，禁止直接使用 OpenAI SDK
"""

import os
import json
import time
from pathlib import Path
from openai import OpenAI, APITimeoutError, APIError

def load_llm_config():
    """加载 LLM 配置"""
    config_path = Path(__file__).parent / "config" / "llm_config.json"
    with open(config_path, 'r') as f:
        return json.load(f)

def get_client(model: str, config: dict, timeout: int):
    """根据模型名称选择 API 客户端"""
    if model.startswith("grok"):
        api_key = config["api_key"]
        base_url = config["api_base"]
    else:
        api_key = config["proxy_api_key"]
        base_url = config["proxy_api_base"]
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

# Fallback 策略：主模型失败后尝试的备用模型
_DEFAULT_FALLBACK_MAP = {
    "grok-4.3": "claude-opus-4-7",
    "grok-4.20-0309-reasoning": "claude-opus-4-7",
    "grok-4.20-0309-non-reasoning": "claude-opus-4-7",
    "gpt-5.4": "claude-opus-4-7",
    "deepseek-r1": "claude-opus-4-7",
    "deepseek-v3.2": "claude-opus-4-7",
    "claude-opus-4-7": "grok-4.3",
}

_INVALID_VALUES = {"", "[REDACTED]", "YOUR_KEY", "TODO", None}


def _is_valid_model(name) -> bool:
    if name in _INVALID_VALUES:
        return False
    if isinstance(name, str) and (name.startswith("YOUR_") or name.startswith("TODO")):
        return False
    return isinstance(name, str)


def get_fallback_map(config: dict) -> dict:
    user_map = config.get("fallback_map", {}) or {}
    cleaned = {
        key: value
        for key, value in user_map.items()
        if _is_valid_model(key) and _is_valid_model(value)
    }
    return {**_DEFAULT_FALLBACK_MAP, **cleaned}


def call_llm_sync(agent_id: str, prompt: str, timeout: int = 60, max_retries: int = 3, temperature: float = None) -> str:
    config = load_llm_config()
    model = config["agent_models"].get(agent_id)

    if not model:
        raise ValueError(f"未找到 agent_id={agent_id} 的模型配置")

    if temperature is None:
        temperature = 0.1 if agent_id == "agent_m_primary" else 0.7

    # 构建模型调用链：主模型 + fallback
    model_chain = [model]
    fallback = get_fallback_map(config).get(model)
    if fallback:
        model_chain.append(fallback)

    last_error = None
    for current_model in model_chain:
        client = get_client(current_model, config, timeout)
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature
                )
                if current_model != model:
                    print(f"⚠️ [{agent_id}] 主模型 {model} 失败，已切换到 {current_model}")
                return response.choices[0].message.content

            except APITimeoutError:
                last_error = TimeoutError(f"超时（{timeout}s）")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

            except APIError as e:
                last_error = RuntimeError(f"API 错误: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

            except Exception as e:
                last_error = RuntimeError(f"调用失败: {e}")
                break

    raise last_error or RuntimeError(f"[{agent_id}] 所有模型均失败")

def call_llm_dual(agent_id_primary: str, agent_id_secondary: str, prompt: str, timeout: int = 60) -> dict:
    return {
        "primary": call_llm_sync(agent_id_primary, prompt, timeout),
        "secondary": call_llm_sync(agent_id_secondary, prompt, timeout)
    }

def call_llm(prompt: str, model: str = "deepseek-r1", temperature: float = 0.7, max_tokens: int = 4000, timeout: int = 60) -> str:
    config = load_llm_config()
    model_chain = [model]
    fallback = get_fallback_map(config).get(model)
    if fallback:
        model_chain.append(fallback)

    last_error = None
    for current_model in model_chain:
        client = get_client(current_model, config, timeout)
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            if current_model != model:
                print(f"⚠️ 主模型 {model} 失败，已切换到 {current_model}")
            return response.choices[0].message.content
        except Exception as e:
            last_error = e

    raise RuntimeError(f"LLM 调用失败: {last_error}")

if __name__ == "__main__":
    try:
        response = call_llm_sync("agent_k", "测试：1+1=?", timeout=10)
        print(f"✅ LLM 调用成功: {response[:100]}")
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
