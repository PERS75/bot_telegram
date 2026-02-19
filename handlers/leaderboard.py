from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.scoring import upsert_user, get_daily_leaderboard, get_leaderboard, get_user_display

router = Router()


def render_daily() -> str:
    items, day = get_daily_leaderboard(limit=10)
    if not items:
        return f"🏆 Лидерборд за {day}\n\nПока пусто 🙂"
    lines = [f"🏆 Лидерборд за {day}\n"]
    for i, (uid, pts) in enumerate(items, 1):
        lines.append(f"{i}. {get_user_display(uid)} — {pts}")
    return "\n".join(lines)


def render_total() -> str:
    items = get_leaderboard(limit=10)
    if not items:
        return "🏆 Лидерборд (всего)\n\nПока пусто 🙂"
    lines = ["🏆 Лидерборд (всего)\n"]
    for i, (uid, pts) in enumerate(items, 1):
        lines.append(f"{i}. {get_user_display(uid)} — {pts}")
    return "\n".join(lines)


def leaderboard_kb(active: str = "daily"):
    kb = InlineKeyboardBuilder()

    if active == "daily":
        kb.button(text="✅ Сегодня", callback_data="lb:daily")
        kb.button(text="За всё время", callback_data="lb:total")
    else:
        kb.button(text="Сегодня", callback_data="lb:daily")
        kb.button(text="✅ За всё время", callback_data="lb:total")

    kb.adjust(2)
    kb.row(
        InlineKeyboardBuilder()
        .button(text="🏠 Главное меню", callback_data="menu:home")
        .as_markup().inline_keyboard[0][0]
    )
    return kb.as_markup()

@router.callback_query(F.data == "menu:leaderboard")
async def leaderboard_cb(cb: CallbackQuery):
    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)

    text = render_daily()
    kb = leaderboard_kb(active="daily")

    if cb.message and cb.message.text:
        await cb.message.edit_text(text, reply_markup=kb)
    else:
        if cb.message:
            try:
                await cb.message.delete()
            except Exception:
                pass
        await cb.message.answer(text, reply_markup=kb)

    await cb.answer()

@router.callback_query(F.data == "lb:daily")
async def leaderboard_daily(cb: CallbackQuery):
    text = render_daily()
    await cb.message.edit_text(text, reply_markup=leaderboard_kb(active="daily"))
    await cb.answer()


@router.callback_query(F.data == "lb:total")
async def leaderboard_total(cb: CallbackQuery):
    text = render_total()
    await cb.message.edit_text(text, reply_markup=leaderboard_kb(active="total"))
    await cb.answer()

@router.message(Command("leaderboard"))
async def leaderboard_msg(message: Message):
    upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(render_daily(), reply_markup=leaderboard_kb(active="daily"))