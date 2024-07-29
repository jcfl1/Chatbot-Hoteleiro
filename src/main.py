"""Create the bot and define the logger."""

import argparse
import logging
import os
from dotenv import load_dotenv
from telegram_chatbot import TelegramChatbot
from rag import RAGParams


load_dotenv(".env")
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

DEFAULT_ASSISTANT_PROMPT = """"Você é um atendente com bastante experiência no ramo de hotelaria. \
Seu objetivo é fornecer respostas claras, concisas e profissionais. \
Mantenha um tom formal e educado. Responda à pergunta do usuário da forma mais concisa e informativa possível, \
sem informações desnecessárias. Se não souber a resposta, diga que não tem a informação e \
ofereça ajuda para encontrar a solução. Dê boas vindas ao cliente na sua primeira mensagem."
"""
DEFAULT_HOTEL_NAME = 'Pousada Porto de Galinhas'

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def create_parser():
    """salvando argumentos"""
    parser = argparse.ArgumentParser(description="Provide arguments for Chatbot Hoteleiro")
    parser.add_argument('--model', default='gpt-3.5-turbo', type=str, help='Model')

    return parser

def main() -> None:
    """orquestrador da aplicação"""
    parser = create_parser()
    args = parser.parse_args()
    rag_params = RAGParams(
        OPENAI_API_KEY,
        DEFAULT_HOTEL_NAME,
        DEFAULT_ASSISTANT_PROMPT,
        args.model
    )

    telegram_chatbot = TelegramChatbot(
        TELEGRAM_TOKEN,
        rag_params,
    )
    telegram_chatbot.run()

if __name__ == "__main__":
    main()
