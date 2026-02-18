import time
import uuid
import random
import asyncio
from math import ceil
from typing import Dict, Any, Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.quiz_questions import QUIZ_QUESTIONS
from services.scoring import add_points, upsert_user
from services.points_text_tfgame import points_text
from services.pvp_storage import get_match, upsert_match, delete_match, cleanup_expired
from services.pvp_stats import add_win, add_loss, add_draw, ensure_user

router = Router()

ROUNDS_PER_MATCH = 5
ROUND_TIMEOUT_SEC = 60  # можешь поменять
MATCH_TTL_SEC = 60 * 60  # авто-очистка старых матчей

DIFFICULTY_EMOJI = {1: "🟢", 2: "🔵", 3: "🟡", 4: "🟠", 5: "🔴"}
LETTER = {0: "A", 1: "B", 2: "C", 3: "D"}


def difficulty_badge(pts: int) -> str:
    pts = max(1, min(5, int(pts)))
    return f"{DIFFICULTY_EMOJI[pts]} Сложность: {pts}/5"


def invite_kb(match_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять дуэль", callback_data=f"pvp:accept:{match_id}")
    kb.button(text="❌ Отменить", callback_data=f"pvp:cancel:{match_id}")
    kb.button(text="🎮 Игры", callback_data="menu:games")
    kb.adjust(1)
    return kb.as_markup()


def answer_kb(match_id: str, qid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="A", callback_data=f"pvp:ans:{match_id}:{qid}:0")
    kb.button(text="B", callback_data=f"pvp:ans:{match_id}:{qid}:1")
    kb.button(text="C", callback_data=f"pvp:ans:{match_id}:{qid}:2")
    kb.button(text="D", callback_data=f"pvp:ans:{match_id}:{qid}:3")
    kb.button(text="⛔ Стоп", callback_data=f"pvp:stop:{match_id}")
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


def render_question(q: Dict[str, Any], round_no: int, total_rounds: int) -> str:
    pts = int(q.get("points", 3))
    badge = difficulty_badge(pts)

    opts = q.get("options", [])
    options_text = "\n".join(
        f"{LETTER[i]}. {opts[i]}" for i in range(min(4, len(opts)))
    )

    return (
        f"⚔️ PvP Викторина — раунд {round_no}/{total_rounds}\n\n"
        f"{badge}\n\n"
        f"⏳ Время на ответ: 1 минута\n\n"
        f"❓ {q['text']}\n\n"
        f"{options_text}\n\n"
        f"Выбери A/B/C/D кнопками ниже:"
    )


def _now() -> int:
    return int(time.time())


def _pick_questions(n: int) -> list[Dict[str, Any]]:
    # безопасно: если вопросов меньше, чем n — берём сколько есть
    n = min(n, len(QUIZ_QUESTIONS))
    return random.sample(QUIZ_QUESTIONS, k=n)


async def _send_round(cb: CallbackQuery, match: Dict[str, Any]) -> None:
    """
    Отправляет текущий раунд обоим игрокам (новым сообщением).
    """
    players = match["players"]
    round_index = int(match["round_index"])  # 0..ROUNDS-1
    q = match["questions"][round_index]
    qid = int(q["id"])

    match["current_qid"] = qid
    match["answers"] = {str(players[0]): None, str(players[1]): None}
    match["round_started_at"] = _now()
    match["updated_at"] = _now()

    # Отправляем каждому игроку в его чат
    for uid in players:
        chat_id = match["chats"].get(str(uid))
        if not chat_id:
            continue
        msg = await cb.bot.send_message(
            chat_id=chat_id,
            text=render_question(q, round_index + 1, ROUNDS_PER_MATCH),
            reply_markup=answer_kb(match["id"], qid),
        )
        match["round_messages"][str(uid)] = {"chat_id": chat_id, "message_id": msg.message_id}

    await upsert_match(match["id"], match)

    # Таймер раунда (не переживает перезапуск — это ок для простой версии)
    asyncio.create_task(_round_timeout_task(cb, match["id"], match["round_started_at"]))


async def _round_timeout_task(cb: CallbackQuery, match_id: str, started_at: int) -> None:
    await asyncio.sleep(ROUND_TIMEOUT_SEC)

    match = await get_match(match_id)
    if not match:
        return

    # если раунд уже другой или матч не активен — ничего
    if match.get("status") != "active":
        return
    if int(match.get("round_started_at", 0)) != int(started_at):
        return

    await _finalize_round(cb, match_id, reason="timeout")


def _calc_delta(is_correct: bool, pts: int) -> int:
    if is_correct:
        return int(pts)
    return -ceil(int(pts) / 2)


def _get_opponent(players: list[int], uid: int) -> int:
    return players[1] if players[0] == uid else players[0]


async def _finalize_round(cb: CallbackQuery, match_id: str, reason: str = "both_answered") -> None:
    match = await get_match(match_id)
    if not match or match.get("status") != "active":
        return

    players = match["players"]
    qid = int(match.get("current_qid", 0))
    round_index = int(match["round_index"])
    q = match["questions"][round_index]
    pts = int(q.get("points", 3))
    correct_opt = int(q["answer"])

    # ответы игроков
    a1 = match["answers"].get(str(players[0]))
    a2 = match["answers"].get(str(players[1]))

    # Если таймаут: кто не ответил — считается как неверно (или можно сделать 0)
    # Здесь: не ответил -> неверно (штраф по формуле)
    def verdict_for(uid: int, ans: Optional[int]) -> Dict[str, Any]:
        is_correct = (ans is not None) and (int(ans) == correct_opt)
        delta = _calc_delta(is_correct, pts) if ans is not None else _calc_delta(False, pts)
        # если хочешь “не ответил = 0”, замени на:
        # delta = 0 if ans is None else _calc_delta(is_correct, pts)
        return {"is_correct": is_correct, "delta": delta, "ans": ans}

    v1 = verdict_for(players[0], a1)
    v2 = verdict_for(players[1], a2)

    # начисляем в общий профиль + в матчевый счёт
    add_points(players[0], v1["delta"])
    add_points(players[1], v2["delta"])

    match["scores"][str(players[0])] += v1["delta"]
    match["scores"][str(players[1])] += v2["delta"]

    # текст “правильный ответ”
    correct_letter = LETTER.get(correct_opt, "?")
    correct_text = q["options"][correct_opt] if q.get("options") else ""
    explain = q.get("explain")

    badge = difficulty_badge(pts)

    # Пишем каждому персональный итог раунда
    for uid in players:
        me = v1 if uid == players[0] else v2
        opp_uid = _get_opponent(players, uid)
        opp = v2 if uid == players[0] else v1

        me_line = f"{'✅' if me['is_correct'] else '❌'} Ты: {points_text(me['delta'])}"
        if me["ans"] is None:
            me_line = f"⏱ Ты не ответил: {points_text(me['delta'])}"

        opp_line = f"{'✅' if opp['is_correct'] else '❌'} Соперник: {points_text(opp['delta'])}"
        if opp["ans"] is None:
            opp_line = f"⏱ Соперник не ответил: {points_text(opp['delta'])}"

        total_me = match["scores"][str(uid)]
        total_opp = match["scores"][str(opp_uid)]

        text = (
            f"{badge}\n"
            f"Раунд {round_index + 1}/{ROUNDS_PER_MATCH} завершён.\n\n"
            f"{me_line}\n"
            f"{opp_line}\n\n"
            f"✅ Правильный ответ: {correct_letter}. {correct_text}"
        )
        if explain:
            text += f"\n\n💡 {explain}"

        text += (
            f"\n\n📊 Счёт матча:\n"
            f"— Ты: {total_me}\n"
            f"— Соперник: {total_opp}"
        )

        # редактируем сообщение раунда, если можем
        msg_info = match["round_messages"].get(str(uid))
        if msg_info:
            try:
                await cb.bot.edit_message_text(
                    chat_id=msg_info["chat_id"],
                    message_id=msg_info["message_id"],
                    text=text,
                    reply_markup=None,
                )
            except Exception:
                # если не получилось отредактировать — отправим новым сообщением
                try:
                    await cb.bot.send_message(chat_id=msg_info["chat_id"], text=text)
                except Exception:
                    pass

    # следующий раунд или конец
    match["round_index"] = round_index + 1
    match["updated_at"] = _now()

    if match["round_index"] >= ROUNDS_PER_MATCH:
        # конец матча
        p1, p2 = players[0], players[1]
        s1 = match["scores"][str(p1)]
        s2 = match["scores"][str(p2)]

        # ✅ ЗАПИСЬ PvP-СТАТИСТИКИ (ОДИН РАЗ НА МАТЧ)
        ensure_user(p1)
        ensure_user(p2)

        if s1 > s2:
            add_win(p1)
            add_loss(p2)
        elif s2 > s1:
            add_win(p2)
            add_loss(p1)
        else:
            add_draw(p1)
            add_draw(p2)

        # отдельно каждому покажем итог
        for uid in players:
            opp_uid = _get_opponent(players, uid)
            my_score = match["scores"][str(uid)]
            opp_score = match["scores"][str(opp_uid)]

            if my_score > opp_score:
                res_line = "🏆 Ты победил!"
            elif my_score < opp_score:
                res_line = "😿 Ты проиграл."
            else:
                res_line = "🤝 Ничья."

            summary = (
                f"⚔️ PvP Викторина завершена!\n\n"
                f"{res_line}\n\n"
                f"📊 Итоговый счёт:\n"
                f"— Ты: {my_score}\n"
                f"— Соперник: {opp_score}\n\n"
                f"Куда дальше?"
            )

            chat_id = match["chats"].get(str(uid))
            if chat_id:
                try:
                    await cb.bot.send_message(chat_id=chat_id, text=summary, reply_markup=stop_kb())
                except Exception:
                    pass

        await delete_match(match_id)
        return

    # продолжаем матч: шлём следующий раунд
    await upsert_match(match_id, match)
    await _send_round(cb, match)


@router.callback_query(F.data == "pvp:invite")
async def pvp_invite(cb: CallbackQuery):
    await cleanup_expired(MATCH_TTL_SEC)

    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)

    match_id = uuid.uuid4().hex[:10]
    host_uid = cb.from_user.id

    match = {
        "id": match_id,
        "status": "waiting",
        "created_at": _now(),
        "updated_at": _now(),
        "host_uid": host_uid,
        "players": [host_uid],
        "chats": {str(host_uid): cb.message.chat.id if cb.message else host_uid},
        "questions": [],
        "round_index": 0,
        "current_qid": None,
        "answers": {},
        "scores": {str(host_uid): 0},
        "round_started_at": None,
        "round_messages": {},
    }

    await upsert_match(match_id, match)

    me = await cb.bot.get_me()
    payload = f"pvp_{match_id}"
    link = f"https://t.me/{me.username}?start={payload}"

    text = (
        "⚔️ PvP Викторина\n\n"
        "Отправь другу эту ссылку:\n"
        f"{link}\n\n"
        "Друг откроет бота по ссылке и нажмёт «Принять дуэль»."
    )

    # Можно оставить кнопки отмены здесь, чтобы создатель мог отменить
    await cb.message.edit_text(text, reply_markup=invite_kb(match_id))
    await cb.answer()


