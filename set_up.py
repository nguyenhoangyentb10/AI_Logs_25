"""
setup.py — Scaffold generator, chỉ dùng để tạo project lần đầu.

DEPRECATED: Project đã được tạo. File này không còn được cập nhật
và có thể không đồng bộ với code hiện tại. Không dùng trong production.
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def write(path: str, content: str) -> None:
    full = os.path.join(BASE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ {path}")


# ══════════════════════════════════════════════════════════════
FILES = {}
# ══════════════════════════════════════════════════════════════

FILES["api/__init__.py"] = ""

FILES["core/__init__.py"] = ""

FILES["services/__init__.py"] = ""

FILES["logs/.gitkeep"] = ""

# ── .env.example ──────────────────────────────────────────────
FILES[".env.example"] = """\
# ── Groq ──────────────────────────────────────────────────────
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── LangFuse ──────────────────────────────────────────────────
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com

# ── App ───────────────────────────────────────────────────────
APP_ENV=development
LOG_LEVEL=INFO
DEFAULT_MODEL=groq/llama-3.3-70b-versatile
"""

# ── requirements.txt ──────────────────────────────────────────
FILES["requirements.txt"] = """\
fastapi==0.115.0
uvicorn[standard]==0.30.6
litellm==1.49.0
langfuse==2.53.0
python-dotenv==1.0.1
pydantic==2.9.2
httpx==0.27.2
"""

# ── core/config.py ────────────────────────────────────────────
FILES["core/config.py"] = '''\
"""
core/config.py — Load env vars + validate khi app khởi động
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str
    default_model: str
    log_level: str
    app_env: str

    def validate(self) -> None:
        missing = [
            name for name, val in [
                ("GROQ_API_KEY",          self.groq_api_key),
                ("LANGFUSE_PUBLIC_KEY",   self.langfuse_public_key),
                ("LANGFUSE_SECRET_KEY",   self.langfuse_secret_key),
            ] if not val
        ]
        if missing:
            raise EnvironmentError(
                f"❌ Thiếu env vars: {', \'.join(missing)}\\n"
                "👉 Copy .env.example → .env rồi điền API keys vào."
            )


def get_settings() -> Settings:
    s = Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        langfuse_host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        default_model=os.getenv("DEFAULT_MODEL", "groq/llama-3.3-70b-versatile"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        app_env=os.getenv("APP_ENV", "development"),
    )
    s.validate()
    return s


settings = get_settings()
'''

# ── model.py ──────────────────────────────────────────────────
FILES["model.py"] = '''\
"""
model.py — Pydantic models dùng chung cho API + service layer
"""
from pydantic import BaseModel, Field
from typing import Optional


class Message(BaseModel):
    """Một lượt hội thoại trong history."""
    role: str = Field(..., examples=["user", "assistant", "system"])
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Câu hỏi từ user")
    session_id: Optional[str] = Field(
        default=None,
        description="ID phiên — group nhiều lượt lại trong LangFuse",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="System prompt tuỳ chỉnh (không bắt buộc)",
    )
    history: list[Message] = Field(
        default_factory=list,
        description="Lịch sử hội thoại để giữ context đa lượt",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "LiteLLM là gì và tại sao nên dùng?",
                "session_id": "session-001",
            }
        }
    }


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    response: str       = Field(..., description="Câu trả lời từ LLM")
    trace_id: str       = Field(..., description="ID trace trong LangFuse")
    session_id: str     = Field(..., description="ID phiên chat")
    model: str          = Field(..., description="Model đã dùng")
    usage: TokenUsage
    latency_ms: int     = Field(..., description="Thời gian xử lý (ms)")


class HealthResponse(BaseModel):
    status: str
    model: str
    langfuse_host: str
    env: str
'''

# ── services/langfuse_service.py ──────────────────────────────
FILES["services/langfuse_service.py"] = '''\
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
    get_client().flush()


def end_trace_error(trace, error: str) -> None:
    trace.update(level="ERROR", status_message=error, output={"error": error})
    get_client().flush()
'''

# ── groq_chat.py ──────────────────────────────────────────────
FILES["groq_chat.py"] = '''\
"""
groq_chat.py — Core service: LiteLLM gọi Groq, LangFuse log toàn bộ

Luồng:
  user_message
      │
      ├─► LangFuse.trace()          ← bắt đầu trace request
      │       └─► span("context")  ← build messages / system prompt
      │
      └─► litellm.acompletion()    ← gọi Groq API
              │
              ├─► Groq trả về response + usage
              └─► LangFuse auto-nhận generation qua success_callback
"""
import os
import logging
from uuid import uuid4
from datetime import datetime, timezone

import litellm

from core.config import settings
from model import Message
from services import langfuse_service
from metrics import record_request

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "Bạn là một trợ lý AI thông minh, hữu ích. "
    "Trả lời bằng tiếng Việt trừ khi user yêu cầu ngôn ngữ khác."
)


