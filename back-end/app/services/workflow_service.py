import os
import time
import re
from typing import Dict, Any, Optional, List
from fastapi import UploadFile
from app.services import ocr_service, brmed_service, validacao_service
from app.core.config import settings
import logging
import json
import asyncio
from openai import OpenAI
import faiss
import pickle
import numpy as np
from tenacity import retry, wait_exponential, stop_after_attempt
from datetime import datetime
import uuid
import csv

logger = logging.getLogger(__name__)

from app.core.clients import client

# Caminhos para o índice de similaridade de exames
logger.info(f"DEBUG: settings.BASE_DIR is {settings.BASE_DIR}")
EXAM_SIMILARITY_INDEX_PATH = os.path.join(settings.BASE_DIR, "data", "exam_similarity_index.faiss")
EXAM_SIMILARITY_DATA_PATH = os.path.join(settings.BASE_DIR, "data", "exam_similarity_data.pkl")
EXAM_SIMILARITY_CSV_PATH = os.path.join(settings.BASE_DIR, "exames_similares_final.csv")

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def gerar_embedding(texto: str) -> np.ndarray:
    """Gera embedding para um texto usando a API da OpenAI."""
    resp = None
    try:
        resp = await client.embeddings.create(
            input=[texto],
            model=settings.MODELO_EMBEDDING
        )
        return np.array(resp.data[0].embedding, dtype="float32").reshape(1, -1)
    except AttributeError as ae:
        logger.error(f"AttributeError ao processar embedding para '{texto[:50]}...': {ae}. Resposta completa: {resp}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar embedding para o texto: '{texto[:50]}...': {e}")
        raise

# Carrega o índice de similaridade de exames
try:
    exam_similarity_index = faiss.read_index(EXAM_SIMILARITY_INDEX_PATH)
    with open(EXAM_SIMILARITY_DATA_PATH, "rb") as f:
        exam_similarity_data = pickle.load(f)
    logger.info("Índice de similaridade de exames carregado com sucesso.")
except Exception as e:
    logger.error(f"Erro ao carregar o índice de similaridade de exames: {e}")
    exam_similarity_index = None
    exam_similarity_data = None

