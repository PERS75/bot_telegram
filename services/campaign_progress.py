import json
import os
from typing import Dict, Any

FILE_PATH = os.path.join("storage", "campaign_progress.json")


def _load() -> Dict[str, Any]:
    if not os.path.exists(FILE_PATH):
        return {}
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_current_chapter(user_id: int, default: int = 1) -> int:
    data = _load()
    ch = data.get(str(user_id), {}).get("chapter", default)
    try:
        return int(ch)
    except Exception:
        return default


def set_current_chapter(user_id: int, chapter: int) -> None:
    data = _load()
    key = str(user_id)
    data.setdefault(key, {})
    data[key]["chapter"] = int(chapter)
    _save(data)