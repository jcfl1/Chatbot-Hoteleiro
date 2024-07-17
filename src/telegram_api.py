"""Define the functions used by Telegram."""

import os
from dotenv import load_dotenv
from telegram import ForceReply, Update
from telegram.ext import ContextTypes
from rag import RAGApplication


load_dotenv(".env")
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
VECTOR_STORE_ID = os.getenv('VECTOR_STORE_ID')
ASSISTANT_ID = os.getenv('ASSISTANT_ID')

rag_application = RAGApplication(OPENAI_API_KEY, ASSISTANT_ID, VECTOR_STORE_ID)

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Oi {user.mention_html()}! Como posso ajudar?",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Você pode perguntar sobre Hoteis em Porto de Galinhas que eu saberei responder 😁."
    )

async def get_bot_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
) -> None:
    """Answers the general user message."""
    rag_application.add_user_message(update.message.text)
    bot_message = str(rag_application.run_thread()["messages"][0])
    await update.message.reply_text(bot_message)
