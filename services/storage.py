import json
from pathlib import Path

STORAGE_DIR = Path("storage")
SCORES_FILE = STORAGE_DIR / "scores.json"

def ensure_storage():
    STORAGE_DIR.mkdir(exist_ok=True)
    if not SCORES_FILE.exists():
        SCORES_FILE.write_text(
            json.dumps({"users": {}, "total": {}, "daily": {}}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

def load_scores() -> dict:
    ensure_storage()
    data = json.loads(SCORES_FILE.read_text(encoding="utf-8"))

    # совместимость со старыми версиями
    data.setdefault("users", {})
    data.setdefault("total", {})
    data.setdefault("daily", {})
    return data

def save_scores(data: dict) -> None:
    ensure_storage()
    SCORES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )