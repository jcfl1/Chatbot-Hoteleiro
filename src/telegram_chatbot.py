"""Define the functions used by Telegram."""

from urllib.parse import urlparse
from datetime import datetime, timedelta
import re
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from bookingcom import scrape_hotel
from rag import RAGAssistant, create_vector_store, RAGParams


def is_valid_url(url: str) -> bool:
    """
    Args:
        url (str): url to be tested

    Returns:
        bool: True if the url is valid
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


class TelegramChatbot:
    """Iniciates Telegram Chatbot
Params:
    telegram_token (str): telegram token
    rag_params (RAGParams): Parameters for the assistant
"""
    def __init__(self,
                telegram_token: str,
                rag_params: RAGParams
                ) -> None:
        self.rag_params = rag_params

        self.telegram_app = Application.builder().token(telegram_token).build()

        self.telegram_app.add_handler(CommandHandler("start", self.start))
        self.telegram_app.add_handler(CommandHandler("help", self.help_command))
        self.telegram_app.add_handler(CommandHandler("hotel", self.hotel_command))

        self.telegram_app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_bot_answer)
        )

        self.chat_ids2assistants = {}


    def run(
        self
    ) -> None:
        """Runs telegram chatbot"""
        self.telegram_app.run_polling(poll_interval=2,allowed_updates=Update.ALL_TYPES)

    async def start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Send a message when the command /start is issued."""

        chat_id = update.message.chat_id
        if chat_id not in self.chat_ids2assistants:
            self.chat_ids2assistants[chat_id] = RAGAssistant(
                self.rag_params
            )

        await update.message.reply_text(
            f"Olá, bem-vindo! Você pode perguntar sobre o estabelecimento {self.rag_params.hotel_name} que eu saberei responder 😁." # pylint: disable=line-too-long
        )

    async def help_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Send a message when the command /help is issued."""
        await update.message.reply_text(
            f"Você pode perguntar sobre o estabelecimento {self.rag_params.hotel_name} que eu saberei responder 😁." # pylint: disable=line-too-long
        )

    async def hotel_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Handle the /hotel command to create a new assistant for a specific hotel URL."""
        chat_id = update.message.chat_id
        # user = update.effective_user
        message_text = update.message.text

        # Extract the URL from the command message
        parts = message_text.split()
        if len(parts) != 2:
            await update.message.reply_text(
                "Por favor, forneça a URL da página do Booking do hotel no formato: /hotel <URL>"
            )
            return

        hotel_booking_url = parts[1]
        if (not is_valid_url(hotel_booking_url)) or ('booking.com' not in hotel_booking_url):
            await update.message.reply_text(
                "Por favor, forneça a URL da página do Booking do hotel no formato: /hotel <URL>"
            )
            return

        days_to_scrape_prices = 7
        booking_hotel_dict = await scrape_hotel(
            hotel_booking_url,
            checkin=(
                datetime.now() + timedelta(days=days_to_scrape_prices)
            ).strftime('%Y-%m-%d'), # One week from now
            price_n_days=days_to_scrape_prices,
        )
        create_vector_store(booking_hotel_dict, self.rag_params.openai_api_key)
        self.rag_params.hotel_name = booking_hotel_dict['title']

        # Create a new assistant associated with the provided URL
        context.user_data['force_start'] = True
        await self.start(update, context)
        self.chat_ids2assistants[chat_id] = RAGAssistant(
            self.rag_params
        )

    async def get_bot_answer(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Answers the general user message."""
        chat_id = update.message.chat_id
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        if chat_id not in self.chat_ids2assistants:
            # Cria um contexto fake para chamar o método start
            context.user_data['force_start'] = True
            await self.start(update, context)

        rag_assistant = self.chat_ids2assistants[chat_id]

        rag_assistant.add_user_message(update.message.text)
        bot_message = str(rag_assistant.run_thread()["messages"][0])
        # Removing retrieval references
        bot_message_cleaned = re.sub('【.*?†source】', '', bot_message)
        await update.message.reply_text(bot_message_cleaned)