def _configure() -> None:
    os.environ["GROQ_API_KEY"]          = settings.groq_api_key
    os.environ["LANGFUSE_PUBLIC_KEY"]   = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"]   = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"]         = settings.langfuse_host
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
    litellm.set_verbose = (settings.app_env == "development")
    logger.info("✅ LiteLLM ready — callbacks: langfuse")


_configure()


async def chat(
    user_message: str,
    session_id: str | None = None,
    system_prompt: str | None = None,
    history: list[Message] | None = None,
    model: str | None = None,
) -> dict:
    model      = model or settings.default_model
    trace_id   = str(uuid4())
    session_id = session_id or str(uuid4())
    started_at = datetime.now(timezone.utc)

    # 1. Bắt đầu LangFuse trace
    trace = langfuse_service.start_trace(
        trace_id=trace_id,
        session_id=session_id,
        user_message=user_message,
        model=model,
    )

    # 2. Span: build context
    span = trace.span(name="build-context")
    messages = _build_messages(user_message, system_prompt, history or [])
    span.end(output={"message_count": len(messages)})

    # 3. Gọi Groq qua LiteLLM
    try:
        logger.info(f"[{trace_id[:8]}] → {model} | {len(messages)} messages")

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

        content: str = response.choices[0].message.content
        usage        = response.usage
        latency_ms   = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )

        logger.info(
            f"[{trace_id[:8]}] ✓ {latency_ms}ms | "
            f"in={usage.prompt_tokens} out={usage.completion_tokens}"
        )

        # 4. Kết thúc trace + ghi metrics
        langfuse_service.end_trace_ok(
            trace=trace, output=content,
            total_tokens=usage.total_tokens, latency_ms=latency_ms,
        )
        record_request(
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
            success=True,
        )

        return {
            "response":   content,
            "trace_id":   trace_id,
            "session_id": session_id,
            "model":      model,
            "usage": {
                "prompt_tokens":     usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens":      usage.total_tokens,
            },
            "latency_ms": latency_ms,
        }

    except Exception as exc:
        latency_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )
        langfuse_service.end_trace_error(trace=trace, error=str(exc))
        record_request(model=model, prompt_tokens=0, completion_tokens=0,
                       latency_ms=latency_ms, success=False)
        logger.error(f"[{trace_id[:8]}] ✗ {exc}")
        raise


def _build_messages(
    user_message: str,
    system_prompt: str | None,
    history: list[Message],
) -> list[dict]:
    msgs: list[dict] = [
        {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT}
    ]
    for m in history:
        msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": user_message})
    return msgs
'''

# ── metrics.py ────────────────────────────────────────────────
FILES["metrics.py"] = '''\
"""
metrics.py — In-memory metrics: request count, token usage, latency, error rate
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock


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
_lock  = Lock()


def record_request(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    success: bool,
) -> None:
    with _lock:
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


def get_summary() -> dict:
    with _lock:
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


def reset() -> None:
    global _stats
    with _lock:
        _stats = _Stats()
'''

# ── api/routes.py ─────────────────────────────────────────────
FILES["api/routes.py"] = '''\
"""
api/routes.py — FastAPI router: /chat, /health, /metrics
"""
import logging
from fastapi import APIRouter, HTTPException, status

import groq_chat
import metrics as metrics_module
from model import ChatRequest, ChatResponse, HealthResponse, TokenUsage
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    return HealthResponse(
        status="ok",
        model=settings.default_model,
        langfuse_host=settings.langfuse_host,
        env=settings.app_env,
    )


@router.get("/metrics", tags=["System"], summary="Token usage, latency, error rate")
async def get_metrics():
    return metrics_module.get_summary()


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    tags=["Chat"],
    summary="Gửi câu hỏi → Groq trả lời, LangFuse log",
)
async def chat(request: ChatRequest):
    try:
        result = await groq_chat.chat(
            user_message=request.message,
            session_id=request.session_id,
            system_prompt=request.system_prompt,
            history=request.history,
        )
        return ChatResponse(
            response=result["response"],
            trace_id=result["trace_id"],
            session_id=result["session_id"],
            model=result["model"],
            usage=TokenUsage(**result["usage"]),
            latency_ms=result["latency_ms"],
        )
    except EnvironmentError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Chat route error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
'''

# ── main.py ───────────────────────────────────────────────────
FILES["main.py"] = '''\
"""
main.py — Entry point FastAPI app

Chạy:
    python main.py
    uvicorn main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from api.routes import router
from services.langfuse_service import flush as langfuse_flush

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 AI_Log starting up")
    logger.info(f"   Env     : {settings.app_env}")
    logger.info(f"   Model   : {settings.default_model}")
    logger.info(f"   LangFuse: {settings.langfuse_host}")
    yield
    logger.info("🛑 Shutting down — flushing LangFuse...")
    langfuse_flush()
    logger.info("✅ Shutdown complete")


