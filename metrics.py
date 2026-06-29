"""
metrics.py — In-memory metrics: request count, token usage, latency, error rate
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class _Stats:
    total_requests: int      = 0
    success_requests: int    = 0
    error_requests: int      = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_latency_ms: int    = 0
    by_model: dict           = field(default_factory=dict)
    started_at: str          = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


_stats = _Stats()
_lock  = asyncio.Lock()


async def record_request(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    success: bool,
) -> None:
    async with _lock:
        _stats.total_requests          += 1
        _stats.total_prompt_tokens     += prompt_tokens
        _stats.total_completion_tokens += completion_tokens
        _stats.total_latency_ms        += latency_ms
        if success:
            _stats.success_requests += 1
        else:
            _stats.error_requests   += 1

        m = _stats.by_model.setdefault(
            model, {"requests": 0, "prompt_tokens": 0,
                    "completion_tokens": 0, "total_latency_ms": 0}
        )
        m["requests"]          += 1
        m["prompt_tokens"]     += prompt_tokens
        m["completion_tokens"] += completion_tokens
        m["total_latency_ms"]  += latency_ms


async def get_summary() -> dict:
    async with _lock:
        n  = _stats.total_requests or 1
        by_model_out = {
            model: {
                "requests":      m["requests"],
                "total_tokens":  m["prompt_tokens"] + m["completion_tokens"],
                "avg_latency_ms": round(m["total_latency_ms"] / (m["requests"] or 1)),
            }
            for model, m in _stats.by_model.items()
        }
        return {
            "started_at":      _stats.started_at,
            "total_requests":  _stats.total_requests,
            "success_requests": _stats.success_requests,
            "error_requests":  _stats.error_requests,
            "error_rate_pct":  round(_stats.error_requests / n * 100, 1),
            "total_tokens": {
                "prompt":     _stats.total_prompt_tokens,
                "completion": _stats.total_completion_tokens,
                "total":      _stats.total_prompt_tokens + _stats.total_completion_tokens,
            },
            "avg_latency_ms": round(_stats.total_latency_ms / n),
            "by_model":       by_model_out,
        }


async def reset() -> None:
    global _stats
    async with _lock:
        _stats = _Stats()
