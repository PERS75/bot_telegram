import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

# AI provider (NeuroAPI)
AI_PROVIDER = os.getenv("AI_PROVIDER", "neuroapi")
AI_MODEL = os.getenv("AI_MODEL", "gpt-5-mini")

NEUROAPI_API_KEY = os.getenv("NEUROAPI_API_KEY")
NEUROAPI_BASE_URL = os.getenv("NEUROAPI_BASE_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден")

if AI_PROVIDER == "neuroapi":
    if not NEUROAPI_API_KEY:
        raise RuntimeError("NEUROAPI_API_KEY не найден")
    if not NEUROAPI_BASE_URL:
        raise RuntimeError("NEUROAPI_BASE_URL не найден")