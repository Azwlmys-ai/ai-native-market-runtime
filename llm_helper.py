"""
LLM 统一调用接口
所有 Agent 必须使用此模块调用 LLM，禁止直接使用 OpenAI SDK
"""

import os
import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, wait
from pathlib import Path
from typing import Any

from openai import OpenAI, APITimeoutError, APIError

# Agent B hedged race defaults (Grok hang mitigation)
AGENT_B_HEDGE_DELAY_SEC = 45
AGENT_B_RACE_DEADLINE_SEC = 90

_FALLBACK_SENTINELS = frozenset({
    "__SINGLE_PROVIDER_NO_FALLBACK__",
    "__NO_FALLBACK__",
})

# Agent M / E / F 与 Agent B 共用 model + provider 路由（不改 agent_b.py）
AGENT_B_ROUTE_ALIASES = frozenset({
    "agent_m_primary",
    "agent_m_secondary",
    "agent_m_trainer",
    "agent_m_test",
    "agent_e",
    "agent_f",
})


def routing_agent_id(agent_id: str) -> str:
    """返回实际用于 model/provider 解析的 agent_id。"""
    return "agent_b" if agent_id in AGENT_B_ROUTE_ALIASES else agent_id

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class LLMModelError(RuntimeError):
    """模型调用失败（非风控拒绝）。"""

    def __init__(
        self,
        message,
        *,
        error_type="model_error",
        agent_id=None,
        models_tried=None,
        fallback_used=False,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.agent_id = agent_id
        self.models_tried = list(models_tried or [])
        self.fallback_used = fallback_used


def load_llm_config():
    """加载 LLM 配置"""
    config_path = Path(__file__).parent / "config" / "llm_config.json"
    with open(config_path, 'r') as f:
        return json.load(f)


def _get_agent_provider(config: dict, agent_id: str = None, model: str = None) -> dict:
    """读取 agent_providers 专属配置（P0-B research rollout）。"""
    providers = config.get("agent_providers") or {}
    if agent_id and agent_id in providers:
        return providers[agent_id]
    if model:
        for aid, provider in providers.items():
            if config.get("agent_models", {}).get(aid) == model:
                return provider
            if provider.get("model") == model:
                return provider
    return {}


def _resolve_provider_for_model(config: dict, model: str) -> dict:
    """按 model 名在 agent_providers 中查找可用 provider（供 fallback 跨 provider 使用）。"""
    for provider in (config.get("agent_providers") or {}).values():
        if provider.get("model") == model:
            return provider
    return {}


def _client_from_provider(provider: dict, timeout: int) -> OpenAI:
    import httpx

    api_key = provider.get("api_key")
    api_base = provider.get("api_base")
    if not api_key or not api_base:
        raise ValueError("agent_provider 缺少 api_key 或 api_base")

    proxy = provider.get("proxy")
    http_client = httpx.Client(
        trust_env=False,
        timeout=timeout,
        proxy=proxy if proxy else None,
    )
    return OpenAI(
        api_key=api_key,
        base_url=api_base,
        timeout=timeout,
        http_client=http_client,
    )


def _default_client(config: dict, timeout: int) -> OpenAI:
    import httpx

    proxy = config.get("proxy")
    http_client = httpx.Client(
        trust_env=False,
        timeout=timeout,
        proxy=proxy if proxy else None,
    )
    return OpenAI(
        api_key=config["proxy_api_key"],
        base_url=config["proxy_api_base"],
        timeout=timeout,
        http_client=http_client,
    )


def get_client(model: str, config: dict, timeout: int, agent_id: str = None):
    """根据 agent_id / 模型名称选择 API 客户端"""
    provider = _get_agent_provider(config, agent_id=agent_id, model=model)
    if not provider:
        provider = _resolve_provider_for_model(config, model)
    if provider:
        return _client_from_provider(provider, timeout)

    if model.startswith("grok"):
        api_key = config["api_key"]
        base_url = config["api_base"]
        import httpx
        proxy = config.get("proxy")
        http_client = httpx.Client(
            trust_env=False,
            timeout=timeout,
            proxy=proxy if proxy else None,
        )
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            http_client=http_client,
        )

    return _default_client(config, timeout)


