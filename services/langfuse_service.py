"""
services/langfuse_service.py — LangFuse client + helper tạo trace/span/generation

Chỉ quản lý observability, không chứa logic LLM.
"""
import logging
from langfuse import Langfuse
from core.config import settings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None


def get_client() -> Langfuse:
    global _client
    if _client is None:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info(f"✅ LangFuse connected → {settings.langfuse_host}")
    return _client


def flush() -> None:
    """Gọi khi shutdown để không mất log nào còn trong buffer."""
    if _client:
        _client.flush()
        logger.info("✅ LangFuse buffer flushed")


def start_trace(trace_id: str, session_id: str, user_message: str, model: str):
    """Tạo trace bao quanh toàn bộ request."""
    return get_client().trace(
        id=trace_id,
        name="user-chat",
        session_id=session_id,
        input=user_message,
        metadata={"model": model, "env": settings.app_env},
        tags=[settings.app_env, "groq", "litellm"],
    )


def end_trace_ok(trace, output: str, total_tokens: int, latency_ms: int) -> None:
    trace.update(
        output=output,
        metadata={"total_tokens": total_tokens, "latency_ms": latency_ms},
    )


def end_trace_error(trace, error: str) -> None:
    trace.update(level="ERROR", status_message=error, output={"error": error})


def create_flow_trace(flow_id: str, session_id: str, input_text: str):
    """Tạo parent trace bao toàn bộ luồng (answer + generate_question)."""
    return get_client().trace(
        id=flow_id,
        name="user-flow",
        session_id=session_id,
        input=input_text,
        tags=[settings.app_env, "flow"],
    )


def end_flow_trace(trace, output: str) -> None:
    """Đóng parent trace sau khi luồng hoàn tất."""
    trace.update(output=output)
    get_client().flush()
