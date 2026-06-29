"""
services/json_logger.py — Ghi mỗi LLM call ra file JSONL theo spec 3.1

Format file: logs/calls_YYYY-MM-DD.jsonl  (rotate theo ngày)
Mỗi dòng là một JSON object độc lập → dễ đọc bằng jq, pandas, v.v.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path("logs")
logger  = logging.getLogger(__name__)


def _current_log_file() -> Path:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return LOG_DIR / f"calls_{date_str}.jsonl"


def _write_line(entry: dict) -> None:
    path = _current_log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def log_call(
    # --- Identity ---
    business_action_id: str | None,
    ai_request_id: str,
    workflow_step: str | None,
    tenant_id: str | None,
    user_id: str | None,
    # --- Model ---
    provider: str,
    model_name: str,
    model_version: str | None,
    # --- Content ---
    input_text: str,
    output_text: str | None,
    # --- Tokens ---
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
    reasoning_tokens: int,
    embedding_tokens: int,
    total_tokens: int,
    # --- Cost ---
    raw_provider_cost: float,
    currency: str,
    provider_pricing_version: str,
    # --- Status ---
    status: str,          # success | failed | timeout | validation_failed
    attempt_number: int,
    is_retry: bool,
    is_fallback: bool,
    cache_status: str,    # hit | miss | skipped | not_applicable
    # --- Timestamp ---
    recorded_at: str,
) -> None:
    entry = {
        "business_action_id":     business_action_id,
        "ai_request_id":          ai_request_id,
        "workflow_step":          workflow_step,
        "tenant_id":              tenant_id,
        "user_id":                user_id,
        "provider":               provider,
        "model_name":             model_name,
        "model_version":          model_version,
        "input_text":             input_text,
        "output_text":            output_text,
        "input_tokens":           input_tokens,
        "output_tokens":          output_tokens,
        "cached_input_tokens":    cached_input_tokens,
        "reasoning_tokens":       reasoning_tokens,
        "embedding_tokens":       embedding_tokens,
        "total_tokens":           total_tokens,
        "raw_provider_cost":      raw_provider_cost,
        "currency":               currency,
        "provider_pricing_version": provider_pricing_version,
        "status":                 status,
        "attempt_number":         attempt_number,
        "is_retry":               is_retry,
        "is_fallback":            is_fallback,
        "cache_status":           cache_status,
        "recorded_at":            recorded_at,
    }
    try:
        await asyncio.to_thread(_write_line, entry)
    except Exception as exc:
        logger.warning(f"JSON log write failed: {exc}")
