from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.main_menu import back_to_menu_kb
from services.scoring import upsert_user

router = Router()


def games_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅❌ Правда / Ложь", callback_data="tf:start")
    kb.button(text="🧠 Викторина", callback_data="quiz:start")
    kb.button(text="⚔️ PvP Викторина", callback_data="pvp:invite")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(2,1,1)
    return kb.as_markup()


@router.message(Command("games"))
async def open_games(message: Message):
    upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer("🎮 Игры\n\nВыбери игру:", reply_markup=games_kb())


@router.callback_query(F.data == "menu:games")
async def open_games_cb(cb: CallbackQuery):
    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
    await cb.message.edit_text("🎮 Игры\n\nВыбери игру:", reply_markup=games_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("stub:"))
async def stub(cb: CallbackQuery):
    await cb.answer("Этот режим пока в разработке 🙂", show_alert=True)
