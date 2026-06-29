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
    # Trường nghiệp vụ theo spec 3.1
    business_action_id: Optional[str] = Field(
        default=None,
        description="ID action nghiệp vụ cha để gom nhiều AI calls cùng 1 action",
    )
    workflow_step: Optional[str] = Field(
        default=None,
        description="Bước cụ thể trong flow/action (ví dụ: generate_questions)",
    )
    tenant_id: Optional[str] = Field(
        default=None,
        description="Tenant sử dụng hệ thống",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="User trigger action nếu có",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "LiteLLM là gì và tại sao nên dùng?",
                "session_id": "session-001",
                "business_action_id": "biz_qgen_20260511_001",
                "workflow_step": "generate_questions",
                "tenant_id": "tenant_viettel_01",
                "user_id": "user_12345",
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
