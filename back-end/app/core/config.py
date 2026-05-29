import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")).lower()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    BRMED_USERNAME = os.getenv("BRMED_USERNAME")
    BRMED_PASSWORD = os.getenv("BRMED_PASSWORD")
    PRONTUAI_API_BASE_URL = os.getenv("PRONTUAI_API_BASE_URL", "https://api.grupobrmed.com.br")
    PRONTUAI_SERVICE_TOKEN = os.getenv("PRONTUAI_SERVICE_TOKEN")
    PRONTUAI_CLIENT_NAME = os.getenv("PRONTUAI_CLIENT_NAME")
    PRONTUAI_API_TIMEOUT_SECONDS = float(os.getenv("PRONTUAI_API_TIMEOUT_SECONDS", "20"))
    USE_PRONTUAI_PATIENTS_EXAMS = os.getenv("USE_PRONTUAI_PATIENTS_EXAMS", "false").lower() == "true"
    USE_PRONTUAI_API_FALLBACK_RPA = os.getenv("USE_PRONTUAI_API_FALLBACK_RPA", "true").lower() == "true"
    MODELO_GPT = os.getenv("MODELO_GPT", "gpt-4o-mini")
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.getenv("LOG_FORMAT", "plain")
    AUDIT_LOG_ENABLED = os.getenv("AUDIT_LOG_ENABLED", "true").lower() == "true"
    AUDIT_LOG_ALL_REQUESTS = os.getenv("AUDIT_LOG_ALL_REQUESTS", "false").lower() == "true"
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
    TEXTRACT_RETRY_ON_TIMEOUT = os.getenv("TEXTRACT_RETRY_ON_TIMEOUT", "true").lower() == "true"
    TEXTRACT_RETRY_MAX = int(os.getenv("TEXTRACT_RETRY_MAX", 1))
    TEXTRACT_SHADOW_JOB_ENABLED = os.getenv("TEXTRACT_SHADOW_JOB_ENABLED", "true").lower() == "true"
    TEXTRACT_SHADOW_JOB_DELAY_SECONDS = int(os.getenv("TEXTRACT_SHADOW_JOB_DELAY_SECONDS", 0))
    TEXTRACT_PREPROCESS_MODE = os.getenv("TEXTRACT_PREPROCESS_MODE", "auto").lower()
    TEXTRACT_PREPROCESS_MAX_MB_SCANNED = float(os.getenv("TEXTRACT_PREPROCESS_MAX_MB_SCANNED", 4.0))
    TEXTRACT_PREPROCESS_MAX_MB_DIGITAL = float(os.getenv("TEXTRACT_PREPROCESS_MAX_MB_DIGITAL", 1.0))
    TEXTRACT_GS_PDFSETTINGS_SCANNED = os.getenv("TEXTRACT_GS_PDFSETTINGS_SCANNED", "ebook")
    TEXTRACT_GS_PDFSETTINGS_DIGITAL = os.getenv("TEXTRACT_GS_PDFSETTINGS_DIGITAL", "screen")
    TEXTRACT_SCAN_DETECT_PAGES = int(os.getenv("TEXTRACT_SCAN_DETECT_PAGES", 3))
    TEXTRACT_SCAN_DETECT_MIN_CHARS_PER_PAGE = int(os.getenv("TEXTRACT_SCAN_DETECT_MIN_CHARS_PER_PAGE", 40))
    TEXTRACT_SCAN_DETECT_MIN_IMAGE_RATIO = float(os.getenv("TEXTRACT_SCAN_DETECT_MIN_IMAGE_RATIO", 0.5))
    TEXTRACT_PREPROCESS_SKIP_SCANNED = os.getenv("TEXTRACT_PREPROCESS_SKIP_SCANNED", "true").lower() == "true"
    TEXTRACT_GS_MIN_SAVINGS_MB = float(os.getenv("TEXTRACT_GS_MIN_SAVINGS_MB", 0.2))
    TEXTRACT_GS_MIN_SAVINGS_RATIO = float(os.getenv("TEXTRACT_GS_MIN_SAVINGS_RATIO", 0.05))

    # Feature Toggle: OCR Engine Selection
    USE_TEXTRACT = os.getenv("USE_TEXTRACT", "false").lower() == "true"

    # BRMED RPA (Playwright) worker pool
    BRMED_CONSULT_ENABLED = os.getenv("BRMED_CONSULT_ENABLED", "true").lower() == "true"
    BRMED_RPA_WORKERS = int(os.getenv("BRMED_RPA_WORKERS", 1))
    BRMED_RPA_CONCURRENCY = int(os.getenv("BRMED_RPA_CONCURRENCY", 1))

    # Concurrency limits (0 = sem limite)
    OCR_CONCURRENCY = int(os.getenv("OCR_CONCURRENCY", 2))
    DOCUMENT_PROCESS_CONCURRENCY = int(os.getenv("DOCUMENT_PROCESS_CONCURRENCY", 2))

    # JWT Authentication
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", 2))
    JWT_ISSUER = os.getenv("JWT_ISSUER", "prontuai-backend")
    JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "prontuai-frontend")
    JWT_MIN_SECRET_LENGTH = int(os.getenv("JWT_MIN_SECRET_LENGTH", 32))
    DEV_AUTH_BYPASS = os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true"

    # Assinatura de artefatos RAG
    ARTIFACT_SIGNING_KEY = os.getenv("ARTIFACT_SIGNING_KEY")

    # CORS Configuration
    # Aceita múltiplas origens separadas por vírgula na variável de ambiente
    ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost,http://localhost:3000,https://prontuai.grupobrmed.com.br",
        ).split(",")
        if origin.strip()
    ]

    # Storage de documentos (para visualização local)
    DOCUMENT_STORAGE_DIR = os.getenv(
        "DOCUMENT_STORAGE_DIR",
        os.path.join(BASE_DIR, "data", "uploads"),
    )

    # Google Drive (upload após aprovação)
    GOOGLE_DRIVE_ENABLED = os.getenv("GOOGLE_DRIVE_ENABLED", "true").lower() == "true"
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    GOOGLE_DRIVE_CREDENTIALS_FILE = os.getenv("GOOGLE_DRIVE_CREDENTIALS_FILE")
    GOOGLE_DRIVE_CREDENTIALS_JSON = os.getenv("GOOGLE_DRIVE_CREDENTIALS_JSON")
    GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES = os.getenv("GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES", "true").lower() == "true"

settings = Settings() 
