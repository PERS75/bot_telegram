import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from keyboards.main_menu import back_to_menu_kb
from services.scoring import upsert_user
from services.ai_client import ask_economist

router = Router()
log = logging.getLogger(__name__)


class AskState(StatesGroup):
    waiting_question = State()


PROMPT_TEXT = (
    "🧠 Экономист\n\n"
    "Напиши вопрос текстом (например: «Почему растут цены?»).\n"
    "Я постараюсь ответить простыми словами."
)


@router.callback_query(F.data == "menu:economist")
async def economist_cb(cb: CallbackQuery, state: FSMContext):
    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
    await state.set_state(AskState.waiting_question)

    await cb.message.edit_text(PROMPT_TEXT, reply_markup=back_to_menu_kb())
    await state.update_data(prompt_msg_id=cb.message.message_id)

    await cb.answer()


@router.callback_query(F.data == "menu:economist")
async def economist_cb(cb: CallbackQuery, state: FSMContext):
    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
    await state.set_state(AskState.waiting_question)
    await cb.message.edit_text(PROMPT_TEXT, reply_markup=back_to_menu_kb())
    await cb.answer()


@router.message(AskState.waiting_question, F.text)
async def economist_question(message: Message, state: FSMContext):
    q = message.text.strip()


    data = await state.get_data()
    prompt_id = data.get("prompt_msg_id")
    if prompt_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=prompt_id,
                reply_markup=None
            )
        except Exception:
            pass

    # ✅ достаём данные FSM
    data = await state.get_data()
    if data.get("ai_busy"):
        await message.answer("🤖 Я ещё думаю над прошлым вопросом 🙂 Подожди ответ и напиши следующий.")
        return

    if len(q) < 3:
        await message.answer("Слишком коротко 🙂 Напиши вопрос чуть подробнее.", reply_markup=back_to_menu_kb())
        return

    # ✅ ставим флаг busy
    await state.update_data(ai_busy=True)

    await message.answer("🤖 Думаю…")

    try:
        answer = await ask_economist(q)
    except Exception:
        log.exception("Economist request failed")
        # ✅ снимаем флаг busy даже при ошибке
        await state.update_data(ai_busy=False)
        await message.answer("Сейчас не получилось получить ответ. Попробуй позже.", reply_markup=back_to_menu_kb())
        return

    # ✅ снимаем флаг busy
    await state.update_data(ai_busy=False)

    if not answer:
        answer = "Не получилось сформировать ответ. Попробуй переформулировать вопрос."

    await message.answer(
        answer + "\n\n(Можешь задать следующий вопрос или нажать «🏠 Главное меню»)",
        reply_markup=back_to_menu_kb()
    )

    # ✅ Остаёмся в AskState.waiting_question — ничего не очищаем
