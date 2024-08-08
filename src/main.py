"""Create the bot and define the logger."""

import argparse
import logging
import os
from dotenv import load_dotenv
from telegram_chatbot import TelegramChatbot
from rag import RAGParams
from prompts import DEFAULT_ASSISTANT_PROMPT

load_dotenv(".env")
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')

DEFAULT_HOTEL_NAME = 'Pousada Porto de Galinhas'

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def create_parser():
    """salvando argumentos"""
    parser = argparse.ArgumentParser(description="Provide arguments for Chatbot Hoteleiro")
    parser.add_argument('--model', default='gpt-4o', type=str, help='Model')
    
    return parser

def main() -> None:
    """orquestrador da aplicação"""
    parser = create_parser()
    args = parser.parse_args()
    rag_params = RAGParams(
        OPENAI_API_KEY,
        TAVILY_API_KEY,
        '',
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
