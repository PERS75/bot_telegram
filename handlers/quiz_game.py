import random
from math import ceil

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.quiz_questions import QUIZ_QUESTIONS
from services.scoring import add_points, upsert_user
from services.progress import get_seen_today, mark_seen_today
from services.points_text_tfgame import points_text
from services.streaks import update_streak, streak_line

router = Router()

active_question = {}  # user_id -> question_dict

DIFFICULTY_EMOJI = {
    1: "🟢",
    2: "🔵",
    3: "🟡",
    4: "🟠",
    5: "🔴",
}

LETTER = {0: "A", 1: "B", 2: "C", 3: "D"}


def difficulty_badge(pts: int) -> str:
    pts = max(1, min(5, int(pts)))
    return f"{DIFFICULTY_EMOJI[pts]} Сложность: {pts}/5"


def pick_unseen_question(user_id: int):
    seen = get_seen_today(user_id, "quiz")
    unseen = [q for q in QUIZ_QUESTIONS if q["id"] not in seen]
    if not unseen:
        return None
    return random.choice(unseen)


def quiz_kb(qid: int):
    kb = InlineKeyboardBuilder()
    # 4 варианта ответа (0..3)
    kb.button(text="A", callback_data=f"quiz:ans:{qid}:0")
    kb.button(text="B", callback_data=f"quiz:ans:{qid}:1")
    kb.button(text="C", callback_data=f"quiz:ans:{qid}:2")
    kb.button(text="D", callback_data=f"quiz:ans:{qid}:3")

    kb.button(text="⛔ Стоп", callback_data="quiz:stop")
    kb.button(text="🎮 Игры", callback_data="menu:games")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")

    kb.adjust(4, 1, 1, 1)
    return kb.as_markup()


def stop_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎮 Игры", callback_data="menu:games")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def render_question(q: dict) -> str:
    pts = int(q.get("points", 3))
    badge = difficulty_badge(pts)

    opts = q.get("options", [])
    # показываем варианты текста под вопросом
    options_text = "\n".join(
        f"{LETTER[i]}. {opts[i]}" for i in range(min(4, len(opts)))
    )

    return f"🧠 Викторина\n\n{badge}\n\n❓ {q['text']}\n\n{options_text}\n\nВыбери A/B/C/D кнопками ниже:"


@router.callback_query(F.data == "quiz:stop")
async def quiz_stop(cb: CallbackQuery):
    active_question.pop(cb.from_user.id, None)
    await cb.message.edit_text("Ок, остановил викторину ✅\n\nКуда дальше?", reply_markup=stop_kb())
    await cb.answer()


@router.callback_query(F.data == "quiz:start")
async def quiz_start(cb: CallbackQuery):
    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)

    q = pick_unseen_question(cb.from_user.id)
    if not q:
        await cb.message.edit_text("Сегодня вопросы викторины закончились 🎉\n\nВозвращайся завтра!", reply_markup=stop_kb())
        await cb.answer()
        return

    active_question[cb.from_user.id] = q
    await cb.message.edit_text(render_question(q), reply_markup=quiz_kb(q["id"]))
    await cb.answer()


@router.callback_query(F.data.startswith("quiz:ans:"))
async def quiz_answer(cb: CallbackQuery):
    parts = cb.data.split(":")
    # quiz:ans:<qid>:<opt>
    qid = int(parts[2])
    user_opt = int(parts[3])

    q = active_question.get(cb.from_user.id)
    if not q or q["id"] != qid:
        await cb.answer("Этот вопрос уже неактуален 🙂", show_alert=True)
        return

    pts = int(q.get("points", 3))
    badge = difficulty_badge(pts)

    correct_opt = int(q["answer"])
    is_correct = (user_opt == correct_opt)

    cur_streak, best_streak, bonus = update_streak(cb.from_user.id, "quiz", is_correct)
    streak_text = streak_line(cur_streak)

    if is_correct:
        # начисляем очки за вопрос
        add_points(cb.from_user.id, pts)

        # бонус за серию — только при правильном ответе
        if bonus > 0:
            add_points(cb.from_user.id, bonus)
            bonus_text = f" 🎁 Бонус: {points_text(bonus)}"
        else:
            bonus_text = ""

        verdict = f"{badge}\n✅ Верно! {points_text(pts)}{bonus_text}"
        if streak_text:
            verdict += f"\n\n{streak_text}"

    else:
        # штраф за ошибку
        penalty = -ceil(pts / 2)
        add_points(cb.from_user.id, penalty)

        correct_letter = LETTER.get(correct_opt, "?")
        correct_text = q["options"][correct_opt] if q.get("options") else ""

        verdict = (
            f"{badge}\n❌ Неверно! {points_text(penalty)}\n\n"
            f"✅ Правильный ответ: {correct_letter}. {correct_text}"
        )

    explain = q.get("explain")
    if explain:
        verdict = f"{verdict}\n\n💡 {explain}"

    mark_seen_today(cb.from_user.id, "quiz", qid)
    active_question.pop(cb.from_user.id, None)

    nxt = pick_unseen_question(cb.from_user.id)
    if not nxt:
        await cb.message.edit_text(f"{verdict}\n\nСегодня вопросы викторины закончились 🎉", reply_markup=stop_kb())
        await cb.answer()
        return

    active_question[cb.from_user.id] = nxt
    await cb.message.edit_text(f"{verdict}\n\n— — —\n\n{render_question(nxt)}", reply_markup=quiz_kb(nxt["id"]))
    await cb.answer()