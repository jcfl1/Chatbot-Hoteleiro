"""Define the class that collects the bot's response using the OpenAI model."""

from openai import OpenAI


class RAGApplication:
    """Iniciates RAG application
    
Params:
    openai_api_key (str): openai api key
    assistant_id (str): openai assistant id
    vector_store_id (str): vector store id
"""
    def __init__(self, openai_api_key: str, assistant_id: str, vector_store_id: str) -> None:
        self._assistant_id = assistant_id
        self._vector_store_id = vector_store_id
        self._run_id = -1

        self.client = OpenAI(api_key=openai_api_key)
        self.assistant = self.client.beta.assistants.update(
            assistant_id = assistant_id,
            tool_resources = {'file_search':{'vector_store_ids':[vector_store_id]}}
        )

        # RUNNING IN A *SINGLE* OPENAI THREAD! This may change in future
        self.thread = self.client.beta.threads.create()
        self._thread_id = self.thread.id

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
