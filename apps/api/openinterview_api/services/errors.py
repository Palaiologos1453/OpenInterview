from __future__ import annotations


def classify_error(error: Exception | str) -> str:
    message = str(error).lower()
    if any(token in message for token in ["api key", "unauthorized", "401", "forbidden", "403"]):
        return "auth"
    if any(token in message for token in ["404", "not found", "model_not_found", "model not found"]):
        return "model_or_endpoint"
    if any(token in message for token in ["429", "rate limit", "quota", "insufficient_quota"]):
        return "quota_or_rate_limit"
    if any(token in message for token in ["timeout", "timed out"]):
        return "timeout"
    if any(
        token in message
        for token in ["network error", "connection refused", "name or service", "getaddrinfo", "dns"]
    ):
        return "network"
    if any(token in message for token in ["unexpected response", "choices", "message", "json"]):
        return "response_shape"
    if any(token in message for token in ["ssl", "certificate", "tls"]):
        return "tls"
    if any(token in message for token in ["already finished", "conflict", "409"]):
        return "conflict"
    if any(token in message for token in ["validation", "invalid", "422", "bad request", "400"]):
        return "validation"
    if any(token in message for token in ["not implemented", "disabled"]):
        return "not_implemented"
    return "unknown"
