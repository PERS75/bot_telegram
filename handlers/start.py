from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from handlers.pvp_quiz import invite_kb
from services.pvp_storage import get_match
from keyboards.main_menu import main_menu_kb
from services.scoring import upsert_user
router = Router()

MENU_TEXT = (
    "🏠 Главное меню\n\n"
    "В этом боте ты можешь:\n"
    "— 🎮 играть в мини-игры и отвечать на вопросы\n"
    "— 🤖 задавать вопросы ИИ-помощнику и получать объяснения простыми словами\n"
    "— 👤 смотреть свои достижения и набранные очки в профиле\n"
    "— 🏆 заглядывать в лидерборд и сравнивать результаты с друзьями\n"
    "— 📖 проходить увлекательную сюжетную линию\n\n"
    "Выбери, с чего хочешь начать 👇"
)

@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()

    upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)

    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("pvp_"):
        match_id = parts[1].replace("pvp_", "", 1)

        match = await get_match(match_id)
        if not match or match.get("status") != "waiting":
            await message.answer("Этот вызов уже неактуален 🙂")
            return

        await message.answer(
            "⚔️ Тебя пригласили в PvP-дуэль!\n\nНажми, чтобы принять:",
            reply_markup=invite_kb(match_id)
        )
        return

    # ✅ если это обычный /start — показываем меню
    await show_menu(message)
    

    
async def show_menu(message: Message):
    await message.answer(MENU_TEXT, reply_markup=main_menu_kb())


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()          # ✅ СБРОС ВСЕХ СОСТОЯНИЙ
    await show_menu(message)


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext):
    await state.clear()          # ✅ СБРОС ВСЕХ СОСТОЯНИЙ
    await show_menu(message)


@router.callback_query(F.data == "menu:home")
async def menu_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()          # ✅ СБРОС ВСЕХ СОСТОЯНИЙ

    if cb.message and cb.message.text:
        await cb.message.edit_text(MENU_TEXT, reply_markup=main_menu_kb())
    else:
        if cb.message:
            try:
                await cb.message.delete()
            except Exception:
                pass
        await cb.message.answer(MENU_TEXT, reply_markup=main_menu_kb())

    await cb.answer()