def _load_exam_similarity_csv() -> list[dict]:
    if not os.path.exists(EXAM_SIMILARITY_CSV_PATH):
        return []
    try:
        with open(EXAM_SIMILARITY_CSV_PATH, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            items = []
            for row in reader:
                principal = (row.get("Exame") or row.get("exame") or "").strip()
                similares_raw = (row.get("Similares") or row.get("similares") or "").strip()
                if not principal and not similares_raw:
                    continue
                similares = [s.strip() for s in similares_raw.split(",") if s.strip()]
                items.append({"exame_principal": principal, "similares": similares})
            return items
    except Exception as e:
        logger.error(f"Erro ao carregar CSV de similares: {e}")
        return []

EXAM_SIMILARITY_CSV_DATA = _load_exam_similarity_csv()

_PROCESSING_SEMAPHORE = None
if getattr(settings, "DOCUMENT_PROCESS_CONCURRENCY", 0) > 0:
    _PROCESSING_SEMAPHORE = asyncio.Semaphore(settings.DOCUMENT_PROCESS_CONCURRENCY)

def _normalizar_busca(texto: str) -> str:
    normalizado = ocr_service.normalizar_texto(texto)
    normalizado = re.sub(r"[^A-Z0-9 ]+", " ", normalizado)
    normalizado = re.sub(r"\s+", " ", normalizado).strip()
    return normalizado

def _build_master_exam_terms() -> set[str]:
    termos = set()
    data_sources = []
    if exam_similarity_data:
        data_sources.extend(exam_similarity_data)
    if EXAM_SIMILARITY_CSV_DATA:
        data_sources.extend(EXAM_SIMILARITY_CSV_DATA)
    if not data_sources:
        return termos
    for item in data_sources:
        principal = item.get("exame_principal")
        if principal:
            termos.add(_normalizar_busca(principal))
        for similar in item.get("similares") or []:
            termos.add(_normalizar_busca(similar))
    return termos

MASTER_EXAM_TERMS = _build_master_exam_terms()

def _build_synonym_map() -> Dict[str, set[str]]:
    synonym_map: Dict[str, set[str]] = {}
    data_sources = []
    if exam_similarity_data:
        data_sources.extend(exam_similarity_data)
    if EXAM_SIMILARITY_CSV_DATA:
        data_sources.extend(EXAM_SIMILARITY_CSV_DATA)
    if not data_sources:
        return synonym_map
    for item in data_sources:
        principal = item.get("exame_principal")
        similares = item.get("similares") or []
        termos = [principal] + list(similares) if principal else list(similares)
        termos_norm = {_normalizar_busca(t) for t in termos if t}
        for termo in termos_norm:
            if termo not in synonym_map:
                synonym_map[termo] = set()
            synonym_map[termo].update(termos_norm)
    return synonym_map

EXAM_SYNONYM_MAP = _build_synonym_map()

def _log_event(event: str, **payload: Any) -> None:
    try:
        logger.info("[WORKFLOW-EVENT] %s", json.dumps({"event": event, **payload}, ensure_ascii=False))
    except Exception:
        logger.info("[WORKFLOW-EVENT] %s | %s", event, payload)

def _extrair_linhas_markdown(markdown: str) -> list[tuple[str, str]]:
    linhas = []
    for linha in markdown.splitlines():
        linha_limpa = linha.strip()
        if not linha_limpa:
            continue
        linhas.append((linha_limpa, _normalizar_busca(linha_limpa)))
    return linhas

def _buscar_evidencias(termo: str, linhas: list[tuple[str, str]]) -> list[str]:
    if not termo:
        return []
    termo_norm = _normalizar_busca(termo)
    if not termo_norm:
        return []
    alvo = f" {termo_norm} "
    evidencias = []
    for original, normalizado in linhas:
        if alvo in f" {normalizado} ":
            evidencias.append(original)
        if len(evidencias) >= 3:
            break
    return evidencias

def _avaliar_campos(
    markdown: str,
    linhas: list[tuple[str, str]],
    patient_name: Optional[str] = None
) -> list[Dict[str, Any]]:
    checks = []

    def add_check(field: str, label: str, evidencias: list[str]):
        checks.append({
            "field": field,
            "label": label,
            "found": bool(evidencias),
            "evidence": evidencias,
        })

    cpf_regex = re.compile(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b|\b[A-Z]{2}/\d{11}\b")
    data_regex = re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{2,4}\b")
    crm_regex = re.compile(r"\bCRM\b|\bCRBM\b|\bCREMEC\b|\bCRO\b", re.IGNORECASE)

    evidencias_cpf = [linha for linha, _ in linhas if cpf_regex.search(linha)]
    evidencias_data = [linha for linha, _ in linhas if data_regex.search(linha)]
    evidencias_crm = [linha for linha, _ in linhas if crm_regex.search(linha)]
    evidencias_assinatura = [
        linha for linha, normalizado in linhas
        if "ASSINATURA" in normalizado or "ASSINADO" in normalizado or "CARIMBO" in normalizado
        or "RUBRICA" in normalizado or "___" in linha
    ]

    add_check("cpf", "CPF", evidencias_cpf[:3])
    if patient_name:
        add_check("nome_paciente", "Nome do paciente", _buscar_evidencias(patient_name, linhas))
    add_check("data", "Data", evidencias_data[:3])
    add_check("crm_medico", "CRM do medico", evidencias_crm[:3])
    add_check("assinatura", "Assinatura/Carimbo", evidencias_assinatura[:3])

    return checks

def _avaliar_qualidade(markdown: str, linhas: list[tuple[str, str]]) -> Dict[str, Any]:
    total_chars = len(markdown)
    total_lines = len(linhas)
    nonspace = sum(1 for c in markdown if not c.isspace())
    alpha = sum(1 for c in markdown if c.isalpha())
    digits = sum(1 for c in markdown if c.isdigit())
    unique_lines = len({linha for linha, _ in linhas})
    alpha_ratio = (alpha / nonspace) if nonspace else 0
    digit_ratio = (digits / nonspace) if nonspace else 0
    unique_ratio = (unique_lines / total_lines) if total_lines else 0

    score = 20
    if total_chars >= 500:
        score += 15
    if total_chars >= 1000:
        score += 15
    if total_lines >= 20:
        score += 10
    if alpha_ratio >= 0.55:
        score += 15
    if unique_ratio >= 0.6:
        score += 15
    if digit_ratio >= 0.05:
        score += 10

    score = max(0, min(100, score))

    return {
        "score": score,
        "total_chars": total_chars,
        "total_lines": total_lines,
        "alpha_ratio": round(alpha_ratio, 3),
        "digit_ratio": round(digit_ratio, 3),
        "unique_line_ratio": round(unique_ratio, 3),
    }

def _token_subset_match(a: str, b: str) -> bool:
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    return bool(a_tokens) and a_tokens.issubset(b_tokens)

def _tokens_relevantes(texto: str) -> set[str]:
    stopwords = {"DE", "DA", "DO", "DAS", "DOS", "E", "COM", "SEM", "PARA", "POR"}
    return {t for t in texto.split() if len(t) >= 3 and t not in stopwords}

def _token_overlap_match(a: str, b: str) -> bool:
    a_tokens = _tokens_relevantes(a)
    b_tokens = _tokens_relevantes(b)
    if not a_tokens or not b_tokens:
        return False
    overlap = a_tokens & b_tokens
    if not overlap:
        return False
    overlap_ratio = len(overlap) / len(a_tokens)
    max_len = max(len(t) for t in overlap)
    return overlap_ratio >= 0.75 or (overlap_ratio >= 0.5 and max_len >= 8)

def _match_ocr_exame(
    exame_brnet: str,
    exames_ocr: list[str],
    linhas: list[tuple[str, str]]
) -> Dict[str, Any]:
    norm_brnet = _normalizar_busca(exame_brnet)
    if not norm_brnet:
        return {"match_type": "invalido", "ocr_match": None, "evidence": []}

    for exame in exames_ocr:
        if _normalizar_busca(exame) == norm_brnet:
            return {
                "match_type": "exato",
                "ocr_match": exame,
                "evidence": _buscar_evidencias(exame, linhas)
            }

    synonyms = EXAM_SYNONYM_MAP.get(norm_brnet, set())
    if synonyms:
        for exame in exames_ocr:
            if _normalizar_busca(exame) in synonyms:
                return {
                    "match_type": "similar",
                    "ocr_match": exame,
                    "evidence": _buscar_evidencias(exame, linhas)
                }

    for exame in exames_ocr:
        if _token_subset_match(norm_brnet, _normalizar_busca(exame)):
            return {
                "match_type": "parcial",
                "ocr_match": exame,
                "evidence": _buscar_evidencias(exame, linhas)
            }

    for exame in exames_ocr:
        if _token_overlap_match(norm_brnet, _normalizar_busca(exame)):
            return {
                "match_type": "parcial",
                "ocr_match": exame,
                "evidence": _buscar_evidencias(exame, linhas)
            }

    return {
        "match_type": "inferido",
        "ocr_match": None,
        "evidence": _buscar_evidencias(exame_brnet, linhas)
    }

def _avaliar_confianca_exames(
    comparacao: list[Dict[str, Any]],
    exames_ocr: list[str],
    linhas: list[tuple[str, str]]
) -> list[Dict[str, Any]]:
    detalhes = []
    for item in comparacao:
        status = item.get("status")
        exame = item.get("exame")
        if not exame:
            continue
        if status == "extra_no_ocr":
            detalhes.append({
                "exame": exame,
                "status": status,
                "match_type": "extra",
                "ocr_match": exame,
                "evidence": _buscar_evidencias(exame, linhas),
                "justificativa": item.get("justificativa", "")
            })
            continue
        if status == "faltante":
            detalhes.append({
                "exame": exame,
                "status": status,
                "match_type": "ausente",
                "ocr_match": None,
                "evidence": _buscar_evidencias(exame, linhas),
                "justificativa": item.get("justificativa", "")
            })
            continue

        match_info = _match_ocr_exame(exame, exames_ocr, linhas)
        detalhes.append({
            "exame": exame,
            "status": status,
            "match_type": match_info["match_type"],
            "ocr_match": match_info["ocr_match"],
            "evidence": match_info["evidence"],
            "justificativa": item.get("justificativa", "")
        })
    return detalhes

def _filtrar_exames_ocr(
    exames_ocr: list[str],
    exames_brnet: list[str],
    markdown: str
) -> list[str]:
    exames_ocr = ocr_service.filtrar_exames(exames_ocr or [])
    if not exames_brnet:
        return exames_ocr

    brnet_norm_list = []
    brnet_norm_set = set()
    for exame in exames_brnet:
        normalizado = _normalizar_busca(exame)
        if not normalizado:
            continue
        brnet_norm_set.add(normalizado)
        brnet_norm_list.append((exame, normalizado))
    termos_validos = MASTER_EXAM_TERMS | brnet_norm_set

    filtrados = []
    vistos = set()
    for exame in exames_ocr or []:
        normalizado = _normalizar_busca(exame)
        if not normalizado:
            continue
        chave = normalizado
        if normalizado not in termos_validos:
            for _, brnet_norm in brnet_norm_list:
                if _token_subset_match(brnet_norm, normalizado) or _token_overlap_match(brnet_norm, normalizado):
                    chave = brnet_norm
                    break
            else:
                continue
        if chave in vistos:
            continue
        vistos.add(chave)
        filtrados.append(exame)

    if markdown:
        markdown_norm = f" {_normalizar_busca(markdown)} "
        linhas = _extrair_linhas_markdown(markdown)
        for exame in exames_brnet:
            normalizado = _normalizar_busca(exame)
            if not normalizado or normalizado in vistos:
                continue
            encontrou = f" {normalizado} " in markdown_norm
            if not encontrou:
                for _, linha_norm in linhas:
                    if _token_subset_match(normalizado, linha_norm) or _token_overlap_match(normalizado, linha_norm):
                        encontrou = True
                        break
            if encontrou:
                vistos.add(normalizado)
                filtrados.append(exame)

    return filtrados

async def comparar_exames_openai(exames_ocr: list[str], exames_brnet: list[str]) -> Dict[str, Any]:
    """
    Compara listas de exames usando o índice de similaridade e, se necessário, LLM para desempate.
    """
    contexto_rag = ""
    if exam_similarity_index and exam_similarity_data:
        # Busca sinônimos para todos os exames obrigatórios.
        contexto_list = []
        todos_exames_para_embedding = list(set(exames_brnet))
        
        if todos_exames_para_embedding:
            try:
                embeddings = np.vstack([await gerar_embedding(exame) for exame in todos_exames_para_embedding])
                D, I = exam_similarity_index.search(embeddings, 5) # Busca os 5 vizinhos mais próximos para cada exame

                # Coleta sinônimos únicos dos resultados
                sinonimos_encontrados = set()
                for i, indices in enumerate(I):
                    exame_principal = todos_exames_para_embedding[i]
                    sinonimos_encontrados.add(exame_principal) # Adiciona o próprio nome
                    for idx in indices:
                        if idx != -1:
                            sinonimos = exam_similarity_data[idx].get('sinonimos', [])
                            for s in sinonimos:
                                sinonimos_encontrados.add(s)
                
                if sinonimos_encontrados:
                    contexto_list.append("Para te ajudar na análise, considere a seguinte lista de exames e seus possíveis sinônimos e variações que encontramos em nossa base:")
                    contexto_list.append(", ".join(sorted(list(sinonimos_encontrados))))

            except Exception as e:
                logger.error(f"Erro durante a busca no índice FAISS: {e}")
        
        contexto_rag = "\n".join(contexto_list)

    prompt = f"""
    Você é um assistente especializado em comparar listas de exames médicos.
    Receberá duas listas de exames:
    1. Exames extraídos via OCR de um documento.
    2. Exames obtidos do sistema BRNET.

    Sua tarefa é comparar essas duas listas e gerar um array JSON de objetos, onde cada objeto representa um exame e contém as seguintes informações:
    - "exame": Nome do exame.
    - "presente_no_ocr": true se o exame estiver na lista do OCR, false caso contrário.
    - "presente_no_brnet": true se o exame estiver na lista do BRNET, false caso contrário.
    - "status":
        - "OK" se o exame estiver presente em ambas as listas.
        - "Faltando no OCR" se o exame estiver no BRNET mas não no OCR.
        - "Extra no OCR" se o exame estiver no OCR mas não no BRNET.

    {contexto_rag}

    Considere variações de nomes (ex: "Hemograma Completo" e "Hemograma") como o mesmo exame se a essência for a mesma. Use sua inteligência para agrupar exames similares.

    Exemplo de entrada:
    OCR: {json.dumps(exames_ocr)}
    BRNET: {json.dumps(exames_brnet)}
    """

    try:
        response = await client.chat.completions.create(
            model=settings.MODELO_GPT,
            messages=[
                {"role": "system", "content": "Você é um assistente que compara exames e retorna JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            temperature=0.0
        )
        content = response.choices[0].message.content
        parsed_content = json.loads(content)
        return parsed_content.get("comparacao", [])
    except Exception as e:
        logger.error(f"Erro ao chamar OpenAI para comparar exames (fallback): {e}")
        return {"erro": f"Erro ao comparar exames (fallback): {e}"}



async def _processar_documento_completo_impl(
    arquivo: UploadFile,
    exames_obrigatorios: list[str],
    progress_callback=None
) -> Dict[str, Any]:
    """
    Orquestra o processo completo de OCR, extração de CPF/exames, consulta BRMED (com fallback)
    e validação de exames.

    Args:
        arquivo: Arquivo para processar
        exames_obrigatorios: Lista de exames obrigatórios
        progress_callback: Callback opcional para enviar progresso (SSE)
    """
    run_id = uuid.uuid4().hex
    logger.info(f"[WORKFLOW] Iniciando processamento completo para: {arquivo.filename}")
    _log_event(
        "workflow_start",
        run_id=run_id,
        filename=arquivo.filename,
        content_type=getattr(arquivo, "content_type", None),
        exames_obrigatorios=exames_obrigatorios,
        exames_obrigatorios_count=len(exames_obrigatorios or []),
    )
    start_total = time.perf_counter()

    # Função auxiliar para enviar progresso
    async def send_progress(progress: int, step: str, message: str):
        logger.info(f"[WORKFLOW-PROGRESS] {progress}% - {step}: {message}")
        if progress_callback:
            await progress_callback(progress, step, message)

    # 1. Processar documento com OCR e extrair informações iniciais
    await send_progress(10, "ocr", "Processando documento com OCR...")
    t_ocr = time.perf_counter()
    loop = asyncio.get_running_loop()

    def ocr_progress_hook(message: str):
        if not progress_callback:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                send_progress(20, "ocr", message),
                loop,
            )
        except RuntimeError:
            logger.warning("[WORKFLOW] Não foi possível agendar progresso do OCR (loop ausente).")

    ocr_resultado = await ocr_service.ocr_pipeline(
        arquivo,
        progress_hook=ocr_progress_hook
    )
    logger.info(f"[WORKFLOW] OCR concluído em {time.perf_counter() - t_ocr:.2f}s")
    await send_progress(30, "ocr", f"OCR concluído. {len(ocr_resultado.get('exames', []))} exames encontrados")
    cpf_inicial = ocr_resultado.get("cpf")
    exames_enviados = ocr_resultado.get("exames", [])
    markdown_content = ocr_resultado.get("markdown_content", "")
    _log_event(
        "ocr_completed",
        run_id=run_id,
        cpf_extraido=cpf_inicial,
        exames_ocr=exames_enviados,
        exames_ocr_count=len(exames_enviados or []),
        markdown_chars=len(markdown_content or ""),
        markdown_lines=len((markdown_content or "").splitlines()),
        elapsed_seconds=round(time.perf_counter() - t_ocr, 3),
    )

    cpfs_tentados = set()
    if cpf_inicial:
        cpfs_tentados.add(cpf_inicial)

    cpf_final = None
    brmed_resultado = None
    patient_name = None

    # 2. Tentar com o CPF inicial (se houver)
    if cpf_inicial:
        await send_progress(40, "brmed", f"Consultando exames obrigatórios (CPF: {cpf_inicial[:3]}***)")
        t_brmed = time.perf_counter()
        logger.info(f"[WORKFLOW] Tentando consultar BRMED com CPF inicial: {cpf_inicial}")
        _log_event("brmed_attempt", run_id=run_id, cpf=cpf_inicial, attempt_type="inicial")
        brmed_resultado = await brmed_service.consultar_exames_brmed(cpf_inicial)
        logger.info(f"[WORKFLOW] Consulta BRMED concluída em {time.perf_counter() - t_brmed:.2f}s")
        if "erro" not in brmed_resultado:
            cpf_final = cpf_inicial
            exames_brnet = brmed_resultado.get("exames", [])
            patient_name = brmed_resultado.get("nome")
            _log_event(
                "brmed_success",
                run_id=run_id,
                cpf=cpf_final,
                patient_name=patient_name,
                exames_brnet=exames_brnet,
                exames_brnet_count=len(exames_brnet or []),
                elapsed_seconds=round(time.perf_counter() - t_brmed, 3),
            )
            await send_progress(60, "brmed", f"Exames obrigatórios obtidos: {len(exames_brnet)} exames")
        else:
            logger.warning(f'[WORKFLOW] Consulta BRMED falhou para CPF {cpf_inicial}: {brmed_resultado["erro"]}')
            _log_event(
                "brmed_failed",
                run_id=run_id,
                cpf=cpf_inicial,
                error=brmed_resultado.get("erro"),
                elapsed_seconds=round(time.perf_counter() - t_brmed, 3),
            )
            await send_progress(45, "brmed", "CPF inicial falhou, buscando CPFs alternativos...")
    else:
        await send_progress(40, "brmed", "CPF não encontrado, buscando alternativas...")

    exames_brnet = brmed_resultado.get("exames", []) if brmed_resultado else []

    # Se a consulta inicial falhou, tentar CPFs alternativos via IA
    if not cpf_final and markdown_content:
        logger.info("[WORKFLOW] CPF inicial falhou ou não encontrado. Buscando CPFs alternativos via IA...")
        cpfs_alternativos = await ocr_service.extrair_todos_cpfs_ia(markdown_content, exclude_cpf=cpf_inicial)
        _log_event(
            "cpf_alternatives",
            run_id=run_id,
            cpf_inicial=cpf_inicial,
            cpfs_alternativos=cpfs_alternativos,
            cpfs_alternativos_count=len(cpfs_alternativos or []),
        )

        for idx, alt_cpf in enumerate(cpfs_alternativos):
            if alt_cpf not in cpfs_tentados: # Evita tentar o mesmo CPF novamente
                await send_progress(45 + (idx * 5), "brmed", f"Tentando CPF alternativo {idx + 1}...")
                t_brmed_alt = time.perf_counter()
                logger.info(f"[WORKFLOW] Tentando consultar BRMED com CPF alternativo: {alt_cpf}")
                _log_event(
                    "brmed_attempt",
                    run_id=run_id,
                    cpf=alt_cpf,
                    attempt_type="alternativo",
                    attempt_index=idx + 1,
                )
                brmed_resultado = await brmed_service.consultar_exames_brmed(alt_cpf)
                logger.info(f"[WORKFLOW] Consulta BRMED concluída em {time.perf_counter() - t_brmed_alt:.2f}s")
                if "erro" not in brmed_resultado:
                    cpf_final = alt_cpf
                    exames_brnet = brmed_resultado.get("exames", [])
                    patient_name = brmed_resultado.get("nome")
                    _log_event(
                        "brmed_success",
                        run_id=run_id,
                        cpf=cpf_final,
                        patient_name=patient_name,
                        exames_brnet=exames_brnet,
                        exames_brnet_count=len(exames_brnet or []),
                        elapsed_seconds=round(time.perf_counter() - t_brmed_alt, 3),
                    )
                    await send_progress(60, "brmed", f"CPF válido encontrado! {len(exames_brnet)} exames obrigatórios")
                    break # Encontrou um CPF válido, sai do loop
                else:
                    logger.warning(f"[WORKFLOW] Consulta BRMED falhou para CPF alternativo {alt_cpf}: {brmed_resultado['erro']}")
                    _log_event(
                        "brmed_failed",
                        run_id=run_id,
                        cpf=alt_cpf,
                        error=brmed_resultado.get("erro"),
                        elapsed_seconds=round(time.perf_counter() - t_brmed_alt, 3),
                    )
                cpfs_tentados.add(alt_cpf)

    # Se nenhum CPF funcionou, retornar erro ou resultado parcial
    if not cpf_final:
        logger.error("[WORKFLOW] Não foi possível encontrar um CPF válido para consulta BRMED.")
        _log_event("workflow_failed", run_id=run_id, reason="cpf_nao_encontrado")
        await send_progress(-1, "erro", "Não foi possível extrair um CPF válido")
        cpf_fallback = cpf_inicial or "Não encontrado"
        return {
            "status": "error",
            "cpf": cpf_fallback,
            "cpf_processado": cpf_fallback,
            "patient_name": patient_name,
            "mensagem": "Não foi possível extrair um CPF válido ou consultar exames obrigatórios.",
            "decisao_final": "Erro no processamento",
            "erro": "Não foi possível extrair um CPF válido ou consultar exames obrigatórios.",
            "ocr_result": {
                "text": markdown_content,
                "exames_extraidos": exames_enviados
            },
            "brmed_result": {
                "exames_obrigatorios": []
            },
            "validation_result": {
                "exames_faltantes": [],
                "exames_extras": [],
                "analysis": "Não foi possível validar os exames devido à falta de CPF"
            }
        }

    # Se não vieram exames obrigatórios no request, use os da BRMED
    exames_obrigatorios_final = exames_obrigatorios or exames_brnet or []

    exames_enviados = _filtrar_exames_ocr(exames_enviados, exames_brnet, markdown_content)

    # 3. Validar exames
    await send_progress(70, "validacao", "Validando exames com IA...")
    t_validacao = time.perf_counter()
    logger.info(f"[WORKFLOW] Realizando validação para CPF: {cpf_final}")
    _log_event(
        "validacao_start",
        run_id=run_id,
        cpf=cpf_final,
        exames_obrigatorios=exames_obrigatorios_final,
        exames_obrigatorios_count=len(exames_obrigatorios_final or []),
        exames_ocr=exames_enviados,
        exames_ocr_count=len(exames_enviados or []),
        exames_brnet=exames_brnet,
        exames_brnet_count=len(exames_brnet or []),
    )
    resultado_validacao = await validacao_service.validar_exames(
        cpf=cpf_final,
        exames_obrigatorios=exames_obrigatorios_final,
        exames_enviados=exames_enviados,
        exames_brnet=exames_brnet,
        run_id=run_id
    )
    logger.info(f"[WORKFLOW] Validação concluída em {time.perf_counter() - t_validacao:.2f}s")
    await send_progress(90, "validacao", "Validação concluída, preparando resultado...")
    logger.info(f"[WORKFLOW] Validação concluída.")
    _log_event(
        "validacao_result",
        run_id=run_id,
        status_liberado=resultado_validacao.get("status_liberado"),
        mensagem=resultado_validacao.get("mensagem"),
        exames_faltantes=resultado_validacao.get("exames_faltantes"),
        exames_faltantes_count=len(resultado_validacao.get("exames_faltantes") or []),
        exames_presentes=resultado_validacao.get("exames_presentes"),
        exames_presentes_count=len(resultado_validacao.get("exames_presentes") or []),
        auditoria=resultado_validacao.get("auditoria_salva_em"),
        elapsed_seconds=round(time.perf_counter() - t_validacao, 3),
    )

    linhas_markdown = _extrair_linhas_markdown(markdown_content or "")
    analysis_details = {
        "quality": _avaliar_qualidade(markdown_content or "", linhas_markdown),
        "field_checks": _avaliar_campos(markdown_content or "", linhas_markdown, patient_name),
        "match_confidence": _avaliar_confianca_exames(
            resultado_validacao.get("exames_comparativo", []),
            exames_enviados,
            linhas_markdown
        ),
    }
    comparativo = resultado_validacao.get("exames_comparativo", [])
    obrigatorios_total = len([e for e in comparativo if e.get("status") != "extra_no_ocr"])
    obrigatorios_encontrados = len([e for e in comparativo if e.get("status") == "encontrado"])
    cobertura_obrigatorios = (
        obrigatorios_encontrados / obrigatorios_total
        if obrigatorios_total
        else 0.0
    )
    quality_score = analysis_details["quality"]["score"]
    confiabilidade_score = round((quality_score * 0.4) + (cobertura_obrigatorios * 100 * 0.6))
    confidence_details = {
        "score": confiabilidade_score,
        "quality_score": quality_score,
        "mandatory_coverage": round(cobertura_obrigatorios, 4),
        "mandatory_found": obrigatorios_encontrados,
        "mandatory_total": obrigatorios_total,
    }

    # Prepara o objeto de resposta final para o frontend
    resposta_final = {
        "run_id": run_id,
        "cpf_processado": cpf_final if cpf_final else "Não encontrado",
        "cpf": cpf_final if cpf_final else "Não encontrado",  # Apelido para compatibilidade
        "patient_name": patient_name,
        "exames_ocr": exames_enviados if exames_enviados else [],
        "exames_brnet": exames_brnet if exames_brnet else [],
        "analise_comparacao": (
            resultado_validacao.get("analise_ia")
            or resultado_validacao.get("mensagem")
            or "Análise de comparação de exames:"
        ),
        "tabela_comparacao": resultado_validacao["exames_comparativo"],
        "decisao_final": resultado_validacao["mensagem"],
        "analysis_details": analysis_details,
        "confidence_score": confiabilidade_score,
        "confidence_details": confidence_details,
        "erro": None,  # Inicialmente sem erro
        # Estrutura completa para compatibilidade com front-end (DocumentProcessingResult)
        "ocr_result": {
            "text": markdown_content,
            "exames_extraidos": exames_enviados
        },
        "brmed_result": {
            "exames_obrigatorios": exames_obrigatorios_final
        },
        "validation_result": {
            "exames_faltantes": [e["exame"] for e in resultado_validacao["exames_comparativo"] if e["status"] == "faltante"],
            "exames_extras": [e["exame"] for e in resultado_validacao["exames_comparativo"] if e["status"] == "extra_no_ocr"],
            "analysis": resultado_validacao["mensagem"]
        },
        "status": "success"  # Será ajustado abaixo se houver erro
    }

    if resultado_validacao.get("erro"):
        resposta_final["erro"] = resultado_validacao["erro"]
        resposta_final["status"] = "error"
        await send_progress(-1, "erro", f"Erro na validação: {resultado_validacao['erro']}")
        _log_event("workflow_failed", run_id=run_id, reason="validacao_erro", error=resultado_validacao.get("erro"))
    elif not cpf_final:
        resposta_final["erro"] = "Não foi possível extrair um CPF válido ou consultar exames obrigatórios."
        resposta_final["decisao_final"] = "Erro no processamento."
        resposta_final["status"] = "error"
        await send_progress(-1, "erro", "Erro no processamento")
        _log_event("workflow_failed", run_id=run_id, reason="cpf_nao_encontrado")

    await send_progress(100, "concluido", "Processamento concluído com sucesso!")
    logger.info(f"[WORKFLOW] Processamento completo finalizado para: {arquivo.filename}")
    logger.info(f"[WORKFLOW] Processamento completo em {time.perf_counter() - start_total:.2f}s")
    _log_event(
        "workflow_completed",
        run_id=run_id,
        filename=arquivo.filename,
        status=resposta_final.get("status"),
        elapsed_seconds=round(time.perf_counter() - start_total, 3),
    )

    return resposta_final


async def processar_documento_completo(
    arquivo: UploadFile,
    exames_obrigatorios: list[str],
    progress_callback=None
) -> Dict[str, Any]:
    if _PROCESSING_SEMAPHORE is None:
        return await _processar_documento_completo_impl(
            arquivo,
            exames_obrigatorios,
            progress_callback=progress_callback,
        )
    async with _PROCESSING_SEMAPHORE:
        return await _processar_documento_completo_impl(
            arquivo,
            exames_obrigatorios,
            progress_callback=progress_callback,
        )
