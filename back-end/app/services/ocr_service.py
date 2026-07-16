import os
import asyncio
import time
import tempfile
import io
import re
import json
import unicodedata
import shutil
import subprocess
from openai import OpenAI
from typing import Dict, Any, List, Optional, Callable
import logging
import uuid
from datetime import datetime
import time
import math
import threading
from weakref import WeakKeyDictionary

# Importações do AWS Textract (para migração do OCR)
import boto3
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from PyPDF2 import PdfReader, PdfWriter

# Importações condicionais do Docling/PyTorch (apenas se USE_TEXTRACT=false)
try:
    # Define variável de ambiente para gerenciamento de memória do PyTorch
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    from docling.document_converter import DocumentConverter
    import torch
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    DocumentConverter = None
    torch = None

from app.core.config import settings
from app.services.patient_name_extractor import extract_patient_name_from_markdown
from app.core import metrics
from app.core.pii import mask_cpf, mask_identifier

logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Inicializar clientes AWS (Textract + S3) quando USE_TEXTRACT=true
textract_client = None
s3_client = None
if settings.USE_TEXTRACT:
    try:
        textract_client = boto3.client(
            'textract',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        s3_client = boto3.client(
            's3',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        logger.info("[OCR] Clientes AWS Textract e S3 inicializados com sucesso")
    except Exception as e:
        logger.error(f"[OCR] Erro ao inicializar clientes AWS: {e}")
        logger.warning("[OCR] Fallback para Docling será usado")

# Prompt detalhado para LLM
MODELO_GPT = settings.MODELO_GPT

# Prompt detalhado para LLM
PROMPT_EXTRAIR_EXAMES = """
Você é um assistente de extração de dados altamente preciso.
Sua tarefa é extrair a lista de nomes de exames de um texto.
Considere como exame qualquer linha que contenha uma lista clara de exames ou procedimentos realizados, linhas no formato 'NOME DO EXAME - DATA',
ou qualquer header do tipo '## NOME DO EXAME'. Extraia o nome do exame do header, ignorando o prefixo '##' e espaços.
Nesses casos, extraia apenas o nome antes do hífen como exame.
Se o texto não contiver uma lista clara de exames ou procedimentos, retorne uma lista vazia.
Não infira exames a partir de menções genéricas como 'exame de sangue'.
Ignore nomes de empresas, marcas, logos ou setores (ex: "BR MED", "SAUDE CORPORATIVA").
Responda APENAS com um objeto JSON válido, sem nenhum texto adicional antes ou depois.
O formato do JSON deve ser: {"exames": ["<exame1>", "<exame2>"]}.
Se nenhum exame for encontrado, use uma lista vazia [] para a chave "exames".
Não invente exames e ignore informações irrelevantes.
Retorne os nomes dos exames em caixa alta.
"""

PROMPT_EXTRAIR_CPF = """
Você é um assistente de extração de dados altamente preciso.
Sua tarefa é extrair o CPF (apenas números, sem pontuação) de um texto.
ATENÇÃO: Se houver um CPF imediatamente após uma sigla de UF (por exemplo, CE/12345678909, SP/12345678901, etc),
você DEVE priorizar e retornar esse CPF, ignorando outros CPFs que possam aparecer no texto.
Se houver mais de um padrão UF/CPF, retorne o primeiro que aparecer.
Se não houver nenhum CPF após UF, aí sim retorne o primeiro CPF de 11 dígitos encontrado.
Responda APENAS com um objeto JSON válido, sem nenhum texto adicional antes ou depois.
O formato do JSON deve ser: {"cpf": "<cpf_extraido>"}.
Se o CPF não for encontrado, use o valor null para a chave "cpf".
"""

NON_EXAM_TERMS = {
    "BR MED",
    "BRMED",
    "SAUDE CORPORATIVA",
    "SAUDE",
    "CORPORATIVA",
    "BR MED SAUDE CORPORATIVA",
    "FICHA MEDICA",
    "FICHA MEDICA PERIODICO",
}

def normalizar_texto(texto: str) -> str:
    texto_normalizado = unicodedata.normalize("NFKD", texto)
    texto_normalizado = "".join(
        c for c in texto_normalizado if not unicodedata.combining(c)
    )
    texto_normalizado = re.sub(r"\s+", " ", texto_normalizado).strip().upper()
    return texto_normalizado

def filtrar_exames(exames: List[str]) -> List[str]:
    filtrados = []
    vistos = set()
    for exame in exames:
        if not isinstance(exame, str):
            continue
        normalizado = normalizar_texto(exame)
        if not normalizado:
            continue
        if normalizado in NON_EXAM_TERMS:
            continue
        if re.search(r"\bBR\s*MED\b", normalizado):
            continue
        if "SAUDE CORPORATIVA" in normalizado:
            continue
        if normalizado in vistos:
            continue
        vistos.add(normalizado)
        filtrados.append(exame)
    return filtrados

def extrair_cpf_ia(markdown: str) -> str:
    """Extrai CPF do markdown usando LLM."""
    user_prompt = f"""Texto:\n{markdown}"""
    try:
        response = client.chat.completions.create(
            model=MODELO_GPT,
            messages=[
                {"role": "system", "content": PROMPT_EXTRAIR_CPF},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("cpf")
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"Erro ao extrair CPF via IA: {e}")
        return None


def processar_arquivo_docling(file) -> str:
    """Processa o arquivo com Docling e retorna o markdown extraído."""
    if not DOCLING_AVAILABLE:
        raise ImportError(
            "Docling não está instalado. "
            "Para usar Docling OCR, instale: pip install docling torch torchvision. "
            "Ou configure USE_TEXTRACT=true no .env para usar AWS Textract."
        )

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption

    # Configurações otimizadas para velocidade
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True  # Habilita OCR
    pipeline_options.do_table_structure = False  # Desabilita detecção de tabelas (mais rápido)
    pipeline_options.table_structure_options.do_cell_matching = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    resultado = converter.convert(file)
    markdown = resultado.document.export_to_markdown()
    return markdown


def textract_to_markdown(textract_response: dict) -> str:
    """
    Converte resposta JSON do AWS Textract em formato markdown.
    Preserva formato compatível com a lógica de extração existente (regex CPF + LLM exames).

    Args:
        textract_response: Resposta completa do detect_document_text()

    Returns:
        str: Texto em formato markdown compatível com o pipeline atual

    Estratégia de conversão:
    - Blocos do tipo LINE são convertidos em linhas de texto
    - Texto curto em maiúsculas (≤ 4 palavras) se torna cabeçalho markdown (##)
    - Preserva padrões UF/CPF para detecção via regex
    """
    lines = []

    for block in textract_response.get('Blocks', []):
        if block['BlockType'] == 'LINE':
            text = block['Text'].strip()

            if not text:
                continue

            # Detectar possíveis cabeçalhos de exames:
            # - Texto curto (até 4 palavras)
            # - Maioria em maiúsculas (pelo menos 50% dos caracteres alfabéticos)
            words = text.split()
            if len(words) <= 4:
                alpha_chars = [c for c in text if c.isalpha()]
                upper_chars = [c for c in text if c.isupper()]

                # Se pelo menos 50% das letras são maiúsculas, considerar como cabeçalho
                if alpha_chars and len(upper_chars) / len(alpha_chars) >= 0.5:
                    lines.append(f"\n## {text}\n")
                    continue

            # Texto normal
            lines.append(text)

    markdown = '\n'.join(lines)
    return markdown


def reparar_pdf_para_textract(file_path: str) -> str:
    """
    Repara e reescreve PDF para garantir compatibilidade com AWS Textract.
    Remove proteções, criptografia e reescreve em formato padrão.

    Args:
        file_path: Caminho do PDF original

    Returns:
        str: Caminho do PDF reparado (arquivo temporário)
    """
    try:
        logger.info(f"[OCR] Reparando PDF para compatibilidade Textract: {file_path}")

        # Ler o PDF original
        reader = PdfReader(file_path)
        writer = PdfWriter()

        # Copiar todas as páginas para um novo PDF limpo
        for page_num, page in enumerate(reader.pages):
            writer.add_page(page)
            logger.debug(f"[OCR] Página {page_num + 1}/{len(reader.pages)} processada")

        # Criar arquivo temporário para o PDF reparado
        fd, temp_repaired_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)

        # Escrever PDF reparado
        with open(temp_repaired_path, 'wb') as output_file:
            writer.write(output_file)

        logger.info(f"[OCR] PDF reparado salvo em: {temp_repaired_path}")
        return temp_repaired_path

    except Exception as e:
        logger.error(f"[OCR] Erro ao reparar PDF: {e}")
        # Se falhar, retorna o original
        logger.warning(f"[OCR] Usando PDF original sem reparo")
        return file_path


def _pagina_tem_imagem(page, depth: int = 0) -> bool:
    if depth > 2:
        return False
    try:
        resources = page.get("/Resources") if hasattr(page, "get") else None
        if resources is None:
            resources = page if isinstance(page, dict) else {}
        if "/XObject" not in resources:
            resources = resources.get("/Resources") if isinstance(resources, dict) else resources
            if resources is None:
                resources = {}
        xobject = resources.get("/XObject") or {}
        for obj in xobject.values():
            try:
                resolved = obj.get_object() if hasattr(obj, "get_object") else obj
                subtype = resolved.get("/Subtype")
                if subtype == "/Image":
                    return True
                if subtype == "/Form":
                    form_resources = resolved.get("/Resources") or {}
                    if form_resources.get("/XObject"):
                        if _pagina_tem_imagem(form_resources, depth + 1):
                            return True
            except Exception:
                continue
    except Exception:
        return False
    return False

def detectar_documento_digitalizado(file_path: str) -> bool:
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        if total_pages == 0:
            return False

        max_pages = max(1, min(total_pages, settings.TEXTRACT_SCAN_DETECT_PAGES))
        texto_total = 0
        paginas_com_imagem = 0

        for idx in range(max_pages):
            page = reader.pages[idx]
            texto = page.extract_text() or ""
            texto_total += len(texto.strip())
            if _pagina_tem_imagem(page):
                paginas_com_imagem += 1

        avg_chars = texto_total / max_pages if max_pages else 0
        image_ratio = paginas_com_imagem / max_pages if max_pages else 0

        logger.info(
            f"[OCR] Heurística PDF: páginas={max_pages}, chars_medio={avg_chars:.1f}, imagens_ratio={image_ratio:.2f}"
        )

        if avg_chars < settings.TEXTRACT_SCAN_DETECT_MIN_CHARS_PER_PAGE:
            return True
        return image_ratio >= settings.TEXTRACT_SCAN_DETECT_MIN_IMAGE_RATIO
    except Exception as e:
        logger.warning(f"[OCR] Falha ao detectar documento digitalizado: {e}")
        return False

def otimizar_pdf_para_textract(file_path: str) -> str:
    """
    Tenta reduzir o tamanho do PDF para acelerar o Textract.
    Usa Ghostscript se disponivel. Se nao houver, retorna o original.
    """
    if not settings.TEXTRACT_PREPROCESS_PDF:
        return file_path

    try:
        tamanho_mb = os.path.getsize(file_path) / (1024 * 1024)
    except OSError:
        return file_path

    mode = settings.TEXTRACT_PREPROCESS_MODE
    is_scanned = False
    if mode == "auto":
        is_scanned = detectar_documento_digitalizado(file_path)
    elif mode == "scanned":
        is_scanned = True
    elif mode == "digital":
        is_scanned = False

    max_mb = settings.TEXTRACT_PREPROCESS_MAX_MB_SCANNED if is_scanned else settings.TEXTRACT_PREPROCESS_MAX_MB_DIGITAL
    gs_quality = settings.TEXTRACT_GS_PDFSETTINGS_SCANNED if is_scanned else settings.TEXTRACT_GS_PDFSETTINGS_DIGITAL

    if is_scanned and settings.TEXTRACT_PREPROCESS_SKIP_SCANNED:
        logger.info("[OCR] Documento escaneado detectado. Pulando compressao para evitar perda.")
        return file_path

    if tamanho_mb <= max_mb:
        return file_path

    gs_path = shutil.which("gs")
    if not gs_path:
        logger.info("[OCR] Ghostscript nao encontrado, pulando otimizacao do PDF")
        return file_path

    fd, temp_optimized_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)

    logger.info(
        f"[OCR] Preprocessamento PDF: mode={mode}, scanned={is_scanned}, "
        f"max_mb={max_mb}, gs={gs_quality}"
    )
    cmd = [
        gs_path,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS=/{gs_quality}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={temp_optimized_path}",
        file_path,
    ]

    try:
        subprocess.run(cmd, check=True)
        otimizado_mb = os.path.getsize(temp_optimized_path) / (1024 * 1024)
        savings_mb = tamanho_mb - otimizado_mb
        savings_ratio = savings_mb / tamanho_mb if tamanho_mb else 0
        logger.info(
            f"[OCR] PDF otimizado via Ghostscript: {tamanho_mb:.2f} MB -> {otimizado_mb:.2f} MB"
        )
        if (
            savings_mb < settings.TEXTRACT_GS_MIN_SAVINGS_MB
            or savings_ratio < settings.TEXTRACT_GS_MIN_SAVINGS_RATIO
        ):
            logger.info("[OCR] Ganho pequeno na compressao. Mantendo PDF original.")
            if os.path.exists(temp_optimized_path):
                os.remove(temp_optimized_path)
            return file_path
        return temp_optimized_path
    except Exception as e:
        logger.warning(f"[OCR] Falha ao otimizar PDF: {e}")
        if os.path.exists(temp_optimized_path):
            os.remove(temp_optimized_path)
        return file_path


def aguardar_job_textract(
    job_id: str,
    max_attempts: int = 180,
    max_wait_seconds: int = 30,
    progress_hook: Optional[Callable[[str], None]] = None,
    heartbeat_seconds: int = 15,
    status_hook: Optional[Callable[[str], None]] = None
) -> str:
    """
    Aguarda a conclusão de um job do Textract (StartDocumentTextDetection).
    Usa polling adaptativo: começa com 1s e aumenta gradualmente até 5s.

    Args:
        job_id: ID do job retornado por start_document_text_detection
        max_attempts: Número máximo de tentativas (padrão: 180)
        max_wait_seconds: Tempo máximo total de espera (padrão: 30s)

    Returns:
        str: Status final do job ('SUCCEEDED', 'FAILED', etc)

    Raises:
        TimeoutError: Se o job não completar no tempo máximo
        ClientError: Se houver erro ao consultar status
    """
    logger.info(f"[OCR] Aguardando conclusão do job Textract: {job_id}")

    if textract_client is None:
        raise RuntimeError("Cliente Textract não foi inicializado")

    start_time = time.monotonic()
    last_heartbeat = start_time
    if progress_hook:
        progress_hook("OCR em andamento (job iniciado)")
    for attempt in range(1, max_attempts + 1):
        elapsed = time.monotonic() - start_time
        if elapsed >= max_wait_seconds:
            raise TimeoutError(
                f"Job Textract não completou após {max_wait_seconds} segundos"
            )

        try:
            response = textract_client.get_document_text_detection(JobId=job_id)
            status = response['JobStatus']

            logger.debug(f"[OCR] Tentativa {attempt}/{max_attempts} - Status: {status}")
            if status_hook:
                status_hook(status)

            if status == 'SUCCEEDED':
                logger.info(f"[OCR] Job concluído com sucesso após {attempt} tentativas")
                return status
            elif status == 'FAILED':
                status_message = response.get('StatusMessage', 'Sem detalhes')
                logger.error(f"[OCR] Job falhou: {status_message}")
                raise RuntimeError(f"Textract job falhou: {status_message}")
            elif status in ['IN_PROGRESS', 'PENDING']:
                # Polling adaptativo: 1s nas primeiras 10 tentativas, depois aumenta até 5s
                if attempt <= 10:
                    sleep_time = 1
                elif attempt <= 30:
                    sleep_time = 2
                else:
                    sleep_time = 5

                logger.debug(f"[OCR] Job ainda em progresso, aguardando {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                logger.warning(f"[OCR] Status desconhecido: {status}, aguardando 2s...")
                time.sleep(2)

            if progress_hook and (time.monotonic() - last_heartbeat) >= heartbeat_seconds:
                progress_hook(f"OCR em andamento ({status.lower()})...")
                last_heartbeat = time.monotonic()

        except ClientError as e:
            logger.error(f"[OCR] Erro ao verificar status do job: {e}")
            raise
        except Exception as e:
            logger.error(f"[OCR] Erro inesperado ao verificar status: {e}")
            raise

    raise TimeoutError(f"Job Textract não completou após {max_attempts} tentativas")


def aguardar_job_textract_shadow(
    job_ids: List[str],
    max_wait_seconds: int,
    progress_hook: Optional[Callable[[str], None]] = None,
    heartbeat_seconds: int = 15,
) -> str:
    """
    Aguarda a conclusão de qualquer job Textract em paralelo (shadow jobs).
    Retorna o job_id que concluir com sucesso primeiro.
    """
    if textract_client is None:
        raise RuntimeError("Cliente Textract não foi inicializado")

    start_times = {job_id: time.monotonic() for job_id in job_ids}
    last_heartbeat = time.monotonic()
    last_errors: dict[str, str] = {}
    status_map: dict[str, str] = {job_id: "IN_PROGRESS" for job_id in job_ids}
    attempt = 0

    while True:
        attempt += 1
        now = time.monotonic()
        active_jobs = []

        for job_id in job_ids:
            status = status_map.get(job_id, "IN_PROGRESS")
            if status in {"SUCCEEDED", "FAILED", "TIMEOUT"}:
                continue
            if now - start_times[job_id] >= max_wait_seconds:
                status_map[job_id] = "TIMEOUT"
                continue
            active_jobs.append(job_id)

        if not active_jobs:
            if any(status == "FAILED" for status in status_map.values()):
                error_msg = next(iter(last_errors.values()), "Textract job falhou.")
                raise RuntimeError(error_msg)
            raise TimeoutError(
                f"Job Textract não completou após {max_wait_seconds} segundos"
            )

        for job_id in active_jobs:
            try:
                response = textract_client.get_document_text_detection(JobId=job_id)
                status = response["JobStatus"]
                status_map[job_id] = status
                logger.debug(
                    f"[OCR] Shadow job {job_id} tentativa {attempt} - Status: {status}"
                )

                if status == "SUCCEEDED":
                    logger.info(f"[OCR] Shadow job concluído com sucesso: {job_id}")
                    return job_id
                if status == "FAILED":
                    status_message = response.get("StatusMessage", "Sem detalhes")
                    last_errors[job_id] = f"Textract job falhou: {status_message}"
                    logger.error(f"[OCR] Shadow job falhou: {status_message}")
            except ClientError as e:
                last_errors[job_id] = str(e)
                logger.error(f"[OCR] Erro ao verificar status do shadow job: {e}")
                status_map[job_id] = "FAILED"

        if progress_hook and (time.monotonic() - last_heartbeat) >= heartbeat_seconds:
            progress_hook("OCR em andamento (shadow jobs)...")
            last_heartbeat = time.monotonic()

        # Polling adaptativo: 1s nas primeiras 10 tentativas, depois aumenta até 5s
        if attempt <= 10:
            sleep_time = 1
        elif attempt <= 30:
            sleep_time = 2
        else:
            sleep_time = 5
        time.sleep(sleep_time)


def calcular_timeout_textract(tamanho_mb: float) -> int:
    base = settings.TEXTRACT_MIN_WAIT_SECONDS
    per_mb = settings.TEXTRACT_WAIT_SECONDS_PER_MB
    max_wait = settings.TEXTRACT_MAX_WAIT_SECONDS
    if per_mb <= 0:
        per_mb = base
    if base <= 0:
        base = 60
    estimado = max(base, int(math.ceil(tamanho_mb * per_mb)))
    return min(estimado, max_wait)


def coletar_resultados_textract(job_id: str) -> List[dict]:
    """
    Coleta todos os blocos de texto de um job Textract paginado.

    Args:
        job_id: ID do job concluído

    Returns:
        List[dict]: Lista de todos os blocos de texto
    """
    logger.info(f"[OCR] Coletando resultados do job: {job_id}")

    all_blocks = []
    next_token = None
    page = 1

    while True:
        try:
            if next_token:
                response = textract_client.get_document_text_detection(
                    JobId=job_id,
                    NextToken=next_token
                )
            else:
                response = textract_client.get_document_text_detection(JobId=job_id)

            blocks = response.get('Blocks', [])
            all_blocks.extend(blocks)

            logger.debug(f"[OCR] Página {page}: {len(blocks)} blocos coletados")

            next_token = response.get('NextToken')
            if not next_token:
                break

            page += 1

        except ClientError as e:
            logger.error(f"[OCR] Erro ao coletar resultados: {e}")
            raise

    logger.info(f"[OCR] Total de blocos coletados: {len(all_blocks)}")
    return all_blocks


def aguardar_job_textract_com_backoff(job_id: str, max_wait_seconds: int) -> str:
    """
    Usa o waiter do boto3 com backoff apropriado para Textract.
    """
    if textract_client is None:
        raise RuntimeError("Cliente Textract não foi inicializado")
    waiter = textract_client.get_waiter("document_text_detection_complete")
    delay = 5
    max_attempts = max(1, int(max_wait_seconds / delay))
    waiter.wait(
        JobId=job_id,
        WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts}
    )
    return "SUCCEEDED"


_TEXTRACT_RETRYABLE_ERROR_CODES = {
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
    "Throttling",
    "TooManyRequestsException",
    "RequestTimeout",
    "InternalServerError",
}


def _is_retryable_textract_error(error: Exception) -> bool:
    if isinstance(error, (EndpointConnectionError, BotoCoreError, TimeoutError)):
        return True
    if isinstance(error, ClientError):
        error_code = error.response.get("Error", {}).get("Code", "")
        return error_code in _TEXTRACT_RETRYABLE_ERROR_CODES
    return False


def _detect_document_text_with_retry(document_bytes: bytes, context: str) -> dict:
    if textract_client is None:
        raise RuntimeError("Cliente Textract não foi inicializado")

    max_retries = max(0, settings.TEXTRACT_SYNC_PAGE_RETRY_MAX)
    base_delay = max(0.0, settings.TEXTRACT_SYNC_RETRY_BASE_DELAY_SECONDS)
    attempts = max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                logger.info("[OCR] Retry Textract síncrono %s/%s (%s)", attempt, attempts, context)
            return textract_client.detect_document_text(
                Document={"Bytes": document_bytes}
            )
        except ClientError as error:
            last_error = error
            error_info = error.response.get("Error", {})
            error_code = error_info.get("Code", "Unknown")
            error_message = error_info.get("Message", str(error))
            logger.warning(
                "[OCR] Textract síncrono falhou (%s) tentativa %s/%s code=%s message=%s",
                context,
                attempt,
                attempts,
                error_code,
                error_message,
            )
            if attempt >= attempts or not _is_retryable_textract_error(error):
                raise
        except (EndpointConnectionError, BotoCoreError, TimeoutError) as error:
            last_error = error
            logger.warning(
                "[OCR] Textract síncrono falhou (%s) tentativa %s/%s type=%s message=%s",
                context,
                attempt,
                attempts,
                type(error).__name__,
                error,
            )
            if attempt >= attempts:
                raise

        sleep_seconds = base_delay * (2 ** (attempt - 1))
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    if last_error:
        raise last_error
    raise RuntimeError(f"Textract síncrono falhou sem erro explícito ({context})")


def processar_arquivo_textract_sincrono(file_path: str) -> str:
    """
    Processa documento via AWS Textract usando API síncrona (DetectDocumentText).
    Muito mais rápido (15-30s) mas limitado a arquivos de até 5MB.

    Args:
        file_path: Caminho absoluto do arquivo no disco

    Returns:
        str: Conteúdo em formato markdown

    Raises:
        ClientError: Erro na chamada da API Textract
        Exception: Outros erros inesperados
    """
    logger.info(f"[OCR] Processando com AWS Textract (Síncrono): {file_path}")

    try:
        # Reparar PDF para melhorar compatibilidade com Textract
        pdf_reparado = reparar_pdf_para_textract(file_path)
        arquivo_temporario_reparo = pdf_reparado != file_path

        # Otimizar PDF para reduzir tamanho (se necessario)
        pdf_otimizado = otimizar_pdf_para_textract(pdf_reparado)
        arquivo_temporario_otimizado = pdf_otimizado != pdf_reparado

        # Ler o arquivo em bytes
        with open(pdf_otimizado, 'rb') as document:
            document_bytes = document.read()

        file_size = len(document_bytes)
        tamanho_mb = file_size / (1024 * 1024)
        logger.info(f"[OCR] Tamanho do arquivo: {tamanho_mb:.2f} MB")

        # Validar tamanho (limite de 5MB para API síncrona)
        if file_size > 5 * 1024 * 1024:
            raise ValueError(
                f"Arquivo muito grande para API síncrona ({tamanho_mb:.2f} MB). Use API assíncrona."
            )

        # Chamar API síncrona do Textract
        logger.info(f"[OCR] Chamando detect_document_text (síncrono)...")
        response = _detect_document_text_with_retry(
            document_bytes,
            context=f"arquivo={os.path.basename(file_path)} size={tamanho_mb:.2f}MB",
        )

        logger.info(f"[OCR] Resposta recebida. Total de blocos: {len(response.get('Blocks', []))}")

        # Converter para markdown
        markdown = textract_to_markdown(response)
        logger.info(f"[OCR] Conversão concluída. Markdown gerado: {len(markdown)} caracteres")

        return markdown

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"[OCR] Erro AWS [{error_code}]: {error_message}")
        raise
    except FileNotFoundError as e:
        logger.error(f"[OCR] Arquivo não encontrado: {file_path}")
        raise
    except Exception as e:
        logger.error(f"[OCR] Erro inesperado ao processar com Textract síncrono: {e}")
        raise
    finally:
        if 'arquivo_temporario_otimizado' in locals() and arquivo_temporario_otimizado:
            if os.path.exists(pdf_otimizado):
                try:
                    os.remove(pdf_otimizado)
                except Exception as e:
                    logger.warning(f"[OCR] Nao foi possivel remover arquivo temporario: {e}")

        if 'arquivo_temporario_reparo' in locals() and arquivo_temporario_reparo:
            if os.path.exists(pdf_reparado):
                try:
                    os.remove(pdf_reparado)
                except Exception as e:
                    logger.warning(f"[OCR] Nao foi possivel remover arquivo temporario: {e}")


