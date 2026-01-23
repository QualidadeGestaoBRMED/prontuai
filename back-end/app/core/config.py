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

    # AWS Textract Configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
    TEXTRACT_MIN_WAIT_SECONDS = int(os.getenv("TEXTRACT_MIN_WAIT_SECONDS", 180))
    TEXTRACT_MAX_WAIT_SECONDS = int(os.getenv("TEXTRACT_MAX_WAIT_SECONDS", 300))
    TEXTRACT_WAIT_SECONDS_PER_MB = int(os.getenv("TEXTRACT_WAIT_SECONDS_PER_MB", 60))
    TEXTRACT_EXTRA_WAIT_SECONDS = int(os.getenv("TEXTRACT_EXTRA_WAIT_SECONDS", 120))
    TEXTRACT_PREPROCESS_PDF = os.getenv("TEXTRACT_PREPROCESS_PDF", "true").lower() == "true"
    TEXTRACT_PREPROCESS_MAX_MB = float(os.getenv("TEXTRACT_PREPROCESS_MAX_MB", 1.0))
    TEXTRACT_GS_PDFSETTINGS = os.getenv("TEXTRACT_GS_PDFSETTINGS", "ebook")
    TEXTRACT_FALLBACK_TO_LOCAL = os.getenv("TEXTRACT_FALLBACK_TO_LOCAL", "true").lower() == "true"
    TEXTRACT_FALLBACK_AFTER_SECONDS = int(os.getenv("TEXTRACT_FALLBACK_AFTER_SECONDS", 90))

    # Feature Toggle: OCR Engine Selection
    USE_TEXTRACT = os.getenv("USE_TEXTRACT", "false").lower() == "true"

    # JWT Authentication
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production-please")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", 24))

    # CORS Configuration
    # Aceita múltiplas origens separadas por vírgula na variável de ambiente
    ALLOWED_ORIGINS = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost,http://localhost:3000,https://prontuai.grupobrmed.com.br"
    ).split(",")

settings = Settings() 
