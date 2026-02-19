import json
import os
import threading
from pathlib import Path
from typing import Callable

STORAGE_DIR = Path("storage")
SCORES_FILE = STORAGE_DIR / "scores.json"

_lock = threading.Lock()


def _default_payload() -> dict:
    return {"users": {}, "total": {}, "daily": {}}


def ensure_storage() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not SCORES_FILE.exists():
        _atomic_write(_default_payload())


def _read_scores_unlocked() -> dict:
    ensure_storage()
    data = json.loads(SCORES_FILE.read_text(encoding="utf-8"))
    data.setdefault("users", {})
    data.setdefault("total", {})
    data.setdefault("daily", {})
    return data


def _atomic_write(data: dict) -> None:
    tmp = SCORES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SCORES_FILE)


def load_scores() -> dict:
    with _lock:
        return _read_scores_unlocked()


def save_scores(data: dict) -> None:
    with _lock:
        ensure_storage()
        _atomic_write(data)


def update_scores(mutator: Callable[[dict], None]) -> None:
    with _lock:
        data = _read_scores_unlocked()
        mutator(data)
        _atomic_write(data)
