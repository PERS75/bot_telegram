import json
from pathlib import Path

_here = Path(__file__).resolve().parent
_path = _here / "quiz_questions.json"

with _path.open("r", encoding="utf-8") as f:
    QUIZ_QUESTIONS = json.load(f)