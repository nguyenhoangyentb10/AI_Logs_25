"""
groq_chat.py — Core service: LiteLLM gọi Groq, LangFuse log toàn bộ

Luồng:
  user_message
      │
      ├─► LangFuse.trace()          ← bắt đầu trace request
      │       └─► span("context")  ← build messages / system prompt
      │
      └─► retry loop (max_retries lần)
              └─► litellm.acompletion()    ← gọi Groq API
                      │
                      ├─► Groq trả về response + usage → log_call (success)
                      └─► lỗi transient → log_call (failed) → sleep → retry
"""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

import litellm

from core.config import settings
from model import Message
from services import langfuse_service
from services.json_logger import log_call
from metrics import record_request

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "Bạn là một trợ lý AI thông minh, hữu ích. "
    "Trả lời bằng tiếng Việt trừ khi user yêu cầu ngôn ngữ khác."
)

_PROVIDER_MAP: dict[str, str] = {
    "openai":    "OpenAI",
    "anthropic": "Anthropic",
    "google":    "Google",
    "azure":     "Azure OpenAI",
    "groq":      "Groq",
}

_CACHE_SUPPORTED = {"anthropic", "openai"}

# Lỗi tạm thời — đáng retry; các lỗi còn lại (auth, bad request) không retry
_RETRYABLE = (
    litellm.Timeout,
    litellm.RateLimitError,
    litellm.ServiceUnavailableError,
    litellm.APIConnectionError,
)


def configure() -> None:
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
    litellm.set_verbose = (settings.app_env == "development")
    logger.info("LiteLLM ready — callbacks: langfuse")


def _parse_model(model_str: str) -> tuple[str, str, str | None]:
    if "/" in model_str:
        prefix, name = model_str.split("/", 1)
        provider = _PROVIDER_MAP.get(prefix.lower(), prefix)
    else:
        name = model_str
        provider = "Unknown"

    version: str | None = None
    parts = name.rsplit("-", 3)
    if len(parts) == 4 and len(parts[1]) == 4 and parts[1].isdigit():
        version = "-".join(parts[1:])
        name = parts[0]

    return provider, name, version


