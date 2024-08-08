"""Define the class that collects the bot's response using the OpenAI model."""

import os
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from openai import OpenAI
from tavily import TavilyClient

BASE_PROMPT = 'Você é um atendente da rede hoteleira do estabelecimento de nome "{}"\n\n'
VECTOR_STORE_PATH = os.path.join('data', 'hotels2vector_stores.json')

def create_vector_store(booking_hotel_dict: dict, openai_api_key: str) -> str:
    """Creates vector store for scraped hotel.

    Args:
        booking_hotel_dict (dict): scraped dict
        openai_api_key (str): api key

    Returns:
        str: vector store id
    """

    with open(VECTOR_STORE_PATH, 'rt', encoding="utf-8") as f:
        hotels2vector_stores = json.load(f)

    hotel_name = booking_hotel_dict['title']

    if hotel_name in hotels2vector_stores:
        print(
            f'[INFO] The hotel {hotel_name} is already in hotels2vector_stores.json. Skipping it.'
        )
        return hotels2vector_stores[hotel_name]

    output_dir = Path(os.path.join('..', 'data', 'tmp'))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"booking_hotel_data_{hotel_name}.json"
    output_file.write_text(
        json.dumps(booking_hotel_dict, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    client = OpenAI(api_key=openai_api_key)
    vector_store = client.beta.vector_stores.create(name=f'Booking Data "{hotel_name}"')
    file_upload = client.beta.vector_stores.files.upload_and_poll(
        vector_store_id=vector_store.id, file=output_file
    )
    print(f'File upload status: {file_upload.status}')

    # Updating hotels2vector_stores.json
    hotels2vector_stores[hotel_name] = vector_store.id
    with open(VECTOR_STORE_PATH, 'wt', encoding="utf-8") as f:
        json.dump(hotels2vector_stores, f, indent=2)

    return vector_store.id

@dataclass
class RAGParams():
    """Object to store the necessary params for RAG assistant. 
       
    Params:
        openai_api_key (str): openai api key
        hotel_name (str): hotel name
        prompt (str): prompt
        model (str): model
"""
    openai_api_key: str
    tavily_api_token:str
    tools : str
    hotel_name: str
    prompt: str
    model: str


class RAGAssistant:
    """Iniciates RAG Assistant
    
Params:
    rag_params (RAGParams): Parameters for the assistant
"""
    def __init__(self, 
        rag_params: RAGParams
        ) -> None:

        with open(VECTOR_STORE_PATH, 'rt', encoding="utf-8") as f:
            hotels2vector_stores = json.load(f)

        if rag_params.hotel_name not in hotels2vector_stores:
            raise ValueError(f'Please first create a vector store for hotel {rag_params.hotel_name} before creating an assistant to it.') # pylint: disable=line-too-long
        self.vector_store_id = hotels2vector_stores[rag_params.hotel_name]

        self.client = OpenAI(api_key=rag_params.openai_api_key)
        self.assistant = self.client.beta.assistants.create(
            name = f"{rag_params.hotel_name} Assistant {secrets.token_hex(4)}",
            instructions = BASE_PROMPT.format(rag_params.hotel_name) + rag_params.prompt,
            model = rag_params.model,
            tools = rag_params.tools,
            tool_resources = {"file_search": {"vector_store_ids": [self.vector_store_id]}}
        )

        self.tavily_client = TavilyClient(api_key=rag_params.tavily_api_token)
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

    def tavily_search(self, query):
        search_result = self.tavily_client.qna_search(query, search_depth="advanced") 
        return search_result
    
    def run_thread(self) -> dict:
        """Returns:
            dict: {'messages':messages, 'messages_detailed':messages_detailed, 'run':run}
        """

        run = self.client.beta.threads.runs.create_and_poll(
            thread_id = self._thread_id,
            assistant_id = self._assistant_id
        )
        self._run_id = run.id

        while run.status not in ["completed", "failed"]:
            run = self.client.beta.threads.runs.retrieve(
                thread_id = self.thread.id,
                run_id = run.id
            )
            if run.status == "requires_action":
                tools_to_call = run.required_action.submit_tool_outputs.tool_calls
                tools_output_array = []
                for each_tool in tools_to_call:
                    output = None
                    tool_call_id = each_tool.id
                    function_name = each_tool.function.name
                    function_args = each_tool.function.arguments
                    print("Tool ID:" + tool_call_id)
                    print("Function to Call:" + function_name )
                    print("Parameters to use:" + function_args)

                    if (function_name == 'get_tourist_points'):
                        output = self.tavily_search(query=json.loads(function_args)["query"])
                    if (function_name == 'get_restaurants'):
                        output = self.tavily_search(query=json.loads(function_args)["query"])
                    if output:
                        tools_output_array.append({"tool_call_id": tool_call_id, "output": output})

                    self.client.beta.threads.runs.submit_tool_outputs(
                        thread_id = self._thread_id,
                        run_id = run.id,
                        tool_outputs=tools_output_array
                    )
            time.sleep(1)
            print(run.status)

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
