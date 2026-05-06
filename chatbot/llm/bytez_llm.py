"""
Groq LLM Wrapper for Onboarding AI Chatbot

Drop-in replacement for the old Bytez wrapper.
Uses Groq's OpenAI-compatible API with llama-3.3-70b-versatile.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL   = 'llama-3.1-8b-instant'


class BytezLLM:
    """Groq backend, drop-in replacement for the old Bytez wrapper."""

    DEFAULT_MODEL = GROQ_MODEL

    def __init__(
        self,
        model_name: str = None,
        api_key: str = None,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ):
        self.model_name  = model_name or self.DEFAULT_MODEL
        self.api_key     = api_key or GROQ_API_KEY
        self.max_tokens  = max_tokens
        self.temperature = temperature
        self._init_client()

    def _init_client(self):
        try:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url='https://api.groq.com/openai/v1',
            )
            self._available = True
        except Exception as e:
            print(f"Warning: Failed to initialize Groq client: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        if not self._available:
            return "Error: LLM not available. Please check your Groq API configuration."
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"
    
    def health_check(self) -> dict:
        if not self._available:
            return {'status': 'error', 'message': 'LLM client not initialized'}
        try:
            response = self.generate("Say 'OK' if you're working.")
            if 'ok' in response.lower():
                return {'status': 'ok', 'model': self.model_name, 'message': 'LLM is responding correctly'}
            return {'status': 'warning', 'model': self.model_name, 'message': f'Unexpected response: {response[:100]}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


if __name__ == "__main__":
    llm = BytezLLM()
    print(llm.health_check())