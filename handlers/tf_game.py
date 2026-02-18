import random
from math import ceil
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.tf_questions import TF_QUESTIONS
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

def difficulty_badge(pts: int) -> str:
    pts = max(1, min(5, int(pts)))
    return f"\n {DIFFICULTY_EMOJI[pts]} Сложность: {pts}/5\n"


def question_kb(qid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Правда", callback_data=f"tf:ans:{qid}:1")
    kb.button(text="❌ Ложь", callback_data=f"tf:ans:{qid}:0")
    kb.button(text="⛔ Стоп", callback_data="tf:stop")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def stop_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎮 Игры", callback_data="menu:games")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def pick_unseen_question(user_id: int):
    seen = get_seen_today(user_id, "tf")
    unseen = [q for q in TF_QUESTIONS if q["id"] not in seen]
    if not unseen:
        return None
    return random.choice(unseen)


@router.callback_query(F.data == "tf:stop")
async def tf_stop(cb: CallbackQuery):
    active_question.pop(cb.from_user.id, None)
    await cb.message.edit_text("Ок, остановил игру ✅\n\nКуда дальше?", reply_markup=stop_kb())
    await cb.answer()


@router.callback_query(F.data == "tf:start")
async def start_tf(cb: CallbackQuery):
    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)

    q = pick_unseen_question(cb.from_user.id)
    if not q:
        await cb.message.edit_text("Сегодня вопросы закончились 🎉\n\nВозвращайся завтра!", reply_markup=stop_kb())
        await cb.answer()
        return

    active_question[cb.from_user.id] = q
    pts = int(q.get("points", 5))
    badge = difficulty_badge(pts)
    await cb.message.edit_text(
    f"✅❌ Правда или ложь?\n\n{badge}\n\n{q['text']}",
    reply_markup=question_kb(q["id"])
)
    await cb.answer()


@router.callback_query(F.data.startswith("tf:ans:"))
async def answer_tf(cb: CallbackQuery):
    parts = cb.data.split(":")
    # tf:ans:<qid>:<user_answer>
    qid = int(parts[2])
    user_answer = int(parts[3])

    q = active_question.get(cb.from_user.id)
    if not q or q["id"] != qid:
        await cb.answer("Этот вопрос уже неактуален 🙂", show_alert=True)
        return

    correct = int(q["answer"])
    pts = int(q.get("points", 5))  # сложность вопроса (1–5)
    badge = difficulty_badge(pts)

    is_correct = (user_answer == correct)

    # 🔥 стрик + бонус (считаем всегда, чтобы при ошибке стрик сбрасывался)
    cur_streak, best_streak, bonus = update_streak(cb.from_user.id, "tf", is_correct)
    streak_text = streak_line(cur_streak)
    bonus_text = f"\n 🎁 Бонус: {points_text(bonus)}" if bonus > 0 else ""

    if is_correct:
        add_points(cb.from_user.id, pts)
        if bonus > 0:
            add_points(cb.from_user.id, bonus)

        verdict = f"{badge}\n✅ Верно! {points_text(pts)}{bonus_text}"
        if streak_text:
            verdict += f"\n{streak_text}"
    else:
        penalty = -ceil(pts / 2)
        add_points(cb.from_user.id, penalty)
        verdict = f"{badge}\n❌ Неверно! {points_text(penalty)}"

    explain = q.get("explain")
    if explain:
        verdict = f"{verdict}\n\n💡 {explain}"

    mark_seen_today(cb.from_user.id, "tf", qid)
    active_question.pop(cb.from_user.id, None)

    # следующий вопрос
    nxt = pick_unseen_question(cb.from_user.id)
    if not nxt:
        await cb.message.edit_text(f"{verdict}\n\nСегодня вопросы закончились 🎉", reply_markup=stop_kb())
        await cb.answer()
        return
    
    nxt_pts = int(nxt.get("points", 5))
    badge = difficulty_badge(nxt_pts)
                         
    active_question[cb.from_user.id] = nxt
    await cb.message.edit_text(
    f"{verdict}\n\nСледующий вопрос:\n\n{badge}\n\n{nxt['text']}",
    reply_markup=question_kb(nxt["id"])
)
    await cb.answer()