@router.callback_query(F.data.startswith("pvp:cancel:"))
async def pvp_cancel(cb: CallbackQuery):
    match_id = cb.data.split(":")[2]
    match = await get_match(match_id)
    if not match:
        await cb.answer("Этот вызов уже неактуален 🙂", show_alert=True)
        return

    if match.get("status") != "waiting":
        await cb.answer("Матч уже начался — отменить нельзя.", show_alert=True)
        return

    if int(match.get("host_uid")) != cb.from_user.id:
        await cb.answer("Отменить может только создатель дуэли.", show_alert=True)
        return

    await delete_match(match_id)
    await cb.message.edit_text("Ок, дуэль отменена ✅\n\nКуда дальше?", reply_markup=stop_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("pvp:accept:"))
async def pvp_accept(cb: CallbackQuery):
    await cleanup_expired(MATCH_TTL_SEC)

    match_id = cb.data.split(":")[2]
    match = await get_match(match_id)
    if not match:
        await cb.answer("Этот вызов уже неактуален 🙂", show_alert=True)
        return

    if match.get("status") != "waiting":
        await cb.answer("Этот матч уже начался 🙂", show_alert=True)
        return

    host_uid = int(match["host_uid"])
    guest_uid = cb.from_user.id

    if guest_uid == host_uid:
        await cb.answer("Нельзя принять дуэль самому себе 🙂", show_alert=True)
        return

    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)

    # регистрируем гостя
    match["players"] = [host_uid, guest_uid]
    match["chats"][str(guest_uid)] = cb.message.chat.id if cb.message else guest_uid
    match["status"] = "active"
    match["updated_at"] = _now()

    # вопросы на матч
    match["questions"] = _pick_questions(ROUNDS_PER_MATCH)
    match["round_index"] = 0

    # счёт
    match["scores"] = {str(host_uid): 0, str(guest_uid): 0}
    match["round_messages"] = {}

    await upsert_match(match_id, match)

    # обоим сообщаем, что матч начался
    for uid in match["players"]:
        chat_id = match["chats"].get(str(uid))
        if chat_id:
            try:
                await cb.bot.send_message(chat_id=chat_id, text="⚔️ Дуэль принята! Начинаем 🔥")
            except Exception:
                pass

    # стартуем 1 раунд
    await _send_round(cb, match)
    await cb.answer("Матч начался ✅", show_alert=True)


