from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Профиль", callback_data="menu:profile")
    kb.button(text="🎮 Игры", callback_data="menu:games")
    kb.button(text="🏆 Лидерборд", callback_data="menu:leaderboard")
    kb.button(text="🧠 Экономист", callback_data="menu:economist")
    kb.button(text="📖 Расскажи историю", callback_data="menu:campaign")
    kb.adjust(2,2,1)
    return kb.as_markup()

def back_to_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()
