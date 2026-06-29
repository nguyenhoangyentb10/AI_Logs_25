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
import groq_chat

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
    groq_chat.configure()
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
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
