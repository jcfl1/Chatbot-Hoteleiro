from dotenv import load_dotenv
from openai import OpenAI
import os


class RAGApplication:
    def __init__(self, openai_api_key, assistant_id, vector_store_id):
        self._assistant_id = assistant_id
        self._vector_store_id = vector_store_id
        
        self.client = OpenAI(api_key=openai_api_key)
        self.assistant = self.client.beta.assistants.update(
            assistant_id = assistant_id,
            tool_resources = {'file_search':{'vector_store_ids':[vector_store_id]}}
        )

        # RUNNING IN A *SINGLE* OPENAI THREAD! This may change in future
        self.thread = self.client.beta.threads.create()
        self._thread_id = self.thread.id

    def add_user_message(self, message):
        api_response = self.client.beta.threads.messages.create(
            thread_id = self._thread_id,
            role = 'user',
            content = message
        )
        return api_response
    
    def run_thread(self):
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
        return self.client.beta.threads.runs.steps.list(
            run_id = self._run_id,
            thread_id = self._thread_id
        )