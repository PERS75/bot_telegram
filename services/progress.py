from datetime import datetime
from zoneinfo import ZoneInfo

from services.storage import load_scores, save_scores

TZ = ZoneInfo("Europe/Amsterdam")

def today_key() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")

def get_seen_today(user_id: int, game: str) -> set[int]:
    data = load_scores()
    day = today_key()
    uid = str(user_id)

    data.setdefault("progress", {})
    data["progress"].setdefault(game, {})
    data["progress"][game].setdefault(day, {})
    seen_list = data["progress"][game][day].get(uid, [])
    return set(int(x) for x in seen_list)

def mark_seen_today(user_id: int, game: str, qid: int) -> None:
    data = load_scores()
    day = today_key()
    uid = str(user_id)

    data.setdefault("progress", {})
    data["progress"].setdefault(game, {})
    data["progress"][game].setdefault(day, {})
    data["progress"][game][day].setdefault(uid, [])

    if qid not in data["progress"][game][day][uid]:
        data["progress"][game][day][uid].append(qid)

    save_scores(data)