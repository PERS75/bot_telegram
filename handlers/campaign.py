from typing import Dict, Any
from typing import Union
from typing import Optional
from aiogram import Router, F
import aiogram
import os
import re
import asyncio
from aiogram.types import FSInputFile
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.campaign.ch1 import CH1_STEPS, CH1_CROSSWORD
from data.campaign.ch2 import CH2_STEPS, CH2_REBUS
from data.campaign.ch3 import CH3_STEPS, CH3_HANGMAN
from data.campaign.ch4 import CH4_STEPS, CH4_LIFTS
from data.campaign.ch5 import CH5_STEPS, CH5_KEYRATE
from data.campaign.ch5_quiz import CH5_QUIZ, CH5_QUIZ_PHOTOS, CH5_QUIZ_ACHIEVEMENTS

from keyboards.campaign import (
    keyrate_kb, keyrate_back_kb, keyrate_thanks_kb, keyrate_win_kb,
    ch5_quiz_kb, ch5_quiz_next_kb, ch5_quiz_menu_kb,
    story_kb, crossword_kb, ai_entry_kb, rebus_kb, ai_back_kb, ai_done_kb,
    ch3_story_choice_kb
)
from services.campaign_progress import get_current_chapter, set_current_chapter
from services.ai_client import ask_economist
from html import escape as html_escape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))  # если handlers/ -> проект на уровень выше

def resolve_path(p: str) -> str:
    if os.path.isabs(p):
        return p
    return os.path.join(PROJECT_DIR, p)

router = Router()

# Состояние только в памяти (как ты хотела: вышла -> можно начать заново)
state: Dict[int, Dict[str, Any]] = {}

CHAPTERS = {
    1: {"steps": CH1_STEPS},
    2: {"steps": CH2_STEPS},
    3: {"steps": CH3_STEPS},
    4: {"steps": CH4_STEPS},
    5: {"steps": CH5_STEPS},
}

async def disable_prev_kb(user_id: int, bot, chat_id: int):
    prev_id = state.get(user_id, {}).get("last_story_msg_id")
    if not prev_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=prev_id, reply_markup=None)
    except Exception:
        pass

async def disable_kb_by_id(bot, chat_id: int, msg_id: int):
    if not msg_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
    except Exception:
        pass

async def disable_last_crossword_kb(bot, chat_id: int, user_id: int):
    msg_id = state.get(user_id, {}).get("last_crossword_msg_id")
    if not msg_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
    except Exception:
        pass

def max_chapter() -> int:
    return max(CHAPTERS.keys())

def get_chapter(user_id: int) -> int:
    # берём из памяти, если есть, иначе из файла (с диска)
    return int(state.get(user_id, {}).get("chapter") or get_current_chapter(user_id, 1))

def set_chapter(user_id: int, chapter: int) -> None:
    state.setdefault(user_id, {})
    state[user_id]["chapter"] = int(chapter)
    set_current_chapter(user_id, int(chapter))

def get_steps_for(user_id: int):
    ch = get_chapter(user_id)
    if ch not in CHAPTERS:
        ch = 1
        set_chapter(user_id, 1)
    return CHAPTERS[ch]["steps"]

def norm(s: str) -> str:
    return (s or "").strip().lower().replace("ё", "е")

def ch5_quiz_review_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Разбор ответов", callback_data="camp:ch5:quiz:review")
    return kb.as_markup()

def get_step(user_id: int) -> int:
    return int(state.get(user_id, {}).get("step", 0))

