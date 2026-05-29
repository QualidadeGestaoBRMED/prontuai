import hashlib
import hmac
import json
import logging
import os
import re
import unicodedata
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = os.getenv("MODELO_EMBEDDING", "text-embedding-3-large")
ARTIFACT_SIGNING_KEY = os.getenv("ARTIFACT_SIGNING_KEY")

MAX_ROWS = int(os.getenv("EXAM_SIMILARITY_MAX_ROWS", "5000"))
MAX_TERM_LENGTH = int(os.getenv("EXAM_SIMILARITY_MAX_TERM_LENGTH", "180"))
MAX_SIMILARS_PER_ROW = int(os.getenv("EXAM_SIMILARITY_MAX_SIMILARS_PER_ROW", "40"))

SUSPICIOUS_PATTERNS = (
    "ignore previous",
    "system:",
    "assistant:",
    "```",
    "<script",
    "</script>",
    "http://",
    "https://",
)

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY não encontrada.")
if not ARTIFACT_SIGNING_KEY:
    raise ValueError("ARTIFACT_SIGNING_KEY não encontrada.")

client = OpenAI(api_key=OPENAI_API_KEY)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
SIMILAR_EXAMS_CSV_PATH = os.path.join(PROJECT_ROOT, "exames_similares_final.csv")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INDEX_PATH = os.path.join(DATA_DIR, "exam_similarity_index.faiss")
DATA_PATH = os.path.join(DATA_DIR, "exam_similarity_data.json")
INDEX_HMAC_PATH = f"{INDEX_PATH}.hmac"
DATA_HMAC_PATH = f"{DATA_PATH}.hmac"


class SimilarExamRow(BaseModel):
    exame_principal: str = Field(min_length=1, max_length=MAX_TERM_LENGTH)
    similares: list[str]

    @field_validator("exame_principal")
    @classmethod
    def clean_principal(cls, value: str) -> str:
        return _sanitize_term(value)

    @field_validator("similares")
    @classmethod
    def clean_similares(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for term in value[:MAX_SIMILARS_PER_ROW]:
            cleaned_term = _sanitize_term(term)
            if cleaned_term:
                cleaned.append(cleaned_term)
        if not cleaned:
            raise ValueError("Linha sem similares válidos após sanitização.")
        return cleaned


def normalizar_exame(exame: str) -> str:
    nfkd = unicodedata.normalize("NFKD", exame)
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).upper().strip()


def _sanitize_term(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for marker in SUSPICIOUS_PATTERNS:
        if marker in text.lower():
            text = text.lower().replace(marker, " ")
            text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_TERM_LENGTH]


def _write_atomic_text(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    os.chmod(target, 0o640)


def _sign_file(path: str, signature_path: str) -> None:
    digest = hmac.new(
        ARTIFACT_SIGNING_KEY.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    _write_atomic_text(signature_path, digest.hexdigest())


def _write_index_atomic(index: faiss.Index, path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    faiss.write_index(index, str(tmp))
    with open(tmp, "rb") as handle:
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    os.chmod(target, 0o640)


@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(5))
def gerar_embedding(texto: str) -> np.ndarray:
    try:
        resp = client.embeddings.create(input=[texto], model=EMBED_MODEL)
        return np.array(resp.data[0].embedding, dtype="float32")
    except Exception as exc:
        logger.error("Erro ao gerar embedding", extra={"error_type": type(exc).__name__})
        raise


def _load_and_validate_csv() -> list[SimilarExamRow]:
    try:
        df = pd.read_csv(SIMILAR_EXAMS_CSV_PATH, sep=",", engine="python")
    except FileNotFoundError:
        raise FileNotFoundError(f"Arquivo '{SIMILAR_EXAMS_CSV_PATH}' não encontrado.")

    if len(df) > MAX_ROWS:
        raise ValueError(f"CSV excede limite de {MAX_ROWS} linhas.")

    validated_rows: list[SimilarExamRow] = []
    for row_number, row in enumerate(df.itertuples(index=False), start=1):
        try:
            principal = getattr(row, "Exame", None) or getattr(row, "exame", "")
            similares_raw = getattr(row, "Similares", None) or getattr(row, "similares", "")
            similares = [s.strip() for s in str(similares_raw).split(",") if s.strip()]
            validated_rows.append(
                SimilarExamRow(exame_principal=str(principal), similares=similares)
            )
        except ValidationError as exc:
            logger.warning(
                "Linha inválida no CSV de similaridade",
                extra={"row_number": row_number, "error": str(exc)},
            )
        except Exception as exc:
            logger.warning(
                "Falha ao processar linha do CSV",
                extra={"row_number": row_number, "error_type": type(exc).__name__},
            )
    return validated_rows


def criar_indice_similaridade_exames() -> None:
    logger.info("Iniciando criação do índice de similaridade de exames...")
    rows = _load_and_validate_csv()
    if not rows:
        raise ValueError("Nenhuma linha válida encontrada para gerar índice de similaridade.")

    embeddings = []
    exames_data = []

    for row_number, item in enumerate(rows, start=1):
        texto_para_embedding = (
            f"Exame: {normalizar_exame(item.exame_principal)}. "
            f"Similares: {', '.join([normalizar_exame(s) for s in item.similares])}"
        )
        try:
            embedding = gerar_embedding(texto_para_embedding)
            embeddings.append(embedding)
            exames_data.append(
                {
                    "exame_principal": item.exame_principal,
                    "similares": item.similares,
                    "texto_embedding": texto_para_embedding,
                }
            )
        except Exception:
            logger.warning("Embedding não gerado para linha", extra={"row_number": row_number})

    if not embeddings:
        raise ValueError("Nenhum embedding foi gerado. Abortando.")

    embeddings_matrix = np.vstack(embeddings)
    dimensao = embeddings_matrix.shape[1]
    index = faiss.IndexFlatL2(dimensao)
    index.add(embeddings_matrix)

    os.makedirs(DATA_DIR, exist_ok=True)
    _write_index_atomic(index, INDEX_PATH)

    data_json = json.dumps(exames_data, ensure_ascii=False)
    _write_atomic_text(DATA_PATH, data_json)
    _sign_file(INDEX_PATH, INDEX_HMAC_PATH)
    _sign_file(DATA_PATH, DATA_HMAC_PATH)

    logger.info(
        "Índice e payload de similaridade gerados com sucesso. total_exames=%d dimensao=%d",
        len(exames_data),
        dimensao,
    )


if __name__ == "__main__":
    criar_indice_similaridade_exames()
