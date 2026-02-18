import json
from pathlib import Path

_DATA_PATH = Path(__file__).with_name("tf_questions.json")

def load_tf_questions():
    with _DATA_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # небольшая валидация, чтобы не падало “тихо”
    if not isinstance(data, list):
        raise ValueError("tf_questions.json должен содержать список вопросов")

    ids = set()
    for q in data:
        for key in ("id", "text", "answer"):
            if key not in q:
                raise ValueError(f"В вопросе нет поля '{key}': {q}")
        if q["id"] in ids:
            raise ValueError(f"Повторяющийся id={q['id']} в tf_questions.json")
        ids.add(q["id"])

    return data

TF_QUESTIONS = load_tf_questions()