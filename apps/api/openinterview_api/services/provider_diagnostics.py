from __future__ import annotations

import re


def diagnose_llm_error(error: Exception | str, provider: str) -> dict:
    message = str(error)
    lower = message.lower()
    category = "unknown"
    hint = "请检查 provider、API Base、模型名、Key 和网络环境。"

    if any(token in lower for token in ["api key", "unauthorized", "401", "forbidden", "403"]):
        category = "auth"
        hint = "API Key 无效、权限不足或没有给当前模型授权。请重新复制 Key，并确认账号有该模型权限。"
    elif any(token in lower for token in ["404", "not found", "model_not_found", "model not found"]):
        category = "model_or_endpoint"
        hint = "模型名或 API Base 不匹配。请确认模型名真实存在，API Base 不要漏掉 /v1 或兼容模式路径。"
    elif any(token in lower for token in ["429", "rate limit", "quota", "insufficient_quota"]):
        category = "quota_or_rate_limit"
        hint = "账号额度不足、限流或并发过高。请检查余额、套餐、限流策略，或稍后重试。"
    elif any(token in lower for token in ["timeout", "timed out"]):
        category = "timeout"
        hint = "请求超时。请检查网络、代理、中转站稳定性，或把超时时间调大。"
    elif any(token in lower for token in ["network error", "connection refused", "name or service", "getaddrinfo", "dns"]):
        category = "network"
        hint = "网络不可达或本地服务未启动。Ollama 请确认已运行；云模型请检查代理和域名。"
    elif any(token in lower for token in ["unexpected response", "choices", "message", "json"]):
        category = "response_shape"
        hint = "服务返回格式不是 OpenAI Chat Completions 兼容格式。请换兼容接口或检查中转站配置。"
    elif any(token in lower for token in ["ssl", "certificate", "tls"]):
        category = "tls"
        hint = "TLS/证书校验失败。请检查系统时间、代理证书或中转站 HTTPS 配置。"

    return {
        "category": category,
        "provider": provider or "unknown",
        "message": message,
        "hint": hint,
        "http_status": _extract_http_status(message),
    }


def _extract_http_status(message: str) -> int | None:
    match = re.search(r"HTTP\s+(\d{3})", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(400|401|403|404|408|409|422|429|500|502|503|504)\b", message)
    if match:
        return int(match.group(1))
    return None
