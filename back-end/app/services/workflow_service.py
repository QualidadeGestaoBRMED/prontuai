import os
from typing import Dict, Any, Optional, List
from fastapi import UploadFile
from app.services import ocr_service, brmed_service, validacao_service
from app.core.config import settings
import logging
import json
from openai import OpenAI
import faiss
import pickle
import numpy as np
from tenacity import retry, wait_exponential, stop_after_attempt
from datetime import datetime

logger = logging.getLogger(__name__)

from app.core.clients import client

# Caminhos para o índice de similaridade de exames
logger.info(f"DEBUG: settings.BASE_DIR is {settings.BASE_DIR}")
EXAM_SIMILARITY_INDEX_PATH = os.path.join(settings.BASE_DIR, "data", "exam_similarity_index.faiss")
EXAM_SIMILARITY_DATA_PATH = os.path.join(settings.BASE_DIR, "data", "exam_similarity_data.pkl")

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



async def processar_documento_completo(
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
    logger.info(f"[WORKFLOW] Iniciando processamento completo para: {arquivo.filename}")

    # Helper para enviar progresso
    async def send_progress(progress: int, step: str, message: str):
        logger.info(f"[WORKFLOW-PROGRESS] {progress}% - {step}: {message}")
        if progress_callback:
            await progress_callback(progress, step, message)

    # 1. Processar documento com OCR e extrair informações iniciais
    await send_progress(10, "ocr", "Processando documento com OCR...")
    ocr_resultado = await ocr_service.ocr_pipeline(arquivo)
    await send_progress(30, "ocr", f"OCR concluído. {len(ocr_resultado.get('exames', []))} exames encontrados")
    cpf_inicial = ocr_resultado.get("cpf")
    exames_enviados = ocr_resultado.get("exames", [])
    markdown_content = ocr_resultado.get("markdown_content", "")

    cpfs_tentados = set()
    if cpf_inicial:
        cpfs_tentados.add(cpf_inicial)

    cpf_final = None
    brmed_resultado = None

    # 2. Tentar com o CPF inicial (se houver)
    if cpf_inicial:
        await send_progress(40, "brmed", f"Consultando exames obrigatórios (CPF: {cpf_inicial[:3]}***)")
        logger.info(f"[WORKFLOW] Tentando consultar BRMED com CPF inicial: {cpf_inicial}")
        brmed_resultado = await brmed_service.consultar_exames_brmed(cpf_inicial)
        if "erro" not in brmed_resultado:
            cpf_final = cpf_inicial
            exames_brnet = brmed_resultado.get("exames", [])
            await send_progress(60, "brmed", f"Exames obrigatórios obtidos: {len(exames_brnet)} exames")
        else:
            logger.warning(f'[WORKFLOW] Consulta BRMED falhou para CPF {cpf_inicial}: {brmed_resultado["erro"]}')
            await send_progress(45, "brmed", "CPF inicial falhou, buscando CPFs alternativos...")
    else:
        await send_progress(40, "brmed", "CPF não encontrado, buscando alternativas...")

    exames_brnet = brmed_resultado.get("exames", []) if brmed_resultado else []

    # Se a consulta inicial falhou, tentar CPFs alternativos via IA
    if not cpf_final and markdown_content:
        logger.info("[WORKFLOW] CPF inicial falhou ou não encontrado. Buscando CPFs alternativos via IA...")
        cpfs_alternativos = await ocr_service.extrair_todos_cpfs_ia(markdown_content, exclude_cpf=cpf_inicial)

        for idx, alt_cpf in enumerate(cpfs_alternativos):
            if alt_cpf not in cpfs_tentados: # Evita tentar o mesmo CPF novamente
                await send_progress(45 + (idx * 5), "brmed", f"Tentando CPF alternativo {idx + 1}...")
                logger.info(f"[WORKFLOW] Tentando consultar BRMED com CPF alternativo: {alt_cpf}")
                brmed_resultado = await brmed_service.consultar_exames_brmed(alt_cpf)
                if "erro" not in brmed_resultado:
                    cpf_final = alt_cpf
                    exames_brnet = brmed_resultado.get("exames", [])
                    await send_progress(60, "brmed", f"CPF válido encontrado! {len(exames_brnet)} exames obrigatórios")
                    break # Encontrou um CPF válido, sai do loop
                else:
                    logger.warning(f"[WORKFLOW] Consulta BRMED falhou para CPF alternativo {alt_cpf}: {brmed_resultado['erro']}")
                cpfs_tentados.add(alt_cpf)

    # Se nenhum CPF funcionou, retornar erro ou resultado parcial
    if not cpf_final:
        logger.error("[WORKFLOW] Não foi possível encontrar um CPF válido para consulta BRMED.")
        await send_progress(-1, "erro", "Não foi possível extrair um CPF válido")
        return {
            "status": "falha",
            "mensagem": "Não foi possível extrair um CPF válido ou consultar exames obrigatórios.",
            "exames_enviados": exames_enviados,
            "ocr_info": ocr_resultado
        }

    # 3. Validar exames
    await send_progress(70, "validacao", "Validando exames com IA...")
    logger.info(f"[WORKFLOW] Realizando validação para CPF: {cpf_final}")
    resultado_validacao = await validacao_service.validar_exames(
        cpf=cpf_final,
        exames_obrigatorios=exames_obrigatorios,
        exames_enviados=exames_enviados,
        exames_brnet=exames_brnet
    )
    await send_progress(90, "validacao", "Validação concluída, preparando resultado...")
    logger.info(f"[WORKFLOW] Validação concluída.")

    # Prepara o objeto de resposta final para o frontend
    resposta_final = {
        "cpf_processado": cpf_final if cpf_final else "Não encontrado",
        "exames_ocr": f"{', '.join(exames_enviados) if exames_enviados else 'Nenhum exame encontrado.'}",
        "exames_brnet": f"{', '.join(exames_brnet) if exames_brnet else 'Nenhum exame encontrado.'}",
        "analise_comparacao": "Análise de comparação de exames:",
        "tabela_comparacao": resultado_validacao["exames_comparativo"],
        "decisao_final": resultado_validacao["mensagem"],
        "erro": None # Inicialmente sem erro
    }

    if resultado_validacao.get("erro"):
        resposta_final["erro"] = resultado_validacao["erro"]
        await send_progress(-1, "erro", f"Erro na validação: {resultado_validacao['erro']}")
    elif not cpf_final:
        resposta_final["erro"] = "Não foi possível extrair um CPF válido ou consultar exames obrigatórios."
        resposta_final["decisao_final"] = "Erro no processamento."
        await send_progress(-1, "erro", "Erro no processamento")

    await send_progress(100, "concluido", "Processamento concluído com sucesso!")
    logger.info(f"[WORKFLOW] Processamento completo finalizado para: {arquivo.filename}")

    return resposta_final