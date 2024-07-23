"""Define the class that collects the bot's response using the OpenAI model."""

import os
import tempfile
from pathlib import Path
from openai import OpenAI
import json
import secrets

BASE_PROMPT = 'Você é um atendente da rede hoteleira do estabelecimento de nome "{}"\n\n'

def create_vector_store(booking_hotel_dict, openai_api_key):
    path_hotels2vector_stores = os.path.join('..', 'data', 'hotels2vector_stores.json')
    hotels2vector_stores = json.load(open(path_hotels2vector_stores, 'rt'))

    hotel_name = booking_hotel_dict['title']

    if hotel_name in hotels2vector_stores:
        print(f'[INFO] The hotel {hotel_name} is already in hotels2vector_stores.json. Skipping it.')
        return
    
    output_dir = Path(os.path.join('..', 'data', 'tmp'))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"booking_hotel_data_{hotel_name}.json"
    output_file.write_text(json.dumps(booking_hotel_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    client = OpenAI(api_key=openai_api_key)
    vector_store = client.beta.vector_stores.create(name=f'Booking Data "{hotel_name}"')
    file_upload = client.beta.vector_stores.files.upload_and_poll(
        vector_store_id=vector_store.id, file=output_file
    )
    print(f'File upload status: {file_upload.status}')

    # Updating hotels2vector_stores.json
    hotels2vector_stores[hotel_name] = vector_store.id
    with open(path_hotels2vector_stores, 'wt') as f:
        json.dump(hotels2vector_stores, f, indent=2)

    return vector_store.id


class RAGAssistant:
    """Iniciates RAG Assistant
    
Params:
    openai_api_key (str): openai api key
    hotel_name (str): hotel name
    prompt (str): prompt
    model (str): model
"""
    def __init__(self, openai_api_key: str, 
                hotel_name: str, 
                prompt: str, 
                model: str) -> None:
        self.hotel_name = hotel_name
        hotels2vector_stores = json.load(open('../data/hotels2vector_stores.json', 'rt'))
        if hotel_name not in hotels2vector_stores:
            raise ValueError(f'Please first create a vector store for hotel {hotel_name} before create an assistant to this hotel.')
        self.vector_store_id = hotels2vector_stores[hotel_name]

        self.client = OpenAI(api_key=openai_api_key)
        self.assistant = self.client.beta.assistants.create(
            name = f"{hotel_name} Assistant {secrets.token_hex(4)}",
            instructions = BASE_PROMPT.format(hotel_name) + prompt,
            model = model,
            tools = [{"type": "file_search"}],
            tool_resources = {"file_search": {"vector_store_ids": [self.vector_store_id]}}
        )

        self.thread = self.client.beta.threads.create()

        self._assistant_id = self.assistant.id
        self._thread_id = self.thread.id
        self._run_id = -1

    def update_assistant_prompt(self, assistant_prompt: str):
        """Updates assistant prompt"""
        self.assistant = self.client.beta.assistants.update(
            assistant_id = self._assistant_id,
            instructions = assistant_prompt
        )

    def add_user_message(self, message: str):
        """Adds user message to thread

        Args:
            message (str): user message

        Returns:
            Messase: api response
        """
        api_response = self.client.beta.threads.messages.create(
            thread_id = self._thread_id,
            role = 'user',
            content = message
        )
        return api_response

    def run_thread(self) -> dict:
        """Returns:
            dict: {'messages':messages, 'messages_detailed':messages_detailed, 'run':run}
        """

        run = self.client.beta.threads.runs.create_and_poll(
            thread_id = self._thread_id,
            assistant_id = self._assistant_id
        )
        self._run_id = run.id

        messages_detailed = list(self.client.beta.threads.messages.list(
            thread_id = self._thread_id,
            run_id = run.id
            ))

        messages = [message.content[0].text.value for message in messages_detailed]

        return {'messages':messages, 'messages_detailed':messages_detailed, 'run':run}

    def get_detailed_run_steps(self):
        """Get deails by the run id and thread id"""
        return self.client.beta.threads.runs.steps.list(
            run_id = self._run_id,
            thread_id = self._thread_id
        )