@router.callback_query(F.data.startswith("pvp:stop:"))
async def pvp_stop(cb: CallbackQuery):
    match_id = cb.data.split(":")[2]
    match = await get_match(match_id)
    if not match:
        await cb.answer("Матч уже неактуален 🙂", show_alert=True)
        return

    if cb.from_user.id not in match.get("players", []):
        await cb.answer("Ты не участник этого матча.", show_alert=True)
        return

    # Завершаем матч “по инициативе”
    players = match["players"]
    for uid in players:
        chat_id = match["chats"].get(str(uid))
        if chat_id:
            try:
                await cb.bot.send_message(
                    chat_id=chat_id,
                    text="⛔ Матч остановлен.\n\nКуда дальше?",
                    reply_markup=stop_kb(),
                )
            except Exception:
                pass

    await delete_match(match_id)
    await cb.answer()


@router.callback_query(F.data.startswith("pvp:ans:"))
async def pvp_answer(cb: CallbackQuery):
    await cleanup_expired(MATCH_TTL_SEC)

    parts = cb.data.split(":")
    # pvp:ans:<match_id>:<qid>:<opt>
    match_id = parts[2]
    qid = int(parts[3])
    opt = int(parts[4])

    match = await get_match(match_id)
    if not match or match.get("status") != "active":
        await cb.answer("Этот матч уже неактуален 🙂", show_alert=True)
        return

    uid = cb.from_user.id
    if uid not in match.get("players", []):
        await cb.answer("Ты не участник этого матча.", show_alert=True)
        return

    # проверка актуальности вопроса
    if int(match.get("current_qid", 0)) != qid:
        await cb.answer("Этот вопрос уже неактуален 🙂", show_alert=True)
        return

    # если уже ответил — не даём накликать
    if match["answers"].get(str(uid)) is not None:
        await cb.answer("Ты уже ответил 🙂", show_alert=True)
        return

    match["answers"][str(uid)] = opt
    match["updated_at"] = _now()
    await upsert_match(match_id, match)

    # если второй ещё не ответил — просто подтверждаем
    players = match["players"]
    other_uid = players[1] if players[0] == uid else players[0]
    other_ans = match["answers"].get(str(other_uid))

    if other_ans is None:
        await cb.answer("Ответ принят ✅")
        return

    # оба ответили -> завершаем раунд
    await cb.answer()
    await _finalize_round(cb, match_id, reason="both_answered")
