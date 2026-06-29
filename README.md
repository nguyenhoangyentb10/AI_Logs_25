# AI_Logs_25

Hệ thống chat AI tích hợp **Groq + LiteLLM + LangFuse**, log toàn bộ mỗi LLM call ra file JSONL với **25 fields** theo spec chuẩn.

---

## Tính năng

- **Bước 1 — Trả lời**: User hỏi → LLM trả lời
- **Bước 2 — Trắc nghiệm**: Sinh 1 câu hỏi 4 lựa chọn từ nội dung vừa trả lời → User chọn đáp án → Hiển thị kết quả + giải thích
- **Bước 3 — Feedback**: User nhập feedback → LLM phân tích tích cực / tiêu cực / trung tính

Cả 3 bước cùng `business_action_id` → **3 dòng log, 1 trace trên LangFuse**.

---

## Cấu trúc project

```
AI_Logs_25/
├── api/
│   └── routes.py               # FastAPI endpoints: /chat, /generate-question, /analyze-feedback
├── core/
│   └── config.py               # Load env vars
├── services/
│   ├── json_logger.py          # Ghi JSONL 25 fields
│   └── langfuse_service.py     # LangFuse trace/span/generation
├── logs/
│   └── calls_YYYY-MM-DD.jsonl  # Log file (rotate theo ngày)
├── groq_chat.py                # Core: chat(), generate_question(), analyze_feedback()
├── model.py                    # Pydantic models
├── metrics.py                  # In-memory metrics
├── main.py                     # FastAPI app entry point
└── ask.py                      # CLI tương tác
```

---

## Cài đặt

```bash
# 1. Clone repo
git clone https://github.com/nguyenhoangyentb10/AI_Logs_25.git
cd AI_Logs_25

# 2. Cài dependencies
pip install -r requirements.txt

# 3. Tạo file .env
cp .env.example .env
# Điền API keys vào .env
```

### Nội dung `.env`

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
APP_ENV=development
DEFAULT_MODEL=groq/llama-3.3-70b-versatile
```

---

## Chạy

### CLI (không cần server)

```bash
python ask.py
```

### FastAPI server

```bash
python main.py
# hoặc
uvicorn main:app --reload
```

Swagger UI: `http://localhost:8000/docs`

---

## API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/chat` | Gửi câu hỏi, nhận câu trả lời |
| POST | `/generate-question` | Sinh câu hỏi trắc nghiệm từ nội dung |
| POST | `/analyze-feedback` | Phân tích sentiment feedback |
| GET | `/metrics` | Thống kê token, latency, error rate |
| GET | `/health` | Kiểm tra trạng thái server |

### Ví dụ gọi API đầy đủ 1 flow

```bash
# Bước 1: Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Machine learning là gì?",
    "session_id": "session-001",
    "business_action_id": "flow-001",
    "workflow_step": "answer",
    "tenant_id": "tenant_fci",
    "user_id": "user_123"
  }'

# Bước 2: Sinh câu hỏi
curl -X POST http://localhost:8000/generate-question \
  -H "Content-Type: application/json" \
  -d '{
    "context": "<câu trả lời từ bước 1>",
    "session_id": "session-001",
    "business_action_id": "flow-001"
  }'

# Bước 3: Phân tích feedback
curl -X POST http://localhost:8000/analyze-feedback \
  -H "Content-Type: application/json" \
  -d '{
    "feedback": "Câu trả lời rất hay và dễ hiểu!",
    "session_id": "session-001",
    "business_action_id": "flow-001"
  }'
```

---

## Schema log JSONL (25 fields)

Mỗi LLM call ghi 1 dòng vào `logs/calls_YYYY-MM-DD.jsonl`:

| Nhóm | Fields |
|------|--------|
| **Identity** | `business_action_id`, `ai_request_id`, `workflow_step`, `tenant_id`, `user_id` |
| **Model** | `provider`, `model_name`, `model_version` |
| **Content** | `input_text`, `output_text` |
| **Tokens** | `input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_tokens`, `embedding_tokens`, `total_tokens` |
| **Cost** | `raw_provider_cost`, `currency`, `provider_pricing_version` |
| **Status** | `status`, `attempt_number`, `is_retry`, `is_fallback`, `cache_status` |
| **Timestamp** | `recorded_at` |

### Ví dụ 1 flow đầy đủ (3 dòng cùng `business_action_id`)

```
{"business_action_id": "flow-001", "workflow_step": "answer",            "input_tokens": 71,  ...}
{"business_action_id": "flow-001", "workflow_step": "generate_question", "input_tokens": 600, ...}
{"business_action_id": "flow-001", "workflow_step": "analyze_feedback",  "input_tokens": 122, ...}
```

---

## LangFuse Observability

Mỗi flow tạo **1 parent trace** chứa **3 generation con**:

```
trace: user-flow  (business_action_id)
  ├── generation: answer
  ├── generation: generate_question
  └── generation: analyze_feedback
```

---

## Tech stack

- [Groq](https://groq.com) — LLM inference tốc độ cao
- [LiteLLM](https://github.com/BerriAI/litellm) — Unified LLM API
- [LangFuse](https://langfuse.com) — LLM observability & tracing
- [FastAPI](https://fastapi.tiangolo.com) — Web framework
