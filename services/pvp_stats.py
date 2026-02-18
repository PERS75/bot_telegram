import json
import os
from pathlib import Path
from typing import Dict

_STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

_STATS_PATH = _STORAGE_DIR / "pvp_stats.json"


def _load() -> Dict[str, dict]:
    if not _STATS_PATH.exists():
        return {}
    try:
        with _STATS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: Dict[str, dict]) -> None:
    tmp = _STATS_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STATS_PATH)


def ensure_user(uid: int) -> None:
    data = _load()
    key = str(uid)
    if key not in data:
        data[key] = {"wins": 0, "losses": 0, "draws": 0}
        _save(data)


def add_win(uid: int):
    data = _load()
    key = str(uid)
    data.setdefault(key, {"wins": 0, "losses": 0, "draws": 0})
    data[key]["wins"] += 1
    _save(data)


def add_loss(uid: int):
    data = _load()
    key = str(uid)
    data.setdefault(key, {"wins": 0, "losses": 0, "draws": 0})
    data[key]["losses"] += 1
    _save(data)


def add_draw(uid: int):
    data = _load()
    key = str(uid)
    data.setdefault(key, {"wins": 0, "losses": 0, "draws": 0})
    data[key]["draws"] += 1
    _save(data)


def get_stats(uid: int) -> dict:
    data = _load()
    return data.get(str(uid), {"wins": 0, "losses": 0, "draws": 0})