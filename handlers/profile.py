from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.main_menu import back_to_menu_kb
from services.scoring import upsert_user, get_profile, get_user_display
from services.progress import get_seen_today
from services.pvp_stats import get_stats

router = Router()

def level_title(total_points: int) -> str:
    # простая шкала — легко объяснить на защите
    if total_points < 20:
        return "🟢 Новичок"
    if total_points < 60:
        return "🟡 Ученик"
    if total_points < 120:
        return "🔵 Знаток"
    return "🟣 Юный экономист"


def profile_text(name: str, total: int, today: int, seen_tf_today: int, seen_quiz_today: int, pvp: dict) -> str:
    return (
        f"👤 Профиль\n\n"
        f"Игрок: {name}\n"
        f"🎓 Уровень: {level_title(total)}\n\n"
        f"⭐ Очки всего: {total}\n"
        f"📅 Очки сегодня: {today}\n\n"
        f"📊 Статистика (сегодня):\n"
        f"— TF «Правда/Ложь» решено: {seen_tf_today}\n"
        f"— 🧠 Викторина решено: {seen_quiz_today}\n"
        f"\n⚔️ PvP дуэли:\n"
        f"— 🏆 Побед: {pvp['wins']}\n"
        f"— ❌ Поражений: {pvp['losses']}\n"
        f"— 🤝 Ничьих: {pvp['draws']}"
    )


@router.message(Command("profile"))
async def profile_msg(message: Message, state: FSMContext):
    # ✅ если пользователь был в "экономисте" / игре и т.п. — выключаем режим
    await state.clear()

    upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)

    uid = message.from_user.id
    total, today = get_profile(uid)
    name = get_user_display(uid)

    seen_tf_today = len(get_seen_today(uid, "tf"))
    seen_quiz_today = len(get_seen_today(uid, "quiz"))
    pvp = get_stats(uid)
    text = profile_text(name, total, today, seen_tf_today, seen_quiz_today, pvp)

    photos = await message.bot.get_user_profile_photos(uid, limit=1)
    if photos.total_count > 0:
        photo_id = photos.photos[0][-1].file_id
        await message.answer_photo(photo_id, caption=text, reply_markup=back_to_menu_kb())
    else:
        await message.answer(text, reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "menu:profile")
async def profile_cb(cb: CallbackQuery, state: FSMContext):
    # ✅ при переходе из меню тоже сбрасываем состояние
    await state.clear()

    upsert_user(cb.from_user.id, cb.from_user.full_name, cb.from_user.username)

    uid = cb.from_user.id
    total, today = get_profile(uid)
    name = get_user_display(uid)
    seen_tf_today = len(get_seen_today(uid, "tf"))
    seen_quiz_today = len(get_seen_today(uid, "quiz"))
    pvp = get_stats(uid)
    text = profile_text(name, total, today, seen_tf_today, seen_quiz_today, pvp)
    photos = await cb.bot.get_user_profile_photos(uid, limit=1)

    # Если у пользователя есть аватар — показываем фото + caption (нельзя edit_text на медиа)
    if photos.total_count > 0:
        photo_id = photos.photos[0][-1].file_id

        # delete может иногда не сработать — не падаем
        if cb.message:
            try:
                await cb.message.delete()
            except Exception:
                pass

        await cb.message.answer_photo(photo_id, caption=text, reply_markup=back_to_menu_kb())
    else:
        # если вдруг кнопка нажата под сообщением без текста — не падаем
        if cb.message and cb.message.text:
            await cb.message.edit_text(text, reply_markup=back_to_menu_kb())
        else:
            if cb.message:
                try:
                    await cb.message.delete()
                except Exception:
                    pass
            await cb.message.answer(text, reply_markup=back_to_menu_kb())

    await cb.answer()