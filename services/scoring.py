from datetime import datetime
from zoneinfo import ZoneInfo

from services.storage import load_scores, save_scores

TZ = ZoneInfo("Europe/Amsterdam")

def _today_key() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")

def upsert_user(user_id: int, full_name: str | None, username: str | None):
    """
    Сохраняем данные пользователя, чтобы потом показывать имена в лидерборде.
    """
    data = load_scores()
    uid = str(user_id)

    # как показывать пользователя по умолчанию
    display = f"@{username}" if username else (full_name or uid)

    data["users"][uid] = {
        "display": display,
        "username": username or "",
        "full_name": full_name or "",
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
    }
    save_scores(data)

def add_points(user_id: int, points: int):
    data = load_scores()
    uid = str(user_id)

    # total
    data["total"][uid] = data["total"].get(uid, 0) + points

    # daily
    day = _today_key()
    data["daily"].setdefault(day, {})
    data["daily"][day][uid] = data["daily"][day].get(uid, 0) + points

    save_scores(data)

def get_profile(user_id: int):
    data = load_scores()
    uid = str(user_id)

    total = data["total"].get(uid, 0)
    day = _today_key()
    today_points = data["daily"].get(day, {}).get(uid, 0)
    return total, today_points

def get_user_display(user_id: int) -> str:
    data = load_scores()
    uid = str(user_id)
    return data["users"].get(uid, {}).get("display", uid)

def get_leaderboard(limit=10):
    """
    Топ по total (всего)
    Возвращает список (user_id, points)
    """
    data = load_scores()
    items = [(int(uid), pts) for uid, pts in data["total"].items()]
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:limit]

def get_daily_leaderboard(limit=10):
    """
    Топ за сегодня.
    Возвращает (items, day_key)
    """
    data = load_scores()
    day = _today_key()
    items = [(int(uid), pts) for uid, pts in data["daily"].get(day, {}).items()]
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:limit], day