async def _safe_edit(cb: CallbackQuery, text: str, reply_markup):
    """
    Редактирует ТЕКУЩЕЕ сообщение:
    - если это фото-сообщение -> edit_caption
    - если текстовое -> edit_text
    """
    try:
        if cb.message.photo:
            await cb.message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await cb.message.edit_text(text=text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        # Частый кейс: "message is not modified"
        if "message is not modified" in str(e):
            pass
        else:
            raise

async def show_story(event: Union[CallbackQuery, Message], step_idx: int):
    user_id = event.from_user.id
    cur_ch = get_chapter(user_id)
    steps = get_steps_for(user_id)

    if step_idx < 0:
        step_idx = 0

    # конец главы -> переход на следующую
    if step_idx >= len(steps):
        if cur_ch < max_chapter():
            set_chapter(user_id, cur_ch + 1)
            cur_ch += 1
            steps = get_steps_for(user_id)
            step_idx = 0
        else:
            step_idx = 0

    step = steps[step_idx]

    # служебные шаги — пропускаем
    if step.get("type") in {"hangman", "lift_quiz", "keyrate_choice", "ch5_bonus", "ch5_survey_ok", "ch5_role_yes", "ch5_quiz_start"}:
        await show_story(event, step_idx + 1)
        return

    state.setdefault(user_id, {})
    state[user_id].update({"mode": step["type"], "step": step_idx})

    # переходы на миниигры
    if step["type"] == "crossword":
        await start_crossword(event if isinstance(event, CallbackQuery) else None,
                              message=event if isinstance(event, Message) else None)
        return

    if step["type"] == "rebus":
        await start_rebus(event if isinstance(event, CallbackQuery) else None,
                          message=event if isinstance(event, Message) else None)
        return

    if step["type"] == "ai_qna":
        text_ai = (
            "🤖 Ты можешь задать мне любой вопрос, а я постараюсь на него ответить.\n\n"
            "Нажми «Спросить у робота» или продолжай сюжет."
        )
        if isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id
            await disable_prev_kb(user_id, event.bot, chat_id)

            sent = await event.message.answer(text_ai, reply_markup=ai_entry_kb())
            state[user_id]["last_story_msg_id"] = sent.message_id
            await event.answer()
        else:
            chat_id = event.chat.id
            await disable_prev_kb(user_id, event.bot, chat_id)

            sent = await event.answer(text_ai, reply_markup=ai_entry_kb())
            state[user_id]["last_story_msg_id"] = sent.message_id
        return

    # ===== обычный story шаг =====
    text = step.get("text")
    if not text:
        await show_story(event, step_idx + 1)
        return

    photo = step.get("photo")

    # клавиатура: keyrate_immediate -> варианты, иначе -> story_kb
    if step.get("keyrate_immediate"):
        markup = keyrate_kb()
    elif step.get("next_action") == "ai_qna":
        markup = ch3_story_choice_kb()
    else:
        next_text = step.get("next_text", "Далее")
        markup = story_kb(next_text, show_menu=False)

    # 🚫 ВАЖНО: если шаг с автопереходом — кнопок быть не должно (иначе мигание)
    if step.get("autonext"):
        markup = None

    # 🚫 ВАЖНО: первое сообщение 1 главы — без кнопок (если оно автопереходное или нет)
    if cur_ch == 1 and step_idx == 0:
        markup = None

    chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id
    await disable_prev_kb(user_id, event.bot, chat_id)

    sent = await send_step(event, text=text, markup=markup, photo=photo)
    state[user_id]["last_story_msg_id"] = sent.message_id

    if step.get("autonext"):
        delay = float(step.get("delay", 1.2))
        await asyncio.sleep(delay)
        await show_story(event, step_idx + 1)
        return

    if isinstance(event, CallbackQuery):
        await event.answer()

async def send_step(event: Union[CallbackQuery, Message], text: str, markup=None, photo: Optional[str] = None):
    """
    Унифицированная отправка: если есть photo -> отправляем фото, иначе текст.
    Поддерживает: http(s) URL, относительные пути, абсолютные пути.
    """
    if isinstance(event, CallbackQuery):
        sender = event.message
    else:
        sender = event

    if photo and isinstance(photo, str) and photo.startswith("http"):
        return await sender.answer_photo(photo, caption=text, reply_markup=markup)

    if photo and isinstance(photo, str):
        path = resolve_path(photo)
        if os.path.exists(path):
            return await sender.answer_photo(FSInputFile(path), caption=text, reply_markup=markup)

    return await sender.answer(text, reply_markup=markup)

async def start_crossword(cb: CallbackQuery | None = None, message: Message | None = None):
    user_id = (cb.from_user.id if cb else message.from_user.id)

    state[user_id] = {
        "mode": "crossword",
        "step": get_step(user_id),
        "word_idx": 0,
        "wrong_tries": 0,
        "hint_used": False,
    }

    w0 = CH1_CROSSWORD[0]

    if cb:
        sent = await send_step(cb, text=w0["prompt"], photo=w0.get("photo"), markup=crossword_kb(0, False))
        state[user_id]["last_crossword_msg_id"] = sent.message_id
        await cb.answer()
    else:
        sent = await send_step(message, text=w0["prompt"], photo=w0.get("photo"), markup=crossword_kb(0, False))
        state[user_id]["last_crossword_msg_id"] = sent.message_id

async def start_rebus(cb: CallbackQuery | None = None, message: Message | None = None):
    user_id = (cb.from_user.id if cb else message.from_user.id)

    state.setdefault(user_id, {})
    state[user_id].update({
        "mode": "rebus",
        "step": get_step(user_id),
        "rebus_idx": 0,
        "rebus_wrong": 0,
    })

    r0 = CH2_REBUS[0]
    if cb:
        await send_step(
            cb,
            text=r0["prompt"],
            photo=r0.get("photo"),
            markup=rebus_kb(0),
        )
        await cb.answer()
    else:
        await send_step(
            message,
            text=r0["prompt"],
            photo=r0.get("photo"),
            markup=rebus_kb(0),
        )

async def start_lift_quiz(cb: Optional[CallbackQuery] = None, message: Optional[Message] = None):
    user_id = (cb.from_user.id if cb else message.from_user.id)

    state.setdefault(user_id, {})
    state[user_id].update({
        "mode": "lift_quiz",
        "step": get_step(user_id),            # <-- важно
        "lift_answer": CH4_LIFTS["answer"],
    })

    if cb:
        await send_step(cb, text=CH4_LIFTS["prompt"], photo=CH4_LIFTS.get("prompt_photo"))
        await cb.answer()
    else:
        await send_step(message, text=CH4_LIFTS["prompt"], photo=CH4_LIFTS.get("prompt_photo"))

def _mask_word(word: str, guessed: set[str]) -> str:
    return " ".join([ch if ch in guessed else "_" for ch in word])

async def start_hangman(hm_index: int, cb: Optional[CallbackQuery] = None, message: Optional[Message] = None):
    user_id = (cb.from_user.id if cb else message.from_user.id)
    data = CH3_HANGMAN[hm_index]
    word = norm(data["word"])

    state.setdefault(user_id, {})
    state[user_id].update({
        "mode": "hangman",
        "hm_index": hm_index,
        "hm_word": word,
        "hm_guessed": set(),
        "hm_wrong": 0,
        "hm_max_wrong": 10,
        "step": get_step(user_id),
    })

    if cb:
        await cb.message.answer(data["intro"])
        await cb.answer()
    else:
        await message.answer(data["intro"])

async def start_ch5_quiz(cb: CallbackQuery):
    user_id = cb.from_user.id

    # выключаем кнопки у сообщения, где нажали
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    state.setdefault(user_id, {})
    state[user_id].update({
        "mode": "ch5_quiz",
        "quiz_idx": 0,
        "quiz_correct": 0,
        "last_quiz_msg_id": None,
        "quiz_wait_next": False,  # чтобы нельзя было отвечать несколько раз на один вопрос
        "quiz_answers": {},
    })

    await send_ch5_quiz_question(cb)

async def send_ch5_quiz_question(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id, {})

    q_idx = int(st.get("quiz_idx", 0))
    q = CH5_QUIZ[q_idx]

    # отправляем вопрос
    sent = await cb.message.answer(
        q["q"],
        reply_markup=ch5_quiz_kb(q_idx, q["options"])
    )
    st["last_quiz_msg_id"] = sent.message_id
    st["quiz_wait_next"] = False
    state[user_id] = st

async def finish_hangman_word(event: Union[CallbackQuery, Message], solved_by: str = "letters"):
    user_id = event.from_user.id

    # выходим из hangman
    st = state.get(user_id, {})
    st["mode"] = "story"
    st["hm_wrong"] = 0
    st["hm_guessed"] = set()
    state[user_id] = st

    step_idx = get_step(user_id)
    await show_story(event, step_idx + 1)

@router.message(F.text.in_({"/story", "/story@hse_econ_bot"}))
async def story_command(message: Message):
    # сброс состояния + начинаем с 0 шага через show_story (там уже умеет photo)
    state[message.from_user.id] = {"mode": "story", "step": 0}
    set_chapter(message.from_user.id, 1)
    await show_story(message, 0)


@router.callback_query(F.data == "camp:next")
async def camp_next(cb: CallbackQuery):
    user_id = cb.from_user.id

    step_idx = get_step(user_id)
    steps = get_steps_for(user_id)

    cur = steps[step_idx]
    action = cur.get("next_action")

    # 1) проверяем "устаревшее" ДО того как убирать кнопки
    last_id = state.get(user_id, {}).get("last_story_msg_id")
    if last_id and cb.message.message_id != last_id:
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    # 2) теперь можно убирать кнопки у текущего сообщения
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


    if action == "start_crossword":
        await start_crossword(cb)
        return

    if action == "start_rebus":
        await start_rebus(cb)
        return

    if action == "ai_qna":
        await show_story(cb, step_idx + 1)
        return

    if action == "start_hangman_1":
        await start_hangman(0, cb=cb)
        return

    if action == "start_hangman_2":
        await start_hangman(1, cb=cb)
        return
    
    if action == "start_lift_quiz":
        await start_lift_quiz(cb=cb)
        return
    

    if action == "ch5_bonus":
        # показать сертификат (картинка + кнопка Продолжить)
        # тут мы пока просто делаем следующий шаг сюжета через show_story
        await show_story(cb, step_idx + 1)
        return

    if action == "ch5_survey_ok":
        await show_story(cb, step_idx + 1)
        return

    if action == "ch5_role_yes":
        await show_story(cb, step_idx + 1)
        return

    if action == "ch5_quiz_start":
        await start_ch5_quiz(cb)
        return

    await show_story(cb, step_idx + 1)

@router.callback_query(F.data == "camp:skip_ai")
async def camp_skip_ai(cb: CallbackQuery):
    user_id = cb.from_user.id

    step_idx = get_step(user_id)
    steps = get_steps_for(user_id)

    # защита от устаревшей кнопки
    last_id = state.get(user_id, {}).get("last_story_msg_id")
    if last_id and cb.message.message_id != last_id:
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    # выключаем кнопки у текущего сообщения
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # перескакиваем через ai_qna и choice
    next_step = step_idx + 1
    while next_step < len(steps) and steps[next_step].get("type") in {"ai_qna", "choice"}:
        next_step += 1

    await cb.answer()
    await show_story(cb, next_step) 

@router.callback_query(F.data == "camp:hint")
async def camp_hint(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id)
    if not st or st.get("mode") != "crossword":
        await cb.answer()
        return

    # ✅ защита: подсказка только на последнем "кроссвордном" сообщении
    last_id = st.get("last_crossword_msg_id")
    if last_id and cb.message.message_id != last_id:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    # ✅ одноразовая подсказка на слово
    if st.get("hint_used"):
        await cb.answer("Подсказка уже была 🙂", show_alert=False)
        return

    idx = int(st.get("word_idx", 0))
    hint_text = CH1_CROSSWORD[idx]["hint"]

    # 1) отмечаем подсказку использованной
    st["hint_used"] = True
    state[user_id] = st

    # 2) отправляем подсказку ОДИН раз
    await cb.message.answer(hint_text)

    # 3) убираем кнопку "Подсказка" с этого сообщения
    #    оставляем, например, только кнопку "Турбо" (или вообще ничего — как тебе надо)
    try:
        await cb.message.edit_reply_markup(reply_markup=crossword_kb(0, True))
        # если хочешь вообще без кнопок после подсказки: reply_markup=None
    except Exception:
        pass

    await cb.answer()


@router.callback_query(F.data == "camp:turbo")
async def camp_turbo(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id)

    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if not st or st.get("mode") != "crossword":
        await cb.answer()
        return

    idx = int(st.get("word_idx", 0))
    if idx >= len(CH1_CROSSWORD):
        await cb.answer()
        return

    # 1) Пишем пользователю правильный ответ (как в turbo поле)
    await cb.message.answer(CH1_CROSSWORD[idx]["turbo"])

    # 2) Считаем слово решённым и идём дальше автоматически
    idx += 1
    st["word_idx"] = idx
    st["wrong_tries"] = 0
    st["hint_used"] = False
    state[user_id] = st

    # 3) Если кроссворд закончился — показываем следующий шаг сюжета
    if idx >= len(CH1_CROSSWORD):
        step_idx = get_step(user_id)
        next_step = step_idx + 1
        while next_step < len(CH1_STEPS) and CH1_STEPS[next_step]["type"] == "crossword":
            next_step += 1
        if next_step >= len(CH1_STEPS):
            next_step = 0

        state[user_id] = {"mode": "story", "step": next_step}
        await show_story(cb, next_step)
        await cb.answer()
        return

    # 4) Иначе — следующий вопрос кроссворда
    nxt = CH1_CROSSWORD[idx]
    await cb.message.answer(
        nxt["prompt"],
        reply_markup=crossword_kb(0, False),
    )
    await cb.answer()

@router.callback_query(F.data == "camp:rebus:turbo")
async def camp_rebus_turbo(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id)

    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if not st or st.get("mode") != "rebus":
        await cb.answer()
        return

    rebus_idx = int(st.get("rebus_idx", 0))
    if rebus_idx >= len(CH2_REBUS):
        await cb.answer()
        return

    # показываем решение
    await cb.message.answer(CH2_REBUS[rebus_idx]["turbo"])

    # считаем ребус решенным и идем дальше автоматически
    rebus_idx += 1
    st["rebus_idx"] = rebus_idx
    st["rebus_wrong"] = 0
    state[user_id] = st

    if rebus_idx >= len(CH2_REBUS):
        step_idx = get_step(user_id)
        steps = get_steps_for(user_id)

        next_step = step_idx + 1
        while next_step < len(steps) and steps[next_step]["type"] == "rebus":
            next_step += 1
        if next_step >= len(steps):
            next_step = 0

        state[user_id].update({"mode": "story", "step": next_step})
        await cb.answer()
        await show_story(cb, next_step)
        return

    nxt = CH2_REBUS[rebus_idx]

    await send_step(
        cb,
        text=nxt["prompt"],
        photo=nxt.get("photo"),
        markup=rebus_kb(0),
    )

    await cb.answer()

@router.callback_query(F.data == "menu:campaign")
async def menu_campaign(cb: CallbackQuery):
    user_id = cb.from_user.id
    
    cur = get_current_chapter(user_id, 1)
    if cur >= 6:
    # можно удалить меню-сообщение, как у тебя сделано
        try:
            await cb.message.delete()
        except Exception:
            pass

        await cb.answer()
        await cb.message.answer(
            "🎉 Ты уже прошёл сюжетную линию!\n\n",
            reply_markup=ch5_quiz_menu_kb()
        )
        return

    try:
        await cb.message.delete()
    except Exception:
        pass

    set_chapter(user_id, get_current_chapter(user_id, 1))
    state[user_id] = {"mode": "story", "step": 0}

    await cb.answer()
    await show_story(cb, 0)


@router.callback_query(F.data == "camp:ai:start")
async def camp_ai_start(cb: CallbackQuery):
    user_id = cb.from_user.id

    # защита от абуза: кнопка должна нажиматься только на актуальном story-сообщении
    last_story_id = state.get(user_id, {}).get("last_story_msg_id")
    if last_story_id and cb.message.message_id != last_story_id:
        # старое сообщение -> уберём кнопки и скажем что устарело
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    # гасим кнопки на сообщении, где нажали
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # режим AI
    st = state.get(user_id, {})
    st["mode"] = "camp_ai"
    state[user_id] = st

    sent = await cb.message.answer(
        "🧠 Вопрос экономисту\n\nНапиши вопрос текстом (например: «Почему растут цены?»).",
        reply_markup=ai_back_kb(),
    )

    # запоминаем, где сейчас актуальные AI-кнопки
    state.setdefault(user_id, {})
    state[user_id]["last_ai_msg_id"] = sent.message_id

    await cb.answer()


@router.callback_query(F.data == "camp:ai:done")
async def camp_ai_done(cb: CallbackQuery):
    user_id = cb.from_user.id

    # защита: "Продолжить" только с последнего AI-сообщения
    last_ai_id = state.get(user_id, {}).get("last_ai_msg_id")
    if last_ai_id and cb.message.message_id != last_ai_id:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    # гасим кнопки на текущем AI-сообщении
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    step_idx = get_step(user_id)

    st = state.get(user_id, {})
    st["mode"] = "story"
    state[user_id] = st

    # чтобы дальше "устаревшая кнопка" не мешала
    state[user_id]["last_ai_msg_id"] = None

    await cb.answer()
    await show_story(cb, step_idx + 1)

@router.message(F.text & ~F.text.startswith("/"))
async def campaign_text_router(message: Message):
    user_id = message.from_user.id
    st = state.get(user_id)


    # если пользователь не в сюжетных режимах — не трогаем
    if not st:
        return

    mode = st.get("mode")

    # =========================
    # 1) КРОССВОРД
    # =========================
    if mode == "crossword":
        idx = int(st.get("word_idx", 0))
        wrong = int(st.get("wrong_tries", 0))
        hint_used = bool(st.get("hint_used", False))

        if idx >= len(CH1_CROSSWORD):
            return

        user_answer = norm(message.text)
        correct = norm(CH1_CROSSWORD[idx]["answer"])

        if user_answer == correct:
            await message.answer(CH1_CROSSWORD[idx]["ok"])

            idx += 1
            st["word_idx"] = idx
            st["wrong_tries"] = 0
            st["hint_used"] = False
            state[user_id] = st

            if idx >= len(CH1_CROSSWORD):
                step_idx = get_step(user_id)
                next_step = step_idx + 1
                while next_step < len(CH1_STEPS) and CH1_STEPS[next_step]["type"] == "crossword":
                    next_step += 1
                if next_step >= len(CH1_STEPS):
                    next_step = 0

                state[user_id] = {"mode": "story", "step": next_step}
                await show_story(message, next_step)  # <-- ВАЖНО: теперь покажет фото
                return

            # следующий вопрос
            nxt = CH1_CROSSWORD[idx]
            await disable_last_crossword_kb(message.bot, message.chat.id, user_id)

            sent = await send_step(
                message,
                text=nxt["prompt"],
                photo=nxt.get("photo"),
                markup=crossword_kb(0, False),
            )
            state[user_id]["last_crossword_msg_id"] = sent.message_id
            return

        # неправильный ответ
        wrong += 1
        st["wrong_tries"] = wrong
        state[user_id] = st

        show_turbo = hint_used and wrong >= 1  # турбо появится только после 1-й ошибки ПОСЛЕ подсказки
        await disable_last_crossword_kb(message.bot, message.chat.id, user_id)

        sent = await message.answer(
            CH1_CROSSWORD[idx]["no"],
            reply_markup=crossword_kb(wrong, show_turbo),
        )
        state[user_id]["last_crossword_msg_id"] = sent.message_id
        return


    # =========================
    # REBUS (глава 2)
    # =========================
    if mode == "rebus":
        rebus_idx = int(st.get("rebus_idx", 0))
        wrong = int(st.get("rebus_wrong", 0))

        if rebus_idx >= len(CH2_REBUS):
            return

        user_answer = norm(message.text)
        correct = norm(CH2_REBUS[rebus_idx]["answer"])

        if user_answer == correct:
            await message.answer(CH2_REBUS[rebus_idx]["ok"])

            rebus_idx += 1
            st["rebus_idx"] = rebus_idx
            st["rebus_wrong"] = 0
            state[user_id] = st

            if rebus_idx >= len(CH2_REBUS):
                step_idx = get_step(user_id)
                steps = get_steps_for(user_id)

                next_step = step_idx + 1
                while next_step < len(steps) and steps[next_step]["type"] == "rebus":
                    next_step += 1
                if next_step >= len(steps):
                    next_step = 0

                state[user_id].update({"mode": "story", "step": next_step})
                await show_story(message, next_step)
                return


            # следующий ребус
            nxt = CH2_REBUS[rebus_idx]
            await send_step(
                message,
                text=nxt["prompt"],
                photo=nxt.get("photo"),
                markup=rebus_kb(0),
            )
            return


        # неправильный ответ -> появляется Турбо
        wrong += 1
        st["rebus_wrong"] = wrong
        state[user_id] = st

        await message.answer(CH2_REBUS[rebus_idx]["no"], reply_markup=rebus_kb(wrong))
        return
    

    # =========================
    # 2) ИИ ВНУТРИ СЮЖЕТА
    # =========================
    if mode == "camp_ai":
        q = message.text.strip()

        if st.get("ai_busy"):
            await message.answer(
                "🤖 Я ещё думаю над прошлым вопросом 🙂 Подожди ответ и напиши следующий."
            )
            return

        if len(q) < 3:
            await message.answer(
                "Слишком коротко 🙂 Напиши вопрос чуть подробнее."
            )
            return

        # гасим кнопки на прошлом AI сообщении (где были кнопки)
        prev_ai = state.get(user_id, {}).get("last_ai_msg_id")
        if prev_ai:
            await disable_kb_by_id(message.bot, message.chat.id, prev_ai)

        st["ai_busy"] = True
        state[user_id] = st

        # "думаю" — только вернуться
        await message.answer("🤖 Думаю…", reply_markup=ai_back_kb())

        try:
            answer = await ask_economist(q)
        except Exception:
            st = state.get(user_id, {})
            st["ai_busy"] = False
            state[user_id] = st
            await message.answer(
                "Сейчас не получилось получить ответ. Попробуй позже.",
                reply_markup=ai_back_kb()
            )
            return

        st = state.get(user_id, {})
        st["ai_busy"] = False
        state[user_id] = st

        if not answer:
            answer = "Не получилось сформировать ответ. Попробуй переформулировать вопрос."

        # ✅ ответ — только "Теперь понятно"
        sent = await message.answer(
            answer + "\n\n(Можешь задать ещё вопрос)",
            reply_markup=ai_done_kb()
        )
        state.setdefault(user_id, {})
        state[user_id]["last_ai_msg_id"] = sent.message_id
        return

    # =========================
    # HANGMAN (глава 3)
    # =========================
    if mode == "hangman":
        hm_index = int(st.get("hm_index", 0))
        data = CH3_HANGMAN[hm_index]

        word = st.get("hm_word", "")
        guessed = st.get("hm_guessed", set())
        if not isinstance(guessed, set):
            guessed = set(guessed)

        wrong = int(st.get("hm_wrong", 0))
        max_wrong = int(st.get("hm_max_wrong", 10))

        guess = norm(message.text)

        # 1) одна буква
        if len(guess) == 1:
            letter = guess

            if letter in guessed:
                await message.answer(
                    f"ℹ️ Буква «{letter}» уже открыта.\n"
                    f"Ошибки: {wrong}/{max_wrong}\n"
                    + _mask_word(word, guessed)
                )
                return
            
            if letter in word:
                guessed.add(letter)
                st["hm_guessed"] = guessed
                state[user_id] = st

                masked = _mask_word(word, guessed)
                await message.answer(f"✅ Верно. Ты почти у цели!\n{masked}")

                if "_" not in masked:
                    await finish_hangman_word(message, solved_by="letters")
                return

            # неправильная буква
            wrong += 1
            st["hm_wrong"] = wrong
            st["hm_guessed"] = guessed
            state[user_id] = st

            # лимит ошибок -> сразу провал (без открытия букв)
            if wrong >= max_wrong:
                await message.answer(data["second_fail"])
                await finish_hangman_word(message, solved_by="fail")
                return

            # просто ошибка
            await message.answer(
                f"❌ Не та буква.\n"
                f"Ошибки: {wrong}/{max_wrong}\n"
                + _mask_word(word, guessed)
            )
            return

        # слово целиком — неверно
        if guess == word:
            await message.answer("✅ Верно! Отлично!")
            await finish_hangman_word(message, solved_by="word")
            return
        else:
            wrong += 1
            st["hm_wrong"] = wrong
            st["hm_guessed"] = guessed
            state[user_id] = st

            if wrong >= max_wrong:
                await message.answer(data.get("second_fail", "❌ Попытки закончились."))
                await finish_hangman_word(message, solved_by="fail")
                return

            await message.answer(
                f"❌ Не похоже на правильное слово.\n"
                f"Ошибки: {wrong}/{max_wrong}\n"
                + _mask_word(word, guessed)
            )
            return
        
        
    # =========================
    # LIFT QUIZ (глава 4)
    # =========================
    if mode == "lift_quiz":
        # правильный ответ всегда берём из состояния, а если его нет — из CH4_LIFTS
        answer = str(st.get("lift_answer") or CH4_LIFTS.get("answer") or "").strip()

        # берём из сообщения ТОЛЬКО цифры (чтобы "1 3 2", "132.", "132\n" тоже работали)
        user_answer = "".join(ch for ch in (message.text or "") if ch.isdigit())

        # если ввели не 3 цифры — это точно неправильный ответ
        if len(user_answer) != 3:
            await message.answer(CH4_LIFTS["wrong"])
            return

        if user_answer == answer:
            # ВАЖНО: сначала переключаем режим, потом двигаем сюжет
            st["mode"] = "story"
            state[user_id] = st

            # двигаемся дальше по шагам (show_story пропустит служебный lift_quiz и покажет следующий story)
            step_idx = get_step(user_id)
            await show_story(message, step_idx + 1)
            return

        await message.answer(CH4_LIFTS["wrong"])
        return


@router.callback_query(F.data.in_({
    "camp:ch5:keyrate:A",
    "camp:ch5:keyrate:B",
    "camp:ch5:keyrate:V",
}))
async def ch5_keyrate_answer(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id, {})
    choice = cb.data.split(":")[-1]

    # Убираем кнопки выбора
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    last_msg = None

    if choice == "A":
        await send_step(cb, text=CH5_KEYRATE["A_text"], photo=CH5_KEYRATE["A_photo"])
        last_msg = await send_step(
            cb,
            text=CH5_KEYRATE["keeper_fix_text"],
            photo=CH5_KEYRATE.get("keeper_fix_photo_A", CH5_KEYRATE["keeper_fix_photo"]),
        )

        # Добавляем кнопку к последнему сообщению
        await last_msg.edit_reply_markup(reply_markup=keyrate_thanks_kb())

    elif choice == "V":
        await send_step(cb, text=CH5_KEYRATE["V_text"], photo=CH5_KEYRATE["V_photo"])
        last_msg = await send_step(
            cb,
            text=CH5_KEYRATE["keeper_fix_text"],
            photo=CH5_KEYRATE.get("keeper_fix_photo_V", CH5_KEYRATE["keeper_fix_photo"]),
        )

        await last_msg.edit_reply_markup(reply_markup=keyrate_thanks_kb())

    else:  # B
        last_msg = await send_step(
            cb,
            text=CH5_KEYRATE["B_text"],
            photo=CH5_KEYRATE["B_photo"],
        )

        await last_msg.edit_reply_markup(reply_markup=keyrate_win_kb())

    # сохраняем id сообщения с кнопкой
    st["last_keyrate_continue_msg_id"] = last_msg.message_id
    state[user_id] = st

    await cb.answer()

@router.callback_query(F.data.startswith("camp:ch5:quiz:ans:"))
async def ch5_quiz_answer(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id, {})

    if not st or st.get("mode") != "ch5_quiz":
        await cb.answer()
        return

    # анти-абуз: клик только на последнем quiz-сообщении
    last_id = st.get("last_quiz_msg_id")
    if last_id and cb.message.message_id != last_id:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    # анти-абуз: если уже отвечали, ждём "Дальше"
    if st.get("quiz_wait_next"):
        await cb.answer("Нажми «Дальше» 🙂", show_alert=False)
        return

    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    parts = cb.data.split(":")
    q_idx = int(parts[-2])
    ans_idx = int(parts[-1])

    q = CH5_QUIZ[q_idx]
    is_correct = (ans_idx == int(q["correct"]))
    if is_correct:
        st["quiz_correct"] = int(st.get("quiz_correct", 0)) + 1

    answers = st.get("quiz_answers") or {}
    answers[q_idx] = {"ans_idx": ans_idx, "is_correct": is_correct}
    st["quiz_answers"] = answers

    st["quiz_wait_next"] = True
    state[user_id] = st

    is_last = (q_idx == len(CH5_QUIZ) - 1)
    await cb.message.answer(
        q["explain"],
        reply_markup=ch5_quiz_next_kb(is_last=is_last)
    )
    await cb.answer()


@router.callback_query(F.data == "camp:ch5:quiz:next")
async def ch5_quiz_next(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id, {})

    if not st or st.get("mode") != "ch5_quiz":
        await cb.answer()
        return

    # одноразовость кнопки "Дальше"
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    st["quiz_idx"] = int(st.get("quiz_idx", 0)) + 1
    st["quiz_wait_next"] = False
    state[user_id] = st

    await cb.answer()
    await send_ch5_quiz_question(cb)

@router.callback_query(F.data == "camp:ch5:quiz:review")
async def ch5_quiz_review(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id, {})

    # можно разрешить и в story, потому что finish уже переключает mode в story
    # главное — чтобы ответы сохранились в st
    if not st or "quiz_answers" not in st:
        await cb.answer("Разбор недоступен 🙂", show_alert=False)
        return

    # одноразовость кнопки "Разбор"
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    def _strip_bot_prefix(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"^[^\wА-Яа-я]+", "", s).strip()
        return s

    def _short(s: str, limit: int = 220) -> str:
        s = (s or "").strip()
        return (s[:limit].rstrip() + "…") if len(s) > limit else s

    answers = st.get("quiz_answers") or {}

    parts = ["<b>📋 Разбор ответов</b>"]
    for i, q in enumerate(CH5_QUIZ):
        q_text = html_escape(q.get("q", ""))
        opts = q.get("options", [])
        correct_idx = int(q.get("correct", 0))
        correct_text = html_escape(opts[correct_idx]) if 0 <= correct_idx < len(opts) else "—"

        rec = answers.get(i)
        expl = html_escape(_short(_strip_bot_prefix(q.get("explain", ""))))

        if not rec:
            parts.append(
                f"<b>Вопрос {i+1}:</b> {q_text}\n"
                f"⚪️ <b>Ты не ответил</b>\n"
                f"<b>Правильный был:</b> {correct_text}\n"
                f"<b>Потому что:</b> {expl}"
            )
            continue

        ans_idx = int(rec.get("ans_idx", -1))
        your_text = html_escape(opts[ans_idx]) if 0 <= ans_idx < len(opts) else "—"
        verdict = "✅ <b>Правильно</b>" if rec.get("is_correct") else "❌ <b>Неправильно</b>"

        parts.append(
            f"<b>Вопрос {i+1}:</b> {q_text}\n\n"
            f"<b>Ты ответил:</b> {your_text}\n\n"
            f"{verdict}\n\n"
            f"<b>Правильный был:</b> {correct_text}\n\n"
            f"<b>Потому что:</b> {expl}"
        )

    await cb.message.answer("\n\n".join(parts), parse_mode="HTML", reply_markup=ch5_quiz_menu_kb())
    await cb.answer()

@router.callback_query(F.data == "camp:ch5:quiz:finish")
async def ch5_quiz_finish(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id, {})

    if not st or st.get("mode") != "ch5_quiz":
        await cb.answer()
        return

    # одноразовость
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    score = int(st.get("quiz_correct", 0))
    score = max(0, min(score, 5))

    photo = CH5_QUIZ_PHOTOS.get(score)
    ach = CH5_QUIZ_ACHIEVEMENTS.get(score, "Экономист")

    text = f"🤖 Тест пройден! Вы получили достижение «{ach}». Теперь вы точно знаете, как защитить свои деньги!"

    # выходим из режима теста
    st["mode"] = "story"
    state[user_id] = st
    set_chapter(user_id, 6)
    state[user_id]["chapter"] = 6

    # ✅ итог + кнопка "Разбор ответов"
    if photo:
        path = resolve_path(photo)
        if os.path.exists(path):
            await cb.message.answer_photo(
                FSInputFile(path),
                caption=text,
                reply_markup=ch5_quiz_review_kb()
            )
        else:
            await cb.message.answer(
                text + f"\n\n(⚠️ Не нашёл картинку: {path})",
                reply_markup=ch5_quiz_review_kb()
            )
    else:
        await cb.message.answer(text, reply_markup=ch5_quiz_review_kb())

    await cb.answer()

@router.callback_query(F.data == "camp:ch5:keyrate:info")
async def ch5_keyrate_info(cb: CallbackQuery):
    user_id = cb.from_user.id

    last_id = state.get(user_id, {}).get("last_story_msg_id")
    if last_id and cb.message.message_id != last_id:
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    await _safe_edit(cb, CH5_KEYRATE["info_text"], keyrate_back_kb())
    await cb.answer()

@router.callback_query(F.data == "camp:ch5:keyrate:back")
async def ch5_keyrate_back(cb: CallbackQuery):
    user_id = cb.from_user.id

    last_id = state.get(user_id, {}).get("last_story_msg_id")
    if last_id and cb.message.message_id != last_id:
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    step_idx = get_step(user_id)
    steps = get_steps_for(user_id)
    step = steps[step_idx]
    original_text = step.get("text", "")

    await _safe_edit(cb, original_text, keyrate_kb())
    await cb.answer()

@router.callback_query(F.data == "camp:ch5:keyrate:continue")
async def ch5_keyrate_continue(cb: CallbackQuery):
    user_id = cb.from_user.id
    st = state.get(user_id, {})

    last_id = st.get("last_keyrate_continue_msg_id")
    if last_id and cb.message.message_id != last_id:
        # старое сообщение
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.answer("Эта кнопка устарела 🙂", show_alert=False)
        return

    # одноразовость
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    step_idx = get_step(user_id)
    await cb.answer()
    await show_story(cb, step_idx + 1)

@router.message(F.text.regexp(r"^/ch([1-5])$"))
async def jump_to_chapter(message: Message):
    ch = int(message.text.replace("/ch", ""))

    # 1) Ставим главу
    set_chapter(message.from_user.id, ch)

    # 2) Сбрасываем состояние (step=0)
    state[message.from_user.id] = {"mode": "story", "step": 0, "chapter": ch}

    # 3) Показываем первый шаг
    await show_story(message, 0)