def _pricing_version(provider: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{provider.lower().replace(' ', '_')}_{now.year}-{now.month:02d}"


def _extract_token_details(usage) -> tuple[int, int, int]:
    cached = reasoning = 0
    try:
        cached = usage.prompt_tokens_details.cached_tokens or 0
    except AttributeError:
        pass
    try:
        reasoning = usage.completion_tokens_details.reasoning_tokens or 0
    except AttributeError:
        pass
    return cached, reasoning, 0


def _cache_status(provider_key: str, cached_tokens: int) -> str:
    if provider_key not in _CACHE_SUPPORTED:
        return "not_applicable"
    return "hit" if cached_tokens > 0 else "miss"


def _classify_status(exc: Exception) -> str:
    msg = str(exc).lower()
    if isinstance(exc, litellm.Timeout) or "timeout" in msg:
        return "timeout"
    if isinstance(exc, litellm.BadRequestError) or "validation" in msg:
        return "validation_failed"
    return "failed"


async def chat(
    user_message: str,
    session_id: str | None = None,
    system_prompt: str | None = None,
    history: list[Message] | None = None,
    model: str | None = None,
    business_action_id: str | None = None,
    workflow_step: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    model      = model or settings.default_model
    session_id = session_id or str(uuid4())
    messages   = _build_messages(user_message, system_prompt, history or [])

    provider, model_name, model_version = _parse_model(model)
    provider_key = model.split("/")[0].lower() if "/" in model else ""

    last_exc: Exception | None = None

    for attempt in range(1, settings.max_retries + 1):
        is_retry  = attempt > 1
        trace_id  = str(uuid4())          # ai_request_id mới cho mỗi attempt
        started_at = datetime.now(timezone.utc)

        trace = langfuse_service.start_trace(
            trace_id=trace_id,
            session_id=session_id,
            user_message=user_message,
            model=model,
        )
        span = trace.span(name="build-context")
        span.end(output={"message_count": len(messages)})

        try:
            logger.info(
                f"[{trace_id[:8]}] attempt={attempt} → {model} | {len(messages)} msgs"
            )

            response = await litellm.acompletion(
                model=model,
                messages=messages,
                metadata={
                    "generation_name": "groq-completion",
                    "trace_id":   trace_id,
                    "trace_name": "user-chat",
                    "session_id": session_id,
                    "tags": [settings.app_env, "groq"],
                },
            )

            content    = response.choices[0].message.content
            usage      = response.usage
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

            logger.info(
                f"[{trace_id[:8]}] ✓ attempt={attempt} {latency_ms}ms | "
                f"in={usage.prompt_tokens} out={usage.completion_tokens}"
            )

            cached_tokens, reasoning_tokens, embedding_tokens = _extract_token_details(usage)

            try:
                cost = litellm.completion_cost(completion_response=response)
            except Exception:
                cost = 0.0

            usage_dict = {
                "prompt_tokens":     usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens":      usage.total_tokens,
            }

            langfuse_service.end_trace_ok(
                trace=trace, output=content,
                total_tokens=usage.total_tokens, latency_ms=latency_ms,
            )
            await record_request(
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                latency_ms=latency_ms,
                success=True,
            )
            await log_call(
                business_action_id=business_action_id,
                ai_request_id=trace_id,
                workflow_step=workflow_step,
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider,
                model_name=model_name,
                model_version=model_version,
                input_text=user_message,
                output_text=content,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                cached_input_tokens=cached_tokens,
                reasoning_tokens=reasoning_tokens,
                embedding_tokens=embedding_tokens,
                total_tokens=usage.total_tokens,
                raw_provider_cost=cost,
                currency="USD",
                provider_pricing_version=_pricing_version(provider),
                status="success",
                attempt_number=attempt,
                is_retry=is_retry,
                is_fallback=False,
                cache_status=_cache_status(provider_key, cached_tokens),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )

            return {
                "response":   content,
                "trace_id":   trace_id,
                "session_id": session_id,
                "model":      model,
                "usage":      usage_dict,
                "latency_ms": latency_ms,
            }

        except _RETRYABLE as exc:
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            last_exc   = exc
            logger.warning(f"[{trace_id[:8]}] ✗ attempt={attempt} retryable: {exc}")

            langfuse_service.end_trace_error(trace=trace, error=str(exc))
            await record_request(model=model, prompt_tokens=0, completion_tokens=0,
                                 latency_ms=latency_ms, success=False)
            await log_call(
                business_action_id=business_action_id,
                ai_request_id=trace_id,
                workflow_step=workflow_step,
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider,
                model_name=model_name,
                model_version=model_version,
                input_text=user_message,
                output_text=None,
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
                embedding_tokens=0,
                total_tokens=0,
                raw_provider_cost=0.0,
                currency="USD",
                provider_pricing_version=_pricing_version(provider),
                status=_classify_status(exc),
                attempt_number=attempt,
                is_retry=is_retry,
                is_fallback=False,
                cache_status=_cache_status(provider_key, 0),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )

            if attempt < settings.max_retries:
                delay = settings.retry_delay_s * (2 ** (attempt - 1))  # 1s, 2s, 4s
                logger.info(f"[{trace_id[:8]}] sleeping {delay}s before retry...")
                await asyncio.sleep(delay)

        except Exception as exc:
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            logger.error(f"[{trace_id[:8]}] ✗ attempt={attempt} non-retryable: {exc}")

            langfuse_service.end_trace_error(trace=trace, error=str(exc))
            await record_request(model=model, prompt_tokens=0, completion_tokens=0,
                                 latency_ms=latency_ms, success=False)
            await log_call(
                business_action_id=business_action_id,
                ai_request_id=trace_id,
                workflow_step=workflow_step,
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider,
                model_name=model_name,
                model_version=model_version,
                input_text=user_message,
                output_text=None,
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
                embedding_tokens=0,
                total_tokens=0,
                raw_provider_cost=0.0,
                currency="USD",
                provider_pricing_version=_pricing_version(provider),
                status=_classify_status(exc),
                attempt_number=attempt,
                is_retry=is_retry,
                is_fallback=False,
                cache_status=_cache_status(provider_key, 0),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
            raise

    raise last_exc


def _build_messages(
    user_message: str,
    system_prompt: str | None,
    history: list[Message],
) -> list[dict]:
    msgs: list[dict] = [
        {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT}
    ]
    max_turns = settings.max_history_turns
    trimmed = history[-(max_turns * 2):] if history else []
    for m in trimmed:
        msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": user_message})
    return msgs


_QUESTION_SYSTEM_PROMPT = (
    "Bạn là chuyên gia tạo câu hỏi trắc nghiệm. "
    "Dựa trên nội dung được cung cấp, tạo đúng 1 câu hỏi trắc nghiệm với 4 lựa chọn (A, B, C, D), "
    "chỉ 1 đáp án đúng. "
    "Trả về JSON hợp lệ theo đúng format sau, không thêm bất kỳ text nào khác:\n"
    '{"question": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "correct": "A", "explanation": "Giải thích tại sao đáp án đúng..."}'
)


async def generate_question(
    context: str,
    session_id: str | None = None,
    business_action_id: str | None = None,
    workflow_step: str = "generate_question",
    tenant_id: str | None = None,
    user_id: str | None = None,
    model: str | None = None,
) -> dict:
    import json as _json

    model      = model or settings.default_model
    session_id = session_id or str(uuid4())
    messages   = [
        {"role": "system", "content": _QUESTION_SYSTEM_PROMPT},
        {"role": "user",   "content": f"Nội dung:\n{context}"},
    ]

    provider, model_name, model_version = _parse_model(model)
    provider_key = model.split("/")[0].lower() if "/" in model else ""

    last_exc: Exception | None = None

    for attempt in range(1, settings.max_retries + 1):
        is_retry   = attempt > 1
        trace_id   = str(uuid4())
        started_at = datetime.now(timezone.utc)

        trace = langfuse_service.start_trace(
            trace_id=trace_id,
            session_id=session_id,
            user_message=context[:200],
            model=model,
        )

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                metadata={
                    "generation_name": "generate-question",
                    "trace_id":   trace_id,
                    "trace_name": "generate-question",
                    "session_id": session_id,
                    "tags": [settings.app_env, "groq", "quiz"],
                },
            )

            content    = response.choices[0].message.content
            usage      = response.usage
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

            cached_tokens, reasoning_tokens, embedding_tokens = _extract_token_details(usage)

            try:
                cost = litellm.completion_cost(completion_response=response)
            except Exception:
                cost = 0.0

            langfuse_service.end_trace_ok(
                trace=trace, output=content,
                total_tokens=usage.total_tokens, latency_ms=latency_ms,
            )
            await record_request(
                model=model, prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                latency_ms=latency_ms, success=True,
            )
            await log_call(
                business_action_id=business_action_id,
                ai_request_id=trace_id,
                workflow_step=workflow_step,
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider,
                model_name=model_name,
                model_version=model_version,
                input_text=context,
                output_text=content,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                cached_input_tokens=cached_tokens,
                reasoning_tokens=reasoning_tokens,
                embedding_tokens=embedding_tokens,
                total_tokens=usage.total_tokens,
                raw_provider_cost=cost,
                currency="USD",
                provider_pricing_version=_pricing_version(provider),
                status="success",
                attempt_number=attempt,
                is_retry=is_retry,
                is_fallback=False,
                cache_status=_cache_status(provider_key, cached_tokens),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )

            # Parse JSON từ LLM
            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            question_data = _json.loads(raw.strip())

            return {
                "question_data": question_data,
                "trace_id":      trace_id,
                "session_id":    session_id,
                "model":         model,
                "usage": {
                    "prompt_tokens":     usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens":      usage.total_tokens,
                },
                "latency_ms": latency_ms,
            }

        except _RETRYABLE as exc:
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            last_exc   = exc
            langfuse_service.end_trace_error(trace=trace, error=str(exc))
            await record_request(model=model, prompt_tokens=0, completion_tokens=0,
                                 latency_ms=latency_ms, success=False)
            await log_call(
                business_action_id=business_action_id,
                ai_request_id=trace_id,
                workflow_step=workflow_step,
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider,
                model_name=model_name,
                model_version=model_version,
                input_text=context,
                output_text=None,
                input_tokens=0, output_tokens=0,
                cached_input_tokens=0, reasoning_tokens=0,
                embedding_tokens=0, total_tokens=0,
                raw_provider_cost=0.0,
                currency="USD",
                provider_pricing_version=_pricing_version(provider),
                status=_classify_status(exc),
                attempt_number=attempt,
                is_retry=is_retry,
                is_fallback=False,
                cache_status=_cache_status(provider_key, 0),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
            if attempt < settings.max_retries:
                await asyncio.sleep(settings.retry_delay_s * (2 ** (attempt - 1)))

        except Exception as exc:
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            langfuse_service.end_trace_error(trace=trace, error=str(exc))
            await record_request(model=model, prompt_tokens=0, completion_tokens=0,
                                 latency_ms=latency_ms, success=False)
            await log_call(
                business_action_id=business_action_id,
                ai_request_id=trace_id,
                workflow_step=workflow_step,
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider,
                model_name=model_name,
                model_version=model_version,
                input_text=context,
                output_text=None,
                input_tokens=0, output_tokens=0,
                cached_input_tokens=0, reasoning_tokens=0,
                embedding_tokens=0, total_tokens=0,
                raw_provider_cost=0.0,
                currency="USD",
                provider_pricing_version=_pricing_version(provider),
                status=_classify_status(exc),
                attempt_number=attempt,
                is_retry=is_retry,
                is_fallback=False,
                cache_status=_cache_status(provider_key, 0),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
            raise

    raise last_exc
