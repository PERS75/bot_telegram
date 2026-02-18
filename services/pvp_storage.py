import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
import asyncio

_STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

_MATCHES_PATH = _STORAGE_DIR / "pvp_matches.json"

_lock = asyncio.Lock()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


async def get_match(match_id: str) -> Optional[Dict[str, Any]]:
    async with _lock:
        data = _load_json(_MATCHES_PATH)
        return data.get(match_id)


async def upsert_match(match_id: str, match: Dict[str, Any]) -> None:
    async with _lock:
        data = _load_json(_MATCHES_PATH)
        data[match_id] = match
        _atomic_write_json(_MATCHES_PATH, data)


async def delete_match(match_id: str) -> None:
    async with _lock:
        data = _load_json(_MATCHES_PATH)
        if match_id in data:
            data.pop(match_id, None)
            _atomic_write_json(_MATCHES_PATH, data)


async def cleanup_expired(ttl_seconds: int = 60 * 60) -> int:
    """
    Удаляет матчи, которые лежат слишком долго без активности (по updated_at).
    Возвращает количество удалённых.
    """
    now = int(time.time())
    removed = 0
    async with _lock:
        data = _load_json(_MATCHES_PATH)
        to_delete = []
        for mid, m in data.items():
            updated_at = int(m.get("updated_at", m.get("created_at", now)))
            if now - updated_at > ttl_seconds:
                to_delete.append(mid)

        for mid in to_delete:
            data.pop(mid, None)
            removed += 1

        if removed:
            _atomic_write_json(_MATCHES_PATH, data)
    return removed