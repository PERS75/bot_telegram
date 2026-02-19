import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands
from aiogram.fsm.storage.memory import MemoryStorage
from handlers.pvp_quiz import router as pvp_router
from handlers import campaign

from config import BOT_TOKEN
from handlers import start, games_menu, tf_game, profile, leaderboard, ask_economist
from handlers.quiz_game import router as quiz_router

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(games_menu.router)
    dp.include_router(tf_game.router)
    dp.include_router(profile.router)
    dp.include_router(leaderboard.router)
    dp.include_router(ask_economist.router) 
    dp.include_router(quiz_router)
    dp.include_router(pvp_router)
    dp.include_router(campaign.router)
    # на всякий случай убираем webhook
    await bot.delete_webhook(drop_pending_updates=True)

    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="menu", description="Открыть главное меню"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    logging.info("✅ Starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
    except Exception as e:
        # если бот падает — ты это точно увидишь
        logging.exception("🔥 Bot crashed with exception:")
        raise