from openai import AsyncOpenAI
from app.core.config import settings

# Centralized OpenAI client
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
