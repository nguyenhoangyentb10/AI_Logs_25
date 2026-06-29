"""
ask.py — CLI chat tương tác với AI_Log

Dùng:
    python ask.py              # chat tương tác (nhập câu hỏi trực tiếp)
    python ask.py --multi      # test đa lượt tự động
    python ask.py --all        # chạy tất cả test
"""
import asyncio
import argparse

import groq_chat
from model import Message
from services.langfuse_service import flush as langfuse_flush
from core.config import settings

G = "\033[92m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; R = "\033[91m"; E = "\033[0m"


def _sep(title: str = "") -> None:
    print(f"\n{C}{'─'*52}{E}")
    if title:
        print(f"{B}  {title}{E}\n{C}{'─'*52}{E}")


def _print_result(result: dict) -> None:
    print(f"\n{G}{B}🤖 Bot:{E}")
    print(result["response"])
    print(f"\n{Y}⏱  {result['latency_ms']} ms | tokens: {result['usage']['total_tokens']}{E}")
    print(f"{Y}🔍 trace: {settings.langfuse_host}/trace/{result['trace_id']}{E}")


# ── Chế độ chat tương tác ─────────────────────────────────────
async def interactive_chat() -> None:
    _sep("Chat tương tác  (gõ 'exit' để thoát, 'reset' để xoá history)")
    print(f"{C}Model: {settings.default_model}{E}\n")

    session_id = f"interactive-{__import__('uuid').uuid4().hex[:8]}"
    history: list[Message] = []

    while True:
        try:
            user_input = input(f"{B}👤 Bạn:{E} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Y}👋 Thoát.{E}")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print(f"{Y}👋 Thoát.{E}")
            break
        if user_input.lower() == "reset":
            history.clear()
            print(f"{C}🔄 Đã xoá lịch sử hội thoại.{E}\n")
            continue

        try:
            result = await groq_chat.chat(
                user_message=user_input,
                session_id=session_id,
                history=history,
            )
            _print_result(result)

            # Lưu history cho lượt tiếp theo
            history.append(Message(role="user",      content=user_input))
            history.append(Message(role="assistant", content=result["response"]))
            print()

        except Exception as e:
            print(f"{R}❌ Lỗi: {e}{E}\n")


# ── Test cases ────────────────────────────────────────────────
async def test_multi() -> None:
    _sep("Multi-turn chat tự động")
    session_id = "test-multi-001"
    history: list[Message] = []
    turns = [
        "FastAPI là gì? Giải thích ngắn gọn.",
        "Vậy nó khác gì với Flask?",
        "Khi nào nên chọn FastAPI thay vì Flask?",
    ]
    for i, q in enumerate(turns, 1):
        print(f"\n{B}── Lượt {i} ──{E}\n{B}👤 User:{E} {q}")
        result = await groq_chat.chat(user_message=q, session_id=session_id, history=history)
        print(f"{G}{B}🤖 Bot:{E}  {result['response'][:200]}...")
        print(f"{Y}⏱  {result['latency_ms']} ms | tokens: {result['usage']['total_tokens']}{E}")
        history.append(Message(role="user",      content=q))
        history.append(Message(role="assistant", content=result["response"]))
    print(f"\n{Y}🔍 Session: {session_id}{E}")


async def test_custom() -> None:
    _sep("Custom system prompt")
    q = "Giải thích Observer pattern bằng ví dụ Python."
    print(f"{B}👤 User:{E} {q}")
    result = await groq_chat.chat(
        user_message=q,
        session_id="test-custom-001",
        system_prompt="Bạn là senior Python engineer. Trả lời bằng tiếng Anh kèm code Python ngắn gọn.",
    )
    _print_result(result)


# ── Main ──────────────────────────────────────────────────────
async def main() -> None:
    parser = argparse.ArgumentParser(description="CLI chat AI_Log")
    parser.add_argument("--multi",  action="store_true", help="Test đa lượt tự động")
    parser.add_argument("--custom", action="store_true", help="Test custom system prompt")
    parser.add_argument("--all",    action="store_true", help="Chạy tất cả test")
    args = parser.parse_args()

    print(f"\n{C}{B}🚀 AI_Log | model: {settings.default_model}{E}")
    groq_chat.configure()

    try:
        if args.all:
            await test_multi()
            await test_custom()
        elif args.multi:
            await test_multi()
        elif args.custom:
            await test_custom()
        else:
            await interactive_chat()   # ← mặc định: chat tương tác
    finally:
        langfuse_flush()
        print(f"\n{G}✅ Done!{E}\n")


if __name__ == "__main__":
    asyncio.run(main())