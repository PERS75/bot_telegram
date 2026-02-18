import asyncio
from openai import OpenAI

from config import NEUROAPI_API_KEY, NEUROAPI_BASE_URL, AI_MODEL

client = OpenAI(
    api_key=NEUROAPI_API_KEY,
    base_url=NEUROAPI_BASE_URL,
)

SYSTEM_INSTRUCTIONS = (
    "Ты — «Цифровой экономист» для школьников 12–17 лет. "
    "Отвечай простым русским языком, коротко и по делу (5–8 предложений). "
    "Объясняй на примерах из жизни. "
    "Если вопрос не по экономике — вежливо скажи об этом и предложи экономическую формулировку. "
    "Не обсуждай политику и не давай инвестиционных рекомендаций."
)

def _sync_call(user_question: str) -> str:
    resp = client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_question},
        ],
    )
    return (resp.choices[0].message.content or "").strip()

async def ask_economist(user_question: str) -> str:
    return await asyncio.to_thread(_sync_call, user_question)