# Fallback 策略：主模型失败后尝试的备用模型
_DEFAULT_FALLBACK_MAP = {
    "grok-4.3": "claude-opus-4-7",
    "grok-4.20-0309-reasoning": "claude-opus-4-7",
    "grok-4.20-0309-non-reasoning": "claude-opus-4-7",
    "gpt-5.4": "claude-opus-4-7",
    "deepseek-r1": "claude-opus-4-7",
    "deepseek-v3.2": "claude-opus-4-7",
    "claude-opus-4-7": "grok-4.3",
    "deepseek-v4-pro": "grok-4-1-fast-reasoning",
    "grok-4-1-fast-reasoning": "deepseek-v4-flash",
}

_INVALID_VALUES = {"", "[REDACTED]", "YOUR_KEY", "TODO", None}


def _is_valid_model(name) -> bool:
    if name in _INVALID_VALUES or name in _FALLBACK_SENTINELS:
        return False
    if isinstance(name, str) and (name.startswith("__") or name.startswith("YOUR_") or name.startswith("TODO")):
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


def _build_model_chain(config: dict, primary_model: str) -> list[str]:
    chain = [primary_model]
    fallback = get_fallback_map(config).get(primary_model)
    if _is_valid_model(fallback) and fallback not in chain:
        chain.append(fallback)
    return chain


def _allocate_timeouts(total_timeout: int, n_models: int) -> list[int]:
    if n_models <= 0:
        return []
    if total_timeout <= 0:
        return [25] * n_models
    ideal = min(30, max(20, 25))
    if n_models * ideal <= total_timeout:
        return [ideal] * n_models
    per = max(10, total_timeout // n_models)
    return [per] * n_models


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, APITimeoutError):
        return "timeout"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None)
        if status in _RETRYABLE_STATUS:
            return "api_error"
        msg = str(exc).lower()
        if "connection" in msg:
            return "connection_error"
        return "api_error"
    msg = str(exc).lower()
    if "connection error" in msg or "connection refused" in msg or "connect" in msg:
        return "connection_error"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    return "model_error"


def _is_retryable(error_type: str) -> bool:
    return error_type in {"connection_error", "timeout", "api_error"}


def _call_single_model(
    *,
    agent_id: str,
    routing_id: str,
    current_model: str,
    primary_model: str,
    prompt: str,
    config: dict,
    timeout: int,
    temperature: float,
    max_retries: int,
) -> str:
    client = get_client(current_model, config, timeout, agent_id=routing_id)
    last_error = None
    last_type = "model_error"

    for attempt in range(max_retries):
        try:
            provider = _get_agent_provider(config, agent_id=routing_id, model=current_model)
            if not provider:
                provider = _resolve_provider_for_model(config, current_model)
            request_model = provider.get("model", current_model) if provider else current_model
            response = client.chat.completions.create(
                model=request_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            if current_model != primary_model:
                print(
                    f"⚠️ [{agent_id}] fallback_used: primary={primary_model} "
                    f"fallback={current_model}"
                )
            return response.choices[0].message.content

        except Exception as exc:
            last_error = exc
            last_type = _classify_error(exc)
            if not _is_retryable(last_type) or attempt >= max_retries - 1:
                break
            time.sleep(min(2 ** attempt, 4))

    raise LLMModelError(
        f"API 错误: {last_error}",
        error_type=last_type,
        agent_id=agent_id,
        models_tried=[current_model],
        fallback_used=current_model != primary_model,
    )


def call_llm_sync(agent_id: str, prompt: str, timeout: int = 60, max_retries: int = 3, temperature: float = None) -> str:
    config = load_llm_config()
    route_id = routing_agent_id(agent_id)
    model = config["agent_models"].get(route_id) or config["agent_models"].get(agent_id)

    if not model:
        raise ValueError(f"未找到 agent_id={agent_id} 的模型配置")

    if temperature is None:
        temperature = 0.1 if agent_id == "agent_m_primary" else 0.7

    model_chain = _build_model_chain(config, model)
    per_model_timeouts = _allocate_timeouts(timeout, len(model_chain))

    models_tried = []
    last_error = None
    fallback_used = False

    for idx, current_model in enumerate(model_chain):
        per_timeout = per_model_timeouts[idx]
        retries = max(1, min(max_retries, 2 if idx == 0 else 1))
        try:
            return _call_single_model(
                agent_id=agent_id,
                routing_id=route_id,
                current_model=current_model,
                primary_model=model,
                prompt=prompt,
                config=config,
                timeout=per_timeout,
                temperature=temperature,
                max_retries=retries,
            )
        except LLMModelError as exc:
            models_tried.extend(exc.models_tried)
            fallback_used = fallback_used or exc.fallback_used
            last_error = exc
            if idx < len(model_chain) - 1:
                route_note = f" via {route_id}" if route_id != agent_id else ""
                print(
                    f"⚠️ [{agent_id}{route_note}] model_error={exc.error_type} on {current_model}; "
                    f"trying fallback"
                )
                continue
            break

    raise LLMModelError(
        str(last_error) if last_error else f"[{agent_id}] 所有模型均失败",
        error_type=getattr(last_error, "error_type", "model_error"),
        agent_id=agent_id,
        models_tried=models_tried or model_chain,
        fallback_used=fallback_used,
    )


def _winner_label(future, grok_future, primary_model: str, fallback_model: str) -> str:
    if future is grok_future:
        return "grok"
    return "deepseek" if "deepseek" in (fallback_model or "").lower() else fallback_model


def _submit_daemon(fn) -> Future:
    """Run fn on a daemon thread so loser hedge calls cannot block subprocess exit."""
    fut: Future = Future()

    def _runner() -> None:
        try:
            fut.set_result(fn())
        except Exception as exc:
            fut.set_exception(exc)

    threading.Thread(target=_runner, daemon=True, name="llm_race").start()
    return fut


def call_llm_hedged_race(
    agent_id: str,
    prompt: str,
    *,
    hedge_delay_sec: float = AGENT_B_HEDGE_DELAY_SEC,
    deadline_sec: float = AGENT_B_RACE_DEADLINE_SEC,
    temperature: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """Hedged race: Grok at T=0; DeepSeek Flash after hedge delay if Grok pending.

    Returns (content, stats). Loser futures are abandoned (non-blocking).
    """
    config = load_llm_config()
    route_id = routing_agent_id(agent_id)
    primary_model = config["agent_models"].get(route_id) or config["agent_models"].get(agent_id)
    if not primary_model:
        raise ValueError(f"未找到 agent_id={agent_id} 的模型配置")

    fallback_model = get_fallback_map(config).get(primary_model)
    if not _is_valid_model(fallback_model):
        content = call_llm_sync(agent_id, prompt, timeout=int(deadline_sec), temperature=temperature)
        return content, {
            "grok_started": True,
            "deepseek_started": False,
            "winner": "grok",
            "elapsed_sec": 0.0,
            "hedge_triggered": False,
            "timeout": False,
            "hedge_disabled": True,
        }

    if temperature is None:
        temperature = 0.1 if agent_id == "agent_m_primary" else 0.7

    stats: dict[str, Any] = {
        "grok_started": True,
        "deepseek_started": False,
        "winner": None,
        "elapsed_sec": 0.0,
        "hedge_triggered": False,
        "timeout": False,
        "primary_model": primary_model,
        "fallback_model": fallback_model,
    }

    t0 = time.monotonic()

    def _remaining_timeout() -> int:
        return max(1, int(deadline_sec - (time.monotonic() - t0)))

    def _run_model(model: str) -> str:
        return _call_single_model(
            agent_id=agent_id,
            routing_id=route_id,
            current_model=model,
            primary_model=primary_model,
            prompt=prompt,
            config=config,
            timeout=_remaining_timeout(),
            temperature=temperature,
            max_retries=1,
        )

    grok_future = _submit_daemon(lambda: _run_model(primary_model))
    flash_future = None

    # Phase 1: Grok-only window (no extra API cost on fast path)
    try:
        content = grok_future.result(timeout=hedge_delay_sec)
        stats["winner"] = "grok"
        stats["elapsed_sec"] = round(time.monotonic() - t0, 2)
        return content, stats
    except Exception:
        pass  # timeout or model error → hedge

    stats["hedge_triggered"] = True
    stats["deepseek_started"] = True
    flash_future = _submit_daemon(lambda: _run_model(fallback_model))

    pending = {grok_future, flash_future}
    while pending and (time.monotonic() - t0) < deadline_sec:
        done, pending = wait(
            pending,
            timeout=_remaining_timeout(),
            return_when=FIRST_COMPLETED,
        )
        if not done:
            break
        for fut in done:
            try:
                content = fut.result()
                stats["winner"] = _winner_label(
                    fut, grok_future, primary_model, fallback_model
                )
                stats["elapsed_sec"] = round(time.monotonic() - t0, 2)
                return content, stats
            except LLMModelError:
                continue

    stats["timeout"] = True
    stats["elapsed_sec"] = round(time.monotonic() - t0, 2)
    raise LLMModelError(
        f"[{agent_id}] hedged race deadline exceeded ({deadline_sec}s)",
        error_type="timeout",
        agent_id=agent_id,
        models_tried=[primary_model, fallback_model],
        fallback_used=stats["hedge_triggered"],
    )


def call_llm_dual(agent_id_primary: str, agent_id_secondary: str, prompt: str, timeout: int = 60) -> dict:
    return {
        "primary": call_llm_sync(agent_id_primary, prompt, timeout),
        "secondary": call_llm_sync(agent_id_secondary, prompt, timeout)
    }


def call_llm(prompt: str, model: str = "deepseek-r1", temperature: float = 0.7, max_tokens: int = 4000, timeout: int = 60) -> str:
    config = load_llm_config()
    model_chain = _build_model_chain(config, model)

    provider_agent_id = None
    for aid, mapped_model in config.get("agent_models", {}).items():
        if mapped_model == model and aid in config.get("agent_providers", {}):
            provider_agent_id = aid
            break

    per_model_timeouts = _allocate_timeouts(timeout, len(model_chain))
    models_tried = []
    last_error = None
    fallback_used = False

    logical_id = provider_agent_id or "call_llm"
    route_id = routing_agent_id(logical_id)
    for idx, current_model in enumerate(model_chain):
        per_timeout = per_model_timeouts[idx]
        try:
            return _call_single_model(
                agent_id=logical_id,
                routing_id=route_id,
                current_model=current_model,
                primary_model=model,
                prompt=prompt,
                config=config,
                timeout=per_timeout,
                temperature=temperature,
                max_retries=1,
            )
        except LLMModelError as exc:
            models_tried.extend(exc.models_tried)
            fallback_used = fallback_used or exc.fallback_used
            last_error = exc
            continue

    raise LLMModelError(
        str(last_error) if last_error else f"LLM 调用失败: {model}",
        error_type=getattr(last_error, "error_type", "model_error"),
        agent_id=provider_agent_id,
        models_tried=models_tried or model_chain,
        fallback_used=fallback_used,
    )


if __name__ == "__main__":
    try:
        response = call_llm_sync("agent_k", "测试：1+1=?", timeout=10)
        print(f"✅ LLM 调用成功: {response[:100]}")
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
