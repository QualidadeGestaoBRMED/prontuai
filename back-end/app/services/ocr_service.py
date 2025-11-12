import os
# Set environment variable for PyTorch memory management
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import tempfile
from docling.document_converter import DocumentConverter
import torch
import re
import json
from openai import OpenAI
from typing import Dict, Any, List, Optional
import logging
import uuid
from datetime import datetime
import time

# AWS Textract imports (para migração do OCR)
import boto3
from botocore.exceptions import ClientError
from PyPDF2 import PdfReader, PdfWriter

from app.core.config import settings

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
    - Blocks tipo LINE são convertidos em linhas de texto
    - Texto curto em maiúsculas (≤ 4 palavras) vira header markdown (##)
    - Preserva padrões UF/CPF para detecção via regex
    """
    lines = []

    for block in textract_response.get('Blocks', []):
        if block['BlockType'] == 'LINE':
            text = block['Text'].strip()

            if not text:
                continue

            # Detectar possíveis headers de exames:
            # - Texto curto (até 4 palavras)
            # - Maioria em maiúsculas (pelo menos 50% dos caracteres alfabéticos)
            words = text.split()
            if len(words) <= 4:
                alpha_chars = [c for c in text if c.isalpha()]
                upper_chars = [c for c in text if c.isupper()]

                # Se pelo menos 50% das letras são maiúsculas, considerar como header
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


def aguardar_job_textract(job_id: str, max_attempts: int = 60, sleep_seconds: int = 2) -> str:
    """
    Aguarda a conclusão de um job do Textract (StartDocumentTextDetection).

    Args:
        job_id: ID do job retornado por start_document_text_detection
        max_attempts: Número máximo de tentativas (padrão: 60 = 2 minutos)
        sleep_seconds: Segundos entre cada verificação

    Returns:
        str: Status final do job ('SUCCEEDED', 'FAILED', etc)

    Raises:
        TimeoutError: Se o job não completar no tempo máximo
        ClientError: Se houver erro ao consultar status
    """
    logger.info(f"[OCR] Aguardando conclusão do job Textract: {job_id}")

    for attempt in range(1, max_attempts + 1):
        try:
            response = textract_client.get_document_text_detection(JobId=job_id)
            status = response['JobStatus']

            logger.debug(f"[OCR] Tentativa {attempt}/{max_attempts} - Status: {status}")

            if status == 'SUCCEEDED':
                logger.info(f"[OCR] Job concluído com sucesso após {attempt} tentativas")
                return status
            elif status == 'FAILED':
                status_message = response.get('StatusMessage', 'Sem detalhes')
                logger.error(f"[OCR] Job falhou: {status_message}")
                raise RuntimeError(f"Textract job falhou: {status_message}")
            elif status in ['IN_PROGRESS', 'PENDING']:
                time.sleep(sleep_seconds)
            else:
                logger.warning(f"[OCR] Status desconhecido: {status}")
                time.sleep(sleep_seconds)

        except ClientError as e:
            logger.error(f"[OCR] Erro ao verificar status do job: {e}")
            raise

    raise TimeoutError(f"Job Textract não completou após {max_attempts * sleep_seconds} segundos")


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


def processar_arquivo_textract(file_path: str) -> str:
    """
    Processa documento via AWS Textract usando API assíncrona (StartDocumentTextDetection).
    Fluxo: Upload S3 → Start Job → Aguardar → Coletar Resultados → Limpeza S3

    Args:
        file_path: Caminho absoluto do arquivo no disco

    Returns:
        str: Conteúdo em formato markdown

    Raises:
        ClientError: Erro na chamada da API Textract ou S3
        Exception: Outros erros inesperados
    """
    logger.info(f"[OCR] Processando com AWS Textract (Assíncrono) via S3: {file_path}")

    # Reparar PDF para garantir compatibilidade com Textract
    pdf_reparado = reparar_pdf_para_textract(file_path)
    arquivo_temporario_reparo = pdf_reparado != file_path

    # Gerar nome único para o arquivo no S3
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    original_filename = os.path.basename(file_path)
    s3_key = f"textract-temp/{timestamp}_{unique_id}_{original_filename}"

    bucket_name = settings.AWS_S3_BUCKET

    try:
        # 1. Upload do PDF para S3
        logger.info(f"[OCR] Fazendo upload para S3: s3://{bucket_name}/{s3_key}")

        with open(pdf_reparado, 'rb') as file_data:
            s3_client.upload_fileobj(file_data, bucket_name, s3_key)

        # Verificar tamanho do arquivo
        file_size = os.path.getsize(pdf_reparado)
        tamanho_mb = file_size / (1024 * 1024)
        logger.info(f"[OCR] Upload concluído. Tamanho: {tamanho_mb:.2f} MB")

        # 2. Iniciar processamento assíncrono com Textract
        logger.info(f"[OCR] Iniciando job Textract assíncrono (StartDocumentTextDetection)...")

        response = textract_client.start_document_text_detection(
            DocumentLocation={
                'S3Object': {
                    'Bucket': bucket_name,
                    'Name': s3_key
                }
            }
        )

        job_id = response['JobId']
        logger.info(f"[OCR] Job iniciado com sucesso. JobId: {job_id}")

        # 3. Aguardar conclusão do job
        aguardar_job_textract(job_id)

        # 4. Coletar resultados paginados
        all_blocks = coletar_resultados_textract(job_id)

        # 5. Converter blocos em markdown
        logger.info(f"[OCR] Convertendo {len(all_blocks)} blocos em markdown...")
        markdown = textract_to_markdown({'Blocks': all_blocks})

        logger.info(f"[OCR] Conversão concluída. Markdown gerado: {len(markdown)} caracteres")
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

        # Limpar arquivo temporário do reparo, se foi criado
        if arquivo_temporario_reparo and os.path.exists(pdf_reparado):
            try:
                os.remove(pdf_reparado)
                logger.debug(f"[OCR] Arquivo temporário reparado removido: {pdf_reparado}")
            except Exception as e:
                logger.warning(f"[OCR] Não foi possível remover arquivo temporário: {e}")


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
        return data
    except json.JSONDecodeError:
        return {"exames": [], "erro": "Falha ao decodificar o JSON da resposta da IA."}
    except Exception as e:
        return {"exames": [], "erro": f"Ocorreu um erro inesperado: {e}"}

def extrair_cpf_regex(markdown: str) -> str:
    # Tenta encontrar o padrão UF/CPF primeiro (ex: CE/12345678900)
    uf_cpf_match = re.search(r'\b[A-Z]{2}/(\d{11})\b', markdown)
    if uf_cpf_match:
        return uf_cpf_match.group(1)

    # Fallback: tenta encontrar qualquer CPF de 11 dígitos
    generic_cpf_match = re.search(r'\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b', markdown)
    if generic_cpf_match:
        return re.sub(r'\D', '', generic_cpf_match.group(0))
    return None

async def ocr_pipeline(file, salvar_markdown=True) -> Dict[str, Any]:
    """
    Pipeline completo: processa arquivo, extrai info, aplica fallbacks, salva markdown.

    Suporta dois motores de OCR via feature toggle (USE_TEXTRACT):
    - Textract (AWS): quando USE_TEXTRACT=true
    - Docling (local): quando USE_TEXTRACT=false (padrão)
    """
    logger.info(f"[OCR] Iniciando pipeline OCR para arquivo: {file.filename}")

    # Determinar qual motor usar
    usar_textract = settings.USE_TEXTRACT and textract_client is not None
    motor_ocr = "AWS Textract" if usar_textract else "Docling (local)"
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
            markdown = processar_arquivo_textract(temp_path)
        else:
            markdown = processar_arquivo_docling(temp_path)

        logger.info(f"[OCR] Conversão concluída. Markdown gerado: {len(markdown)} caracteres")
    finally:
        os.remove(temp_path) # Garante que o arquivo temporário seja removido

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
    logger.info(f"[OCR] CPF extraído: {cpf_extraido if cpf_extraido else 'Nenhum CPF encontrado'}")

    # Extrair exames via IA
    logger.info("[OCR] Iniciando extração de exames via OpenAI GPT...")
    exames_info = extrair_exames_ia(markdown)
    exames_extraidos = exames_info.get("exames", [])
    logger.info(f"[OCR] Exames extraídos: {len(exames_extraidos)} encontrados - {exames_extraidos}")

    info = {
        "cpf": cpf_extraido,
        "exames": exames_extraidos,
        "markdown_content": markdown # Adiciona o markdown para o orquestrador usar
    }

    if "erro" in exames_info:
        info["erro"] = exames_info["erro"]

    if caminho_md:
        info["markdown_salvo_em"] = caminho_md

    # Libera memória da GPU após cada processamento (apenas para Docling)
    if not usar_textract and torch.cuda.is_available():
        torch.cuda.empty_cache()
        logger.info(f"[OCR] Memória GPU liberada (Docling)")

    logger.info(f"[OCR] Pipeline OCR concluído para: {file.filename}")

    return info

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