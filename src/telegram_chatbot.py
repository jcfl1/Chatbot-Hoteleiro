"""Define the functions used by Telegram."""

from urllib.parse import urlparse
from datetime import datetime, timedelta
import requests
import os
import tempfile
import re, time
import openai
from telegram import Update, Message
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from bookingcom import scrape_hotel
from rag import RAGAssistant, create_vector_store, RAGParams
from prompts import promptsPersona
from pydub import AudioSegment

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
        self.telegram_token = telegram_token

        self.telegram_app = Application.builder().token(telegram_token).build()

        self.telegram_app.add_handler(CommandHandler("start", self.start_command))
        self.telegram_app.add_handler(CommandHandler("help", self.help_command))
        self.telegram_app.add_handler(CommandHandler("hotel", self.hotel_command))
        self.telegram_app.add_handler(CommandHandler("Marcos", self.create_persona_handler("Marcos")))
        self.telegram_app.add_handler(CommandHandler("Ana", self.create_persona_handler("Ana")))
        self.telegram_app.add_handler(CommandHandler("Lucas", self.create_persona_handler("Lucas")))

        self.telegram_app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_bot_answer)
        )

        self.telegram_app.add_handler(
            MessageHandler(filters.AUDIO | filters.VOICE, self.handle_audio)
        )

        self.chat_ids2assistants = {}


    def run(
        self
    ) -> None:
        """Runs telegram chatbot"""
        self.telegram_app.run_polling(poll_interval=2,allowed_updates=Update.ALL_TYPES)

    async def start_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Send a message when the command /start is issued."""
        await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
        await update.message.reply_text(
            f"""
            Seja bem-vindo(a) ao {self.rag_params.hotel_name}! 👋\n \n"""
            """Sou o assistente virtual do hotel e estou aqui para te ajudar no que precisar. Para que eu possa te atender melhor, escolha um dos nossos especialistas: \n \n"""
            """Para começar, digite:\n"""
            """- /Marcos: Respostas precisas e objetivas para suas perguntas sobre o hotel. 🤖\n \n"""
            """- /Ana: Uma verdadeira historiadora, te conta tudo sobre a cultura e história dos pontos turisticos da região. 🏛️\n \n"""
            """- /Lucas: Uma especialista em gastronomia, te dá dicas dos melhores restaurantes e pratos da região. 🍽️\n \n"""
            """Escolha seu assistente e começe a explorar! 😊"""
        )
        await update.message.reply_text(
            """Caso deseje assistência com outros hoteis, digite:\n"""
            """/hotel <URL DO HOTEL NO BOOKING.COM>"""
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

    def create_persona_handler(self, persona):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await self.persona_command(persona, update, context)
        return wrapper

    async def persona_command(
        self,
        persona,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        await self.handle_assistant(persona,promptsPersona[persona], update, context)
        await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
        await update.message.reply_text(
            f"Olá! Sou {persona}, atendente do {self.rag_params.hotel_name}. Estou à sua disposição, como eu poderia ajudar?😊"
        )

    async def handle_assistant (
        self,
        persona,
        prompt,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:

        chat_id = update.message.chat_id
        if persona == "Marcos":
            self.rag_params.tools = [{'type':'file_search'}]
        elif  persona == "Ana":
            self.rag_params.tools = [{
                'type':'file_search'
                    }, {
                        "type": "function",
                        "function": {
                            "name": "get_tourist_points",
                            "description": "Esta função recebe um endereço e retorna os pontos turisticos proximos, junto com informações sobre a cultura e historia da região .",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "The search query to use. For example: 'pontos turisticos proximos a pousada porto de galinhas'"},
                                },
                                "required": ["query"]
                            }
                        }
                    }]
        else:
            self.rag_params.tools = [{'type':'file_search'},
                    {
                    "type": "function",
                    "function": {
                        "name": "get_restaurants",
                        "description": "Esta função recebe um endereço proximo e retorna os restaurantes e bares próximos.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "The search query to use. For example: 'bares e restaurantes proximos a pousada porto de galinhas'"},
                            },
                            "required": ["query"]
                        }
                    }
                }]
        self.rag_params.prompt = promptsPersona[persona]
        self.chat_ids2assistants[chat_id] = RAGAssistant(self.rag_params)


    async def hotel_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE # pylint: disable=unused-argument
    ) -> None:
        """Handle the /hotel command to create a new assistant for a specific hotel URL."""
        chat_id = update.message.chat_id
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
        await self.start_command(update, context)
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
    
        if chat_id not in self.chat_ids2assistants:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await update.message.reply_text("Por Favor, antes de começar, selecione seu assistente.")
        else:
            #  await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
             """Answers the general user message."""
             await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
             rag_assistant = self.chat_ids2assistants[chat_id]

             print('setei rag assistant')
           
             rag_assistant.add_user_message(update.message.text)
             print('add')
             bot_message = str(rag_assistant.run_thread()["messages"][0])
             print('rodei a thread')

            # Removing retrieval references
             bot_message_cleaned = re.sub('【.*?†source】', '', bot_message)
             
             await update.message.reply_text(bot_message_cleaned)

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.message.chat_id
        # audio_file = await update.message.voice.get_file() if update.message.voice else await update.message.audio.get_file()
        # my_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.oga')
        # with open(my_audio_file.name, 'wb') as f:
        #     f.write(audio_file)
        file_id = update['message']['voice']['file_id']
        file_path = requests.get(f'https://api.telegram.org/bot{self.telegram_token}/getFile?file_id={file_id}').json()['result']['file_path']
        file_url = f'https://api.telegram.org/file/bot{self.telegram_token}/{file_path}'
        audio_data = requests.get(file_url).content
        temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.oga')
        with open(temp_audio_file.name, 'wb') as f:
            f.write(audio_data)
        audio_local_path = temp_audio_file.name

        # file_path = await audio_file.download_to_drive()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file:
            AudioSegment.from_file(audio_local_path).export(temp_audio_file.name, format="mp3")
            transcript = await self.transcrever_audio(temp_audio_file.name)
        # os.remove(my_audio_file.name)

        # o text não pode ser setado diretamente, então é necessário criar uma nova mensagem
        message = Message(
            message_id=update.message.message_id,
            date=update.message.date,
            chat=update.message.chat,
            from_user=update.message.from_user,
            text=transcript
        )
        message.set_bot(context.bot)
        new_update = Update(
            update_id=update.update_id,
            message=message,
        )
        print(context)
        # Em seguida, processa a transcrição como se fosse uma mensagem de texto normal
        await self.get_bot_answer(new_update, context)

    async def transcrever_audio(self, arquivo_audio):
        with open(arquivo_audio, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")
            print(transcript)
            return transcript.__str__()
