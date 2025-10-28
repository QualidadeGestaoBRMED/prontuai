import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    BRMED_USERNAME = os.getenv("BRMED_USERNAME")
    BRMED_PASSWORD = os.getenv("BRMED_PASSWORD")
    MODELO_GPT = os.getenv("MODELO_GPT", "gpt-4o-mini")
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")
    # Configurações do FAQ
    CAMINHO_INDEX_FAQ = os.getenv("CAMINHO_INDEX_FAQ", "data/faq_index.faiss")
    CAMINHO_DADOS_FAQ = os.getenv("CAMINHO_DADOS_FAQ", "data/faq_data.pkl")
    MODELO_EMBEDDING = os.getenv("MODELO_EMBEDDING", "text-embedding-3-large")
    K_VIZINHOS_FAQ = int(os.getenv("K_VIZINHOS_FAQ", 2))
    MAX_DISTANCIA_FAQ = float(os.getenv("MAX_DISTANCIA_FAQ", 1.0))

settings = Settings() 