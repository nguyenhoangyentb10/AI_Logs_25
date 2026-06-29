"""
api/routes.py — FastAPI router: /chat, /health, /metrics
"""
import logging
from fastapi import APIRouter, HTTPException, status

import groq_chat
import metrics as metrics_module
from model import (ChatRequest, ChatResponse, HealthResponse, TokenUsage,
                   QuestionRequest, QuestionResponse, QuestionData, QuestionOptions,
                   FeedbackRequest, FeedbackResponse, FeedbackData)
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
    return await metrics_module.get_summary()


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
            business_action_id=request.business_action_id,
            workflow_step=request.workflow_step,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
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


@router.post(
    "/generate-question",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Quiz"],
    summary="Sinh câu hỏi trắc nghiệm từ nội dung LLM vừa trả lời",
)
async def generate_question(request: QuestionRequest):
    try:
        result = await groq_chat.generate_question(
            context=request.context,
            session_id=request.session_id,
            business_action_id=request.business_action_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
        )
        qd = result["question_data"]
        return QuestionResponse(
            question_data=QuestionData(
                question=qd["question"],
                options=QuestionOptions(**qd["options"]),
                correct=qd["correct"],
            ),
            trace_id=result["trace_id"],
            session_id=result["session_id"],
            model=result["model"],
            usage=TokenUsage(**result["usage"]),
            latency_ms=result["latency_ms"],
        )
    except EnvironmentError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Generate question error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/analyze-feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    tags=["Feedback"],
    summary="Phân tích feedback của user: tích cực / tiêu cực / trung tính",
)
async def analyze_feedback(request: FeedbackRequest):
    try:
        result = await groq_chat.analyze_feedback(
            feedback=request.feedback,
            session_id=request.session_id,
            business_action_id=request.business_action_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
        )
        fd = result["feedback_data"]
        return FeedbackResponse(
            feedback_data=FeedbackData(
                sentiment=fd["sentiment"],
                score=fd["score"],
                summary=fd["summary"],
            ),
            trace_id=result["trace_id"],
            session_id=result["session_id"],
            model=result["model"],
            usage=TokenUsage(**result["usage"]),
            latency_ms=result["latency_ms"],
        )
    except EnvironmentError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error(f"Analyze feedback error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
