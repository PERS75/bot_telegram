import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Tuple

TZ = ZoneInfo("Europe/Amsterdam")

_STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

_PATH = _STORAGE_DIR / "streaks.json"


def _today_key() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def _load() -> Dict[str, dict]:
    if not _PATH.exists():
        return {}
    try:
        with _PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: Dict[str, dict]) -> None:
    tmp = _PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)


def _ensure_game(u: dict, game: str) -> None:
    if "games" not in u:
        u["games"] = {}
    if game not in u["games"]:
        u["games"][game] = {
            "streak": 0,
            "best": 0,
            "day": _today_key()
        }


def _reset_if_new_day(u: dict, game: str) -> None:
    today = _today_key()
    if u["games"][game].get("day") != today:
        u["games"][game]["streak"] = 0
        u["games"][game]["day"] = today


def streak_bonus(streak: int) -> int:
    """
    Бонусы за серию (можешь менять как хочешь):
    3 подряд -> +1
    5 подряд -> +2
    7 подряд -> +3
    10 подряд -> +5
    """
    if streak == 3:
        return 1
    if streak == 5:
        return 2
    if streak == 7:
        return 3
    if streak == 10:
        return 5
    return 0


def update_streak(user_id: int, game: str, is_correct: bool) -> Tuple[int, int, int]:
    """
    Обновляет стрик для конкретной игры.
    Возвращает (current_streak, best_streak, bonus_points)
    """
    data = _load()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"games": {}}

    _ensure_game(data[uid], game)
    _reset_if_new_day(data[uid], game)

    g = data[uid]["games"][game]

    if is_correct:
        g["streak"] = int(g.get("streak", 0)) + 1
        if g["streak"] > int(g.get("best", 0)):
            g["best"] = g["streak"]
        bonus = streak_bonus(g["streak"])
    else:
        g["streak"] = 0
        bonus = 0

    _save(data)
    return int(g["streak"]), int(g["best"]), int(bonus)


def streak_line(streak: int) -> str:
    if streak <= 0:
        return ""
    # компактно и понятно
    return f"🔥 Серия: {streak}"