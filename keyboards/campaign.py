from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def story_kb(next_text: str = "Далее", show_menu: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=next_text, callback_data="camp:next")

    if show_menu:
        kb.button(text="🏠 В меню", callback_data="menu:home")
        kb.adjust(1, 1)
    else:
        kb.adjust(1)

    return kb.as_markup()


def crossword_kb(wrong_tries: int, hint_used: bool) -> InlineKeyboardMarkup | None:
    """
    Правила:
    - До первой ошибки: кнопок нет
    - После 1-й ошибки: показываем Подсказку
    - Турбо показываем ТОЛЬКО если hint_used=True (пользователь уже нажимал подсказку на этом слове)
    """
    kb = InlineKeyboardBuilder()

    if wrong_tries <= 0:
        return None

    if not hint_used:
        kb.button(text="💡 Подсказка", callback_data="camp:hint")
    else:
        kb.button(text="🆘 Турбо, помоги!", callback_data="camp:turbo")

    kb.adjust(1)
    return kb.as_markup()


def ai_entry_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 Спросить у робота", callback_data="camp:ai:start")
    kb.button(text="Продолжить", callback_data="camp:ai:done")
    kb.adjust(1, 1)
    return kb.as_markup()

def ai_back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Вернуться", callback_data="camp:ai:done")
    return kb.as_markup()

def ai_done_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Теперь понятно", callback_data="camp:ai:done")
    return kb.as_markup()

def rebus_kb(wrong_tries: int):
    """
    Ребус:
    - 0 ошибок -> кнопок нет
    - 1+ ошибок -> кнопка 'Турбо, помоги!'
    """
    if wrong_tries <= 0:
        return None

    kb = InlineKeyboardBuilder()
    kb.button(text="🆘 Турбо, помоги!", callback_data="camp:rebus:turbo")
    kb.adjust(1)
    return kb.as_markup()

def keyrate_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="A) Понизить", callback_data="camp:ch5:keyrate:A")
    kb.button(text="Б) Повысить", callback_data="camp:ch5:keyrate:B")
    kb.button(text="В) Оставить как есть", callback_data="camp:ch5:keyrate:V")
    kb.button(text="❓ Что такое ключевая ставка?", callback_data="camp:ch5:keyrate:info")
    kb.adjust(1)
    return kb.as_markup()

def keyrate_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Теперь понятно", callback_data="camp:ch5:keyrate:back")
    kb.adjust(1)
    return kb.as_markup()

def ch3_story_choice_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="У меня остались вопросы", callback_data="camp:next")
    kb.button(text="Продолжить сюжет", callback_data="camp:skip_ai")
    kb.adjust(1)
    return kb.as_markup()

def ch5_quiz_kb(q_idx: int, options: list[str]):
    kb = InlineKeyboardBuilder()
    for i, opt in enumerate(options):
        kb.button(text=opt, callback_data=f"camp:ch5:quiz:ans:{q_idx}:{i}")
    kb.adjust(1)
    return kb.as_markup()

def ch5_quiz_next_kb(is_last: bool):
    kb = InlineKeyboardBuilder()
    kb.button(
        text=("Завершить тест" if is_last else "Дальше"),
        callback_data=("camp:ch5:quiz:finish" if is_last else "camp:ch5:quiz:next"),
    )
    kb.adjust(1)
    return kb.as_markup()

def ch5_quiz_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()

def keyrate_thanks_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🙏 Спасибо!", callback_data="camp:ch5:keyrate:continue")
    kb.adjust(1)
    return kb.as_markup()

def keyrate_win_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏆 Мы победили!", callback_data="camp:ch5:keyrate:continue")
    kb.adjust(1)
    return kb.as_markup()