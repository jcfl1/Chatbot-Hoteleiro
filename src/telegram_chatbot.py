"""Define the functions used by Telegram."""

import os
from telegram import ForceReply, Update
from telegram.ext import ContextTypes
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from rag import RAGAssistant


class TelegramChatbot:
    def __init__(self, 
                telegram_token: str, 
                openai_api_key: str,
                hotel_name: str,
                prompt: str,
                model: str,
                ) -> None:
        self.openai_api_key = openai_api_key
        self.hotel_name = hotel_name
        self.prompt = prompt
        self.model = model

        self.telegram_app = Application.builder().token(telegram_token).build()

        self.telegram_app.add_handler(CommandHandler("start", self.start))
        self.telegram_app.add_handler(CommandHandler("help", self.help_command))

        self.telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_bot_answer))

        self.chat_ids2assistants = {}


    def run(
        self
    ) -> None:
        """Runs telegram chatbot"""
        self.telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    async def start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Send a message when the command /start is issued."""

        chat_id = update.message.chat_id
        if chat_id not in self.chat_ids2assistants:
            self.chat_ids2assistants[chat_id] = RAGAssistant(
                self.openai_api_key,
                self.hotel_name,
                self.prompt,
                self.model
            )

        ## Old first message
        # await update.message.reply_html(
        #     rf"Oi {user.mention_html()}! Bem vindo ao chat com {self.hotel_name}. Como posso ajudar?",
        #     reply_markup=ForceReply(selective=True),
        # )

    async def help_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Send a message when the command /help is issued."""
        await update.message.reply_text(
            f"Você pode perguntar sobre o estabelecimento {self.hotel_name} que eu saberei responder 😁."
        )

    async def get_bot_answer(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Answers the general user message."""
        chat_id = update.message.chat_id

        if chat_id not in self.chat_ids2assistants:
            # Cria um contexto fake para chamar o método start
            context.user_data['force_start'] = True
            await self.start(update, context)

        rag_assistant = self.chat_ids2assistants[chat_id]

        rag_assistant.add_user_message(update.message.text)
        bot_message = str(rag_assistant.run_thread()["messages"][0])
        await update.message.reply_text(bot_message)