app = FastAPI(
    title="AI_Log — Groq + LiteLLM + LangFuse",
    description="User hỏi → LiteLLM gọi Groq → LangFuse log trace/generation/tokens",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
'''

# ── ask.py ────────────────────────────────────────────────────
FILES["ask.py"] = '''\
"""
ask.py — CLI test không cần chạy server

Dùng:
    python ask.py                      # câu hỏi mặc định
    python ask.py "Câu hỏi của bạn"
    python ask.py --multi              # test đa lượt
    python ask.py --all                # chạy tất cả
"""
import asyncio
import argparse

import groq_chat
from model import Message
from services.langfuse_service import flush as langfuse_flush
from core.config import settings

G = "\\033[92m"; Y = "\\033[93m"; C = "\\033[96m"; B = "\\033[1m"; E = "\\033[0m"


def _sep(title: str = "") -> None:
    print(f"\\n{C}{"─"*52}{E}")
    if title:
        print(f"{B}  {title}{E}\\n{C}{"─"*52}{E}")


def _print_result(result: dict) -> None:
    print(f"\\n{G}{B}🤖 Trả lời:{E}\\n{result[\'response\']}")
    print(f"\\n{Y}📊 Usage   : {result[\'usage\']}{E}")
    print(f"{Y}⏱  Latency : {result[\'latency_ms\']} ms{E}")
    print(f"{Y}🔍 Trace   : {settings.langfuse_host}/trace/{result[\'trace_id\']}{E}")


async def test_single(question: str | None = None) -> None:
    _sep("Single-turn chat")
    q = question or "LiteLLM là gì và tại sao nên dùng khi build LLM app?"
    print(f"{B}👤 User:{E} {q}")
    result = await groq_chat.chat(user_message=q, session_id="ask-single-001")
    _print_result(result)


async def test_multi() -> None:
    _sep("Multi-turn chat")
    session_id = "ask-multi-001"
    history: list[Message] = []
    turns = [
        "FastAPI là gì? Giải thích ngắn gọn.",
        "Vậy nó khác gì với Flask?",
        "Khi nào nên chọn FastAPI thay vì Flask?",
    ]
    for i, q in enumerate(turns, 1):
        print(f"\\n{B}── Lượt {i} ──{E}\\n{B}👤 User:{E} {q}")
        result = await groq_chat.chat(user_message=q, session_id=session_id, history=history)
        print(f"{G}{B}🤖 Bot:{E}  {result[\'response\'][:200]}...")
        print(f"{Y}⏱  {result[\'latency_ms\']} ms | tokens: {result[\'usage\'][\'total_tokens\']}{E}")
        history.append(Message(role="user",      content=q))
        history.append(Message(role="assistant", content=result["response"]))
    print(f"\\n{Y}🔍 Session ID: {session_id}{E}")


async def test_custom() -> None:
    _sep("Custom system prompt")
    q = "Giải thích Observer pattern bằng ví dụ Python."
    print(f"{B}👤 User:{E} {q}")
    result = await groq_chat.chat(
        user_message=q,
        session_id="ask-custom-001",
        system_prompt="Bạn là senior Python engineer. Trả lời bằng tiếng Anh kèm code Python ngắn gọn.",
    )
    _print_result(result)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?")
    parser.add_argument("--multi",  action="store_true")
    parser.add_argument("--custom", action="store_true")
    parser.add_argument("--all",    action="store_true")
    args = parser.parse_args()

    print(f"\\n{C}{B}🚀 AI_Log — ask.py | model: {settings.default_model}{E}")
    try:
        if args.all:
            await test_single(); await test_multi(); await test_custom()
        elif args.multi:  await test_multi()
        elif args.custom: await test_custom()
        else:             await test_single(args.question)
    finally:
        langfuse_flush()
        print(f"\\n{G}✅ Done — kiểm tra LangFuse dashboard!{E}\\n")


if __name__ == "__main__":
    asyncio.run(main())
'''

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n🚀 Đang tạo project AI_Log...\n")
    for path, content in FILES.items():
        write(path, content)

    print(f"""
✅ Xong! Cấu trúc project:

  AI_Log/
  ├── api/
  │   ├── __init__.py
  │   └── routes.py
  ├── core/
  │   ├── __init__.py
  │   └── config.py
  ├── logs/
  ├── services/
  │   ├── __init__.py
  │   └── langfuse_service.py
  ├── ask.py
  ├── groq_chat.py
  ├── main.py
  ├── metrics.py
  ├── model.py
  └── requirements.txt

Bước tiếp theo:
  1. cp .env.example .env          ← điền API keys
  2. pip install -r requirements.txt
  3. python ask.py                  ← test CLI
  4. python main.py                 ← chạy server
""")