def processar_pdf_textract_sincrono_por_pagina(
    file_path: str,
    progress_hook: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Processa PDF página a página usando Textract síncrono.
    Útil para evitar fila do Textract assíncrono.
    """
    logger.info(f"[OCR] Processando PDF por pagina com Textract (Síncrono): {file_path}")

    # Reparar PDF para melhorar compatibilidade com Textract
    pdf_reparado = reparar_pdf_para_textract(file_path)
    arquivo_temporario_reparo = pdf_reparado != file_path

    # Otimizar PDF para reduzir tamanho (se necessario)
    pdf_otimizado = otimizar_pdf_para_textract(pdf_reparado)
    arquivo_temporario_otimizado = pdf_otimizado != pdf_reparado

    markdown_parts: list[str] = []
    try:
        reader = PdfReader(pdf_otimizado)
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError("PDF sem páginas")

        logger.info(f"[OCR] PDF possui {total_pages} pagina(s)")

        for idx, page in enumerate(reader.pages, start=1):
            if progress_hook:
                progress_hook(f"Processando documento com OCR... Página {idx}/{total_pages}")
            writer = PdfWriter()
            writer.add_page(page)
            buffer = io.BytesIO()
            writer.write(buffer)
            page_bytes = buffer.getvalue()
            buffer.close()

            file_size = len(page_bytes)
            tamanho_mb = file_size / (1024 * 1024)
            if file_size > 5 * 1024 * 1024:
                raise ValueError(
                    f"Pagina {idx} muito grande para Textract síncrono ({tamanho_mb:.2f} MB)."
                )

            logger.info(f"[OCR] Textract síncrono página {idx}/{total_pages} ({tamanho_mb:.2f} MB)")
            response = _detect_document_text_with_retry(
                page_bytes,
                context=f"pagina={idx}/{total_pages} size={tamanho_mb:.2f}MB",
            )
            markdown_parts.append(textract_to_markdown(response))
            if settings.TEXTRACT_SYNC_PAGE_DELAY_SECONDS > 0 and idx < total_pages:
                time.sleep(settings.TEXTRACT_SYNC_PAGE_DELAY_SECONDS)

        markdown = "\n\n".join(markdown_parts)
        logger.info(f"[OCR] PDF por página concluído. Markdown: {len(markdown)} caracteres")
        return markdown
    except Exception:
        raise
    finally:
        if 'arquivo_temporario_otimizado' in locals() and arquivo_temporario_otimizado:
            if os.path.exists(pdf_otimizado):
                try:
                    os.remove(pdf_otimizado)
                except Exception as e:
                    logger.warning(f"[OCR] Nao foi possivel remover arquivo temporario: {e}")

        if 'arquivo_temporario_reparo' in locals() and arquivo_temporario_reparo:
            if os.path.exists(pdf_reparado):
                try:
                    os.remove(pdf_reparado)
                except Exception as e:
                    logger.warning(f"[OCR] Nao foi possivel remover arquivo temporario: {e}")


def processar_arquivo_textract(
    file_path: str,
    progress_hook: Optional[Callable[[str], None]] = None
) -> str:
    """
    Processa documento via AWS Textract usando API assíncrona (StartDocumentTextDetection).
    Fluxo: Repara PDF → Upload S3 → Start Job → Aguardar → Coletar Resultados → Limpeza S3

    Args:
        file_path: Caminho absoluto do arquivo no disco

    Returns:
        str: Conteúdo em formato markdown

    Raises:
        ClientError: Erro na chamada da API Textract ou S3
        Exception: Outros erros inesperados
    """
    logger.info(f"[OCR] Processando com AWS Textract (Assíncrono) via S3: {file_path}")
    start_total = time.perf_counter()

    # Reparar PDF para garantir compatibilidade com Textract
    pdf_reparado = reparar_pdf_para_textract(file_path)
    arquivo_temporario_reparo = pdf_reparado != file_path

    # Otimizar PDF para reduzir tamanho (se necessario)
    pdf_otimizado = otimizar_pdf_para_textract(pdf_reparado)
    arquivo_temporario_otimizado = pdf_otimizado != pdf_reparado

    # Gerar nome único para o arquivo no S3
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    original_filename = os.path.basename(file_path)
    s3_key = f"textract-temp/{timestamp}_{unique_id}_{original_filename}"

    bucket_name = settings.AWS_S3_BUCKET

    try:
        # 1. Upload do PDF reparado para S3
        t_upload = time.perf_counter()
        logger.info(f"[OCR] Fazendo upload para S3: s3://{bucket_name}/{s3_key}")

        with open(pdf_otimizado, 'rb') as file_data:
            s3_client.upload_fileobj(file_data, bucket_name, s3_key)

        # Verificar tamanho do arquivo
        file_size = os.path.getsize(pdf_otimizado)
        tamanho_mb = file_size / (1024 * 1024)
        logger.info(f"[OCR] Upload concluído. Tamanho: {tamanho_mb:.2f} MB (em {time.perf_counter() - t_upload:.2f}s)")

        # 2. Iniciar processamento assíncrono com Textract (com retry em timeout)
        max_wait_seconds = calcular_timeout_textract(tamanho_mb)
        if settings.TEXTRACT_FALLBACK_TO_LOCAL:
            max_wait_seconds = min(max_wait_seconds, settings.TEXTRACT_FALLBACK_AFTER_SECONDS)
        logger.info(f"[OCR] Timeout maximo do Textract: {max_wait_seconds}s")

        max_retries = settings.TEXTRACT_RETRY_MAX if settings.TEXTRACT_RETRY_ON_TIMEOUT else 0
        attempt = 0
        last_status = {"value": "IN_PROGRESS"}

        while True:
            attempt += 1
            t_start = time.perf_counter()
            logger.info(
                f"[OCR] Iniciando job Textract assíncrono (StartDocumentTextDetection)... tentativa {attempt}"
            )

            response = textract_client.start_document_text_detection(
                DocumentLocation={
                    "S3Object": {
                        "Bucket": bucket_name,
                        "Name": s3_key,
                    }
                }
            )

            job_id = response["JobId"]
            logger.info(
                f"[OCR] Job iniciado com sucesso. JobId: {job_id} (em {time.perf_counter() - t_start:.2f}s)"
            )

            # 3. Aguardar conclusão do job
            t_wait = time.perf_counter()
            last_status["value"] = "IN_PROGRESS"
            job_ids = [job_id]

            if settings.TEXTRACT_SHADOW_JOB_ENABLED:
                shadow_delay = max(settings.TEXTRACT_SHADOW_JOB_DELAY_SECONDS, 0)
                if shadow_delay > 0:
                    logger.info(f"[OCR] Agendando shadow job em {shadow_delay}s")
                    if progress_hook:
                        progress_hook("OCR em andamento (shadow job agendado)...")
                    time.sleep(shadow_delay)
                logger.info("[OCR] Iniciando shadow job Textract")
                shadow_response = textract_client.start_document_text_detection(
                    DocumentLocation={
                        "S3Object": {
                            "Bucket": bucket_name,
                            "Name": s3_key,
                        }
                    }
                )
                shadow_job_id = shadow_response["JobId"]
                job_ids.append(shadow_job_id)
                logger.info(f"[OCR] Shadow job iniciado. JobId: {shadow_job_id}")

            try:
                winner_job_id = aguardar_job_textract_shadow(
                    job_ids,
                    max_wait_seconds=max_wait_seconds,
                    progress_hook=progress_hook,
                )
                job_id = winner_job_id
                logger.info(f"[OCR] Shadow jobs concluídos. Vencedor: {job_id}")
                last_status["value"] = "SUCCEEDED"
            except TimeoutError:
                if attempt <= max_retries:
                    logger.warning(
                        f"[OCR] Timeout Textract na tentativa {attempt}/{max_retries + 1}. Reenviando job."
                    )
                    continue
                extra_wait = settings.TEXTRACT_EXTRA_WAIT_SECONDS
                remaining = max(settings.TEXTRACT_MAX_WAIT_SECONDS - max_wait_seconds, 0)
                extra_wait = min(extra_wait, remaining)
                if extra_wait > 0:
                    logger.warning(
                        f"[OCR] Timeout atingido, estendendo espera por mais {extra_wait}s"
                    )
                    winner_job_id = aguardar_job_textract_shadow(
                        job_ids,
                        max_wait_seconds=extra_wait,
                        progress_hook=progress_hook,
                    )
                    job_id = winner_job_id
                    logger.info(f"[OCR] Shadow jobs concluídos. Vencedor: {job_id}")
                    last_status["value"] = "SUCCEEDED"
                else:
                    raise

            if last_status["value"] in ["IN_PROGRESS", "PENDING"]:
                logger.info("[OCR] Status ainda pendente, usando waiter do boto3")
                aguardar_job_textract_com_backoff(job_id, settings.TEXTRACT_MAX_WAIT_SECONDS)
            logger.info(
                f"[OCR] Job Textract finalizado em {time.perf_counter() - t_wait:.2f}s (status={last_status['value']})"
            )
            break

        # 4. Coletar resultados paginados
        t_collect = time.perf_counter()
        all_blocks = coletar_resultados_textract(job_id)
        logger.info(f"[OCR] Resultados coletados em {time.perf_counter() - t_collect:.2f}s")

        # 5. Converter blocos em markdown
        t_conv = time.perf_counter()
        logger.info(f"[OCR] Convertendo {len(all_blocks)} blocos em markdown...")
        markdown = textract_to_markdown({'Blocks': all_blocks})

        logger.info(f"[OCR] Conversão concluída em {time.perf_counter() - t_conv:.2f}s. Markdown gerado: {len(markdown)} caracteres")
        return markdown

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"[OCR] Erro AWS [{error_code}]: {error_message}")
        raise
    except TimeoutError as e:
        logger.error(f"[OCR] Timeout ao aguardar job Textract: {e}")
        raise
    except FileNotFoundError as e:
        logger.error(f"[OCR] Arquivo não encontrado: {file_path}")
        raise
    except Exception as e:
        logger.error(f"[OCR] Erro inesperado ao processar com Textract: {e}")
        raise
    finally:
        # 6. Limpeza: remover arquivo do S3
        try:
            logger.info(f"[OCR] Removendo arquivo do S3: {s3_key}")
            s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
            logger.info(f"[OCR] Arquivo removido do S3 com sucesso")
        except Exception as e:
            logger.warning(f"[OCR] Erro ao remover arquivo do S3: {e}")

        # 7. Limpeza: remover arquivo temporário reparado
        if arquivo_temporario_otimizado and os.path.exists(pdf_otimizado):
            try:
                os.remove(pdf_otimizado)
                logger.debug(f"[OCR] Arquivo temporario otimizado removido: {pdf_otimizado}")
            except Exception as e:
                logger.warning(f"[OCR] Nao foi possivel remover arquivo temporario: {e}")

        if arquivo_temporario_reparo and os.path.exists(pdf_reparado):
            try:
                os.remove(pdf_reparado)
                logger.debug(f"[OCR] Arquivo temporário reparado removido: {pdf_reparado}")
            except Exception as e:
                logger.warning(f"[OCR] Não foi possível remover arquivo temporário: {e}")
        logger.info(f"[OCR] Fluxo Textract assíncrono completo em {time.perf_counter() - start_total:.2f}s")


def extrair_exames_ia(markdown: str) -> Dict[str, Any]:
    """Extrai apenas exames do markdown usando LLM."""
    user_prompt = f"""Texto:
{markdown}"""
    try:
        response = client.chat.completions.create(
            model=MODELO_GPT,
            messages=[
                {"role": "system", "content": PROMPT_EXTRAIR_EXAMES},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        if "exames" not in data:
            return {"exames": [], "erro": "Resposta da IA não contém a chave 'exames'."}
        data["exames"] = filtrar_exames(data.get("exames", []))
        return data
    except json.JSONDecodeError:
        return {"exames": [], "erro": "Falha ao decodificar o JSON da resposta da IA."}
    except Exception as e:
        return {"exames": [], "erro": f"Ocorreu um erro inesperado: {e}"}

def _digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _is_valid_cpf(value: str | None) -> bool:
    digits = _digits_only(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False

    numbers = [int(digit) for digit in digits]
    for index in (9, 10):
        checksum = sum(numbers[pos] * (index + 1 - pos) for pos in range(index))
        expected = (checksum * 10) % 11
        if expected == 10:
            expected = 0
        if numbers[index] != expected:
            return False
    return True


def _is_valid_cnpj(value: str | None) -> bool:
    digits = _digits_only(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def _check_digit(numbers: list[int], weights: list[int]) -> int:
        total = sum(number * weight for number, weight in zip(numbers, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    numbers = [int(digit) for digit in digits]
    first = _check_digit(numbers[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = _check_digit(numbers[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return numbers[12] == first and numbers[13] == second


def _line_mentions_any(line: str, labels: tuple[str, ...]) -> bool:
    upper = line.upper()
    return any(label in upper for label in labels)


def extrair_cpf_regex(markdown: str) -> str:
    if not markdown:
        return None

    # 1) Padrão UF/CPF (ex: CE/12345678900) com tolerância a espaços/pontuação
    uf_cpf_match = re.search(r"\b[A-Z]{2}\s*/\s*([0-9.\-\s]{11,20})\b", markdown)
    if uf_cpf_match:
        digits = _digits_only(uf_cpf_match.group(1))
        if _is_valid_cpf(digits):
            return digits

    # 2) Linhas contendo "CPF" com tolerância a separadores variados
    cpf_label_match = re.search(r"CPF[^0-9]{0,10}([0-9.\-\s]{11,20})", markdown, flags=re.IGNORECASE)
    if cpf_label_match:
        digits = _digits_only(cpf_label_match.group(1))
        if _is_valid_cpf(digits):
            return digits

    # 3) Fallback por linha: pega 11 dígitos em linhas que citam CPF
    for line in markdown.splitlines():
        if "CPF" not in line.upper():
            continue
        digits = _digits_only(line)
        if _is_valid_cpf(digits):
            return digits

    # 4) Padrão genérico, mas nunca em linhas de passaporte/CNPJ.
    for line in markdown.splitlines():
        if _line_mentions_any(line, ("PASSAPORTE", "PASSPORT", "CNPJ")):
            continue
        generic_cpf_match = re.search(r"\b\d{3}[\.\s-]{0,5}\d{3}[\.\s-]{0,5}\d{3}[\.\s-]{0,5}\d{2}\b", line)
        if generic_cpf_match:
            digits = _digits_only(generic_cpf_match.group(0))
            if _is_valid_cpf(digits):
                return digits

    return None


def extrair_cnpj_regex(markdown: str) -> str:
    if not markdown:
        return None

    cnpj_label_match = re.search(r"CNPJ[^0-9]{0,10}([0-9.\-/\s]{14,24})", markdown, flags=re.IGNORECASE)
    if cnpj_label_match:
        digits = _digits_only(cnpj_label_match.group(1))
        if _is_valid_cnpj(digits):
            return digits

    for line in markdown.splitlines():
        if _line_mentions_any(line, ("PASSAPORTE", "PASSPORT", "CPF")):
            continue
        generic_cnpj_match = re.search(r"\b\d{2}[.\s-]?\d{3}[.\s-]?\d{3}[/\s-]?\d{4}[-\s]?\d{2}\b", line)
        if generic_cnpj_match:
            digits = _digits_only(generic_cnpj_match.group(0))
            if _is_valid_cnpj(digits):
                return digits

    return None


def extrair_passaporte_regex(markdown: str) -> str:
    if not markdown:
        return None

    passport_label_match = re.search(
        r"(?:PASSAPORTE\s*/\s*PASSPORT|PASSPORT\s*/\s*PASSAPORTE|PASSAPORTE|PASSPORT)\s*[:\-]?\s*([A-Z0-9]{5,20})",
        markdown,
        flags=re.IGNORECASE,
    )
    if passport_label_match:
        return passport_label_match.group(1).upper()

    return None


def _same_identifier_value(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    left_clean = re.sub(r"[^A-Z0-9]", "", str(left).upper())
    right_clean = re.sub(r"[^A-Z0-9]", "", str(right).upper())
    return bool(left_clean and right_clean and left_clean == right_clean)


_OCR_SEMAPHORES_BY_LOOP: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = WeakKeyDictionary()
_OCR_SEMAPHORES_LOCK = threading.Lock()


def _get_ocr_semaphore() -> asyncio.Semaphore | None:
    concurrency = int(getattr(settings, "OCR_CONCURRENCY", 0) or 0)
    if concurrency <= 0:
        return None

    loop = asyncio.get_running_loop()
    with _OCR_SEMAPHORES_LOCK:
        semaphore = _OCR_SEMAPHORES_BY_LOOP.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(concurrency)
            _OCR_SEMAPHORES_BY_LOOP[loop] = semaphore
        return semaphore


async def _ocr_pipeline_impl(file, salvar_markdown=True, progress_hook: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Pipeline completo: processa arquivo, extrai info, aplica fallbacks, salva markdown.

    Suporta dois motores de OCR via feature toggle (USE_TEXTRACT):
    - Textract (AWS): quando USE_TEXTRACT=true
    - Docling (local): quando USE_TEXTRACT=false (padrão)
    """
    logger.info(f"[OCR] Iniciando pipeline OCR para arquivo: {file.filename}")
    start_total = time.perf_counter()

    # Determinar qual motor usar
    usar_textract = settings.USE_TEXTRACT and textract_client is not None
    motor_ocr = "AWS Textract" if usar_textract else "Docling (local)"
    motor_metrica = "textract" if usar_textract else "docling"
    logger.info(f"[OCR] Motor selecionado: {motor_ocr}")

    # Corrige o manuseio de UploadFile do FastAPI
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as temp:
        content = await file.read()  # Lê o conteúdo do UploadFile de forma assíncrona
        temp.write(content)    # Escreve o conteúdo no arquivo temporário
        temp_path = temp.name

    logger.info(f"[OCR] Iniciando conversão com {motor_ocr} para: {file.filename}")

    try:
        # Feature Toggle: escolher motor de OCR
        if usar_textract:
            file_size = os.path.getsize(temp_path)
            try:
                if file.filename.lower().endswith(".pdf"):
                    markdown = await asyncio.to_thread(
                        processar_pdf_textract_sincrono_por_pagina,
                        temp_path,
                        progress_hook
                    )
                elif file_size <= 5 * 1024 * 1024:
                    markdown = await asyncio.to_thread(
                        processar_arquivo_textract_sincrono,
                        temp_path
                    )
                else:
                    markdown = await asyncio.to_thread(
                        processar_arquivo_textract,
                        temp_path,
                        progress_hook
                    )
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code')
                if error_code == 'UnsupportedDocumentException':
                    logger.warning(
                        "[OCR] Documento nao suportado no modo sincrono, usando assincrono"
                    )
                    markdown = await asyncio.to_thread(
                        processar_arquivo_textract,
                        temp_path,
                        progress_hook
                    )
                else:
                    raise
            except ValueError as e:
                logger.warning(f"[OCR] {e} Fallback para modo assincrono.")
                markdown = await asyncio.to_thread(
                    processar_arquivo_textract,
                    temp_path,
                    progress_hook
                )
            except TimeoutError as e:
                metrics.TEXTRACT_TIMEOUT.inc()
                if settings.TEXTRACT_FALLBACK_TO_LOCAL:
                    logger.warning(f"[OCR] {e}. Fallback para OCR local (Docling).")
                    if progress_hook:
                        progress_hook("Fila Textract, usando OCR local.")
                    metrics.OCR_FALLBACK_DOCLING.inc()
                    motor_metrica = "docling_fallback"
                    markdown = await asyncio.to_thread(
                        processar_arquivo_docling,
                        temp_path
                    )
                else:
                    raise
            except (EndpointConnectionError, BotoCoreError) as e:
                if settings.TEXTRACT_FALLBACK_TO_LOCAL:
                    logger.warning(f"[OCR] Falha de conexão Textract: {e}. Fallback para OCR local (Docling).")
                    if progress_hook:
                        progress_hook("Falha temporária no Textract, usando OCR local.")
                    metrics.OCR_FALLBACK_DOCLING.inc()
                    motor_metrica = "docling_fallback"
                    markdown = await asyncio.to_thread(
                        processar_arquivo_docling,
                        temp_path
                    )
                else:
                    raise
        else:
            markdown = await asyncio.to_thread(
                processar_arquivo_docling,
                temp_path
            )

        logger.info(f"[OCR] Conversão concluída. Markdown gerado: {len(markdown)} caracteres")
    finally:
        # Remover arquivo temporário original
        if os.path.exists(temp_path):
            os.remove(temp_path)
        metrics.OCR_DURACAO.labels(motor=motor_metrica).observe(time.perf_counter() - start_total)
        logger.info(f"[OCR] Pipeline OCR finalizado em {time.perf_counter() - start_total:.2f}s")

    # Salvar markdown
    caminho_md = None
    if salvar_markdown:
        os.makedirs("ocr_resultados", exist_ok=True)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_nome = os.path.splitext(file.filename)[0]
        caminho_md = f"ocr_resultados/ocr_{base_nome}_{timestamp}.md"
        with open(caminho_md, "w", encoding="utf-8") as f:
            f.write(markdown)
        logger.info(f"[OCR] Markdown salvo em: {caminho_md}")

    # Extrair CPF localmente
    logger.info("[OCR] Extraindo CPF via regex...")
    cpf_extraido = extrair_cpf_regex(markdown)
    if not cpf_extraido and markdown:
        logger.info("[OCR] CPF não encontrado via regex. Tentando extração via IA...")
        try:
            cpf_extraido = await asyncio.to_thread(extrair_cpf_ia, markdown)
        except Exception as e:
            logger.warning(f"[OCR] Falha ao extrair CPF via IA: {e}")
    logger.info(f"[OCR] CPF extraído: {mask_cpf(cpf_extraido) if cpf_extraido else 'Nenhum CPF encontrado'}")

    # Extrair passaporte e CNPJ via regex
    passaporte_extraido = extrair_passaporte_regex(markdown)
    if _same_identifier_value(cpf_extraido, passaporte_extraido):
        logger.info("[OCR] Valor extraído como CPF também aparece como passaporte; usando como passaporte.")
        cpf_extraido = None
    cnpj_extraido = extrair_cnpj_regex(markdown)
    logger.info(f"[OCR] Passaporte extraído: {mask_identifier(passaporte_extraido) if passaporte_extraido else 'Nenhum passaporte encontrado'}")
    logger.info(f"[OCR] CNPJ extraído: {mask_identifier(cnpj_extraido) if cnpj_extraido else 'Nenhum CNPJ encontrado'}")

    patient_name = extract_patient_name_from_markdown(markdown)
    logger.info(
        f"[OCR] Nome do paciente extraído: {patient_name if patient_name else 'Nenhum nome encontrado'}"
    )

    # Extrair exames via IA
    logger.info("[OCR] Iniciando extração de exames via OpenAI GPT...")
    exames_info = await asyncio.to_thread(extrair_exames_ia, markdown)
    exames_extraidos = exames_info.get("exames", [])
    logger.info(f"[OCR] Exames extraídos: {len(exames_extraidos)} encontrados - {exames_extraidos}")

    info = {
        "cpf": cpf_extraido,
        "passaporte": passaporte_extraido,
        "passport": passaporte_extraido,  # alias para compatibilidade com integração externa
        "cnpj": cnpj_extraido,
        "patient_name": patient_name,
        "exames": exames_extraidos,
        "markdown_content": markdown,  # Adiciona o markdown para o orquestrador usar
    }

    if "erro" in exames_info:
        info["erro"] = exames_info["erro"]

    if caminho_md:
        info["markdown_salvo_em"] = caminho_md

    # Libera memória da GPU após cada processamento (apenas para Docling)
    if not usar_textract and torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()
        logger.info(f"[OCR] Memória GPU liberada (Docling)")

    logger.info(f"[OCR] Pipeline OCR concluído para: {file.filename}")

    return info


async def ocr_pipeline(file, salvar_markdown=True, progress_hook: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Wrapper com limite de concorrência para OCR.
    """
    semaphore = _get_ocr_semaphore()
    if semaphore is None:
        return await _ocr_pipeline_impl(file, salvar_markdown=salvar_markdown, progress_hook=progress_hook)
    async with semaphore:
        return await _ocr_pipeline_impl(file, salvar_markdown=salvar_markdown, progress_hook=progress_hook)

PROMPT_EXTRAIR_TODOS_CPFS = """
Você é um assistente de extração de dados altamente preciso.
Sua tarefa é extrair TODOS os CPFs (apenas números, sem pontuação) de um texto.
Retorne uma lista de CPFs encontrados.
Responda APENAS com um objeto JSON válido, sem nenhum texto adicional antes ou depois.
O formato do JSON deve ser: {\"cpfs\": [\"<cpf1>\", \"<cpf2>\"]}.
Se nenhum CPF for encontrado, use uma lista vazia [] para a chave \"cpfs\".
"""

async def extrair_todos_cpfs_ia(markdown: str, exclude_cpf: Optional[str] = None) -> List[str]:
    """Extrai todos os CPFs do markdown usando LLM, opcionalmente excluindo um CPF."""
    user_prompt = f"""Texto:\n{markdown}"""
    if exclude_cpf:
        user_prompt += f"\nExcluir CPF: {exclude_cpf}"

    try:
        response = client.chat.completions.create(
            model=MODELO_GPT,
            messages=[
                {"role": "system", "content": PROMPT_EXTRAIR_TODOS_CPFS},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        cpfs = [cpf for cpf in data.get("cpfs", []) if cpf != exclude_cpf]
        return cpfs
    except json.JSONDecodeError:
        return []
    except Exception as e:
        print(f"Erro ao extrair todos os CPFs via IA: {e}")
        return [] 
