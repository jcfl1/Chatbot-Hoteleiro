"""Create the bot and define the logger."""

import logging
import os
from dotenv import load_dotenv
from telegram import  Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram_api import start, help_command, get_bot_answer

load_dotenv(".env")
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    """orquestrador do telegram"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_bot_answer))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
