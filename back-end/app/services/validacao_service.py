import os
import re
import unicodedata
from typing import List, Dict, Any, Optional
import logging
from app.core.config import settings
from tenacity import retry, wait_exponential, stop_after_attempt
import numpy as np
import faiss
import json
import pickle
from datetime import datetime
from app.core.clients import client
import csv

logger = logging.getLogger(__name__)

def _log_event(event: str, **payload: Any) -> None:
    try:
        logger.info("[VALIDACAO-EVENT] %s", json.dumps({"event": event, **payload}, ensure_ascii=False))
    except Exception:
        logger.info("[VALIDACAO-EVENT] %s | %s", event, payload)

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

def _normalizar_exame(texto: str) -> str:
    texto_normalizado = unicodedata.normalize("NFKD", texto or "")
    texto_normalizado = "".join(
        c for c in texto_normalizado if not unicodedata.combining(c)
    )
    texto_normalizado = re.sub(r"[^A-Z0-9 ]+", " ", texto_normalizado.upper())
    texto_normalizado = re.sub(r"\s+", " ", texto_normalizado).strip()
    if not texto_normalizado:
        return ""
    texto_normalizado = re.sub(r"\bRAIO\s*X\b", "RADIOGRAFIA", texto_normalizado)
    texto_normalizado = re.sub(r"\bRX\b", "RADIOGRAFIA", texto_normalizado)
    return texto_normalizado

def _tokens_relevantes(texto: str) -> set[str]:
    stopwords = {"DE", "DA", "DO", "DAS", "DOS", "E", "COM", "SEM", "PARA", "POR"}
    return {t for t in texto.split() if len(t) >= 3 and t not in stopwords}

def _token_subset_match(a: str, b: str) -> bool:
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    return bool(a_tokens) and a_tokens.issubset(b_tokens)

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
        sinonimos = item.get("sinonimos") or []
        termos = [principal] + list(similares) + list(sinonimos) if principal else list(similares) + list(sinonimos)
        termos_norm = {_normalizar_exame(t) for t in termos if t}
        for termo in termos_norm:
            if termo not in synonym_map:
                synonym_map[termo] = set()
            synonym_map[termo].update(termos_norm)
    return synonym_map

EXAM_SYNONYM_MAP = _build_synonym_map()

def _match_exame_local(exame_brnet: str, exames_ocr: List[str]) -> Optional[str]:
    norm_brnet = _normalizar_exame(exame_brnet)
    if not norm_brnet:
        return None
    synonyms = EXAM_SYNONYM_MAP.get(norm_brnet, set())

    for exame in exames_ocr:
        norm_ocr = _normalizar_exame(exame)
        if not norm_ocr:
            continue
        if norm_ocr == norm_brnet:
            return exame
        if synonyms and norm_ocr in synonyms:
            return exame

    for exame in exames_ocr:
        norm_ocr = _normalizar_exame(exame)
        if not norm_ocr:
            continue
        if _token_subset_match(norm_brnet, norm_ocr) or _token_overlap_match(norm_brnet, norm_ocr):
            return exame

    return None

async def comparar_exames_com_rag(exames_ocr: list[str], exames_brnet: list[str]) -> Dict[str, Any]:
    """
    Compara listas de exames usando o índice de similaridade e, se necessário, LLM para desempate.
    """
    contexto_rag = ""
    if exam_similarity_index and exam_similarity_data:
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
    Você é um assistente especializado em analisar exames médicos.
    Sua tarefa é comparar a lista de 'Exames Obrigatórios' com a lista de 'Exames Recebidos' e determinar quais obrigatórios foram encontrados.

    {contexto_rag}

    Use o contexto acima para entender possíveis variações de nomes. Um exame recebido pode satisfazer um obrigatório mesmo que os nomes não sejam idênticos (ex: 'Hemograma', 'Hemograma Completo' e 'Hemograma com Plaquetas').

    Considere hemograma completo, completo com plaquetas e hemograma como iguais.

    Use o contexto acima para entender possíveis variações de nomes. Um exame recebido pode satisfazer um obrigatório mesmo que os nomes não sejam idênticos (ex: 'Hemograma', 'Hemograma Completo' e 'Hemograma com Plaquetas').

    Considere também que um exame mais abrangente pode cobrir exames mais específicos (ex: 'Colesterol Total' pode ser considerado encontrado se 'COLESTEROL HDL' e 'COLESTEROL LDL' forem encontrados).

    Listas para análise:
    - Exames Obrigatórios: {json.dumps(exames_brnet)}
    - Exames Recebidos: {json.dumps(exames_ocr)}

    Gere um array JSON de objetos, um para cada exame obrigatório, com os seguintes campos:
    - "exame": O nome do exame obrigatório.
    - "status": Pode ser "encontrado", "faltante", ou "extra_no_ocr".
        - "encontrado": O exame foi encontrado e corresponde ao esperado.
        - "faltante": O exame era esperado, mas não foi encontrado.
        - "extra_no_ocr": O exame foi encontrado no documento (OCR), mas não estava na lista de exames previstos (BRNET).
    - "justificativa": Uma breve explicação sobre o status do exame. Esta será a informação exibida no tooltip.

    Além disso, identifique quaisquer exames na lista de 'Exames Recebidos' que não correspondam a nenhum 'Exame Obrigatório' e inclua-os no array JSON com o status "extra_no_ocr".

    Exemplo de saída esperada:
    ```json
    [
        {{"exame": "CLÍNICO OCUPACIONAL", "status": "faltante", "justificativa": "O exame 'CLÍNICO OCUPACIONAL' não foi encontrado na lista de exames recebidos."}},
        {{"exame": "LDL", "status": "encontrado", "justificativa": "'LDL' foi encontrado na lista de exames recebidos como 'COLESTEROL LDL'."}},
        {{"exame": "HEMOGRAMA COMPLETO COM PLAQUETAS", "status": "encontrado", "justificativa": "'HEMOGRAMA COMPLETO COM PLAQUETAS' foi considerado encontrado pois 'HEMOGRAMA' foi recebido."}},
        {{"exame": "EXAME_EXTRA_1", "status": "extra_no_ocr", "justificativa": "Este exame foi encontrado no documento (OCR), mas não está previsto na lista de exames do BRNET."}}
    ]
    ```
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
        # A IA pode aninhar a lista dentro de uma chave, então verificamos isso.
        if isinstance(parsed_content, dict) and len(parsed_content.keys()) == 1:
             possible_key = list(parsed_content.keys())[0]
             if isinstance(parsed_content[possible_key], list):
                  return parsed_content[possible_key]
        return parsed_content # Retorna o objeto JSON diretamente
    except Exception as e:
        logger.error(f"Erro ao chamar OpenAI para comparar exames (fallback): {e}")
        return {"erro": f"Erro ao comparar exames (fallback): {e}"}



def salvar_auditoria(cpf: str, obrigatorios: List[str], enviados: List[str], resultado: Dict[str, Any]):
    """Salva o resultado da validação para auditoria."""
    os.makedirs("auditoria_validacao", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = f"auditoria_validacao/validacao_{cpf}_{ts}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump({
            "cpf": cpf,
            "exames_obrigatorios": obrigatorios,
            "exames_enviados": enviados,
            "resultado": resultado
        }, f, ensure_ascii=False, indent=4)
    return fn

async def validar_exames(cpf: str, exames_obrigatorios: List[str], exames_enviados: List[str], exames_brnet: List[str], run_id: Optional[str] = None) -> Dict[str, Any]:
    """Pipeline de validação: compara, salva auditoria e retorna resultado."""
    comparacao_final = await comparar_exames_com_rag(exames_enviados, exames_brnet)

    if isinstance(comparacao_final, dict) and "erro" in comparacao_final:
        return {"status_liberado": False, "mensagem": comparacao_final["erro"], "exames_comparativo": [], "auditoria_salva_em": "", "erro": comparacao_final["erro"]}

    def extrair_lista_comparacao(resultado: Any) -> List[Dict[str, Any]] | None:
        if isinstance(resultado, list):
            return resultado if all(isinstance(item, dict) for item in resultado) else None
        if isinstance(resultado, dict):
            for key in ("comparacao", "comparativo", "resultado", "exames"):
                valor = resultado.get(key)
                if isinstance(valor, list) and all(isinstance(item, dict) for item in valor):
                    return valor
            for valor in resultado.values():
                if isinstance(valor, list) and all(isinstance(item, dict) for item in valor):
                    return valor
        return None

    comparacao_list = extrair_lista_comparacao(comparacao_final)
    if comparacao_list is None:
        logger.error(f"Formato inesperado de comparacao_final: {type(comparacao_final)}")
        return {
            "status_liberado": False,
            "mensagem": "Erro ao validar exames: formato de resposta inesperado.",
            "exames_comparativo": [],
            "auditoria_salva_em": "",
            "erro": "formato_de_resposta_invalido"
        }

    if run_id:
        _log_event(
            "comparacao_raw",
            run_id=run_id,
            cpf=cpf,
            comparacao_raw=comparacao_list,
            comparacao_raw_count=len(comparacao_list or []),
        )

    brnet_norm_list = []
    brnet_norm_set = set()
    for exame in exames_brnet or []:
        normalizado = _normalizar_exame(exame)
        if not normalizado:
            continue
        brnet_norm_set.add(normalizado)
        brnet_norm_list.append((exame, normalizado))

    ocr_norm_to_brnet = {}
    for exame_brnet, _ in brnet_norm_list:
        match = _match_exame_local(exame_brnet, exames_enviados or [])
        if match:
            ocr_norm_to_brnet[_normalizar_exame(match)] = exame_brnet

    extras_matched = set()
    for item in comparacao_list:
        if item.get("status") != "faltante":
            continue
        exame = item.get("exame")
        if not exame:
            continue
        match = _match_exame_local(exame, exames_enviados or [])
        if match:
            item["status"] = "encontrado"
            item["justificativa"] = f"Correspondencia aproximada com '{match}'."
            extras_matched.add(_normalizar_exame(match))

    comparacao_corrigida = []
    brnet_present_norms = set()
    for item in comparacao_list:
        status = item.get("status")
        exame = item.get("exame")
        if not exame or not status:
            continue
        normalizado = _normalizar_exame(exame)
        if status == "extra_no_ocr":
            if normalizado in extras_matched or normalizado in brnet_norm_set or normalizado in ocr_norm_to_brnet:
                continue
        if normalizado and status != "extra_no_ocr":
            if normalizado in brnet_present_norms:
                continue
            brnet_present_norms.add(normalizado)
        comparacao_corrigida.append(item)

    for exame_brnet, normalizado in brnet_norm_list:
        if normalizado in brnet_present_norms:
            continue
        match = _match_exame_local(exame_brnet, exames_enviados or [])
        if match:
            comparacao_corrigida.append({
                "exame": exame_brnet,
                "status": "encontrado",
                "justificativa": f"Correspondencia aproximada com '{match}'."
            })
        else:
            comparacao_corrigida.append({
                "exame": exame_brnet,
                "status": "faltante",
                "justificativa": "Exame obrigatório não encontrado no OCR."
            })
        brnet_present_norms.add(normalizado)

    if run_id:
        status_counts = {"encontrado": 0, "faltante": 0, "extra_no_ocr": 0}
        for item in comparacao_corrigida:
            status = item.get("status")
            if status in status_counts:
                status_counts[status] += 1
        _log_event(
            "comparacao_corrigida",
            run_id=run_id,
            cpf=cpf,
            status_counts=status_counts,
            comparacao_corrigida=comparacao_corrigida,
            comparacao_corrigida_count=len(comparacao_corrigida or []),
        )

    # Processa o resultado da comparação para determinar o status final
    status_liberado = True
    exames_faltantes = []
    exames_presentes = []
    exames_comparativo = []

    # Primeiro, adicione todos os exames obrigatórios com seu status
    for item in comparacao_corrigida:
        status = item.get("status")
        exame = item.get("exame")
        if not exame or not status:
            continue
        if status == "encontrado":
            exames_comparativo.append({"exame": exame, "status": "encontrado", "justificativa": item.get("justificativa", "")})
            exames_presentes.append(exame)
        elif status == "faltante":
            exames_comparativo.append({"exame": exame, "status": "faltante", "justificativa": item.get("justificativa", "")})
            exames_faltantes.append(exame)
        elif status == "extra_no_ocr":
            if _normalizar_exame(exame) in extras_matched:
                continue
            exames_comparativo.append({"exame": exame, "status": "extra_no_ocr", "justificativa": item.get("justificativa", "")})

    status_liberado = len(exames_faltantes) == 0

    caminho_auditoria = salvar_auditoria(cpf, exames_obrigatorios, exames_enviados, comparacao_corrigida)
    
    # Prepara a resposta final para o frontend
    resposta_final = {
        "status_liberado": status_liberado,
        "exames_comparativo": exames_comparativo,
        "auditoria_salva_em": caminho_auditoria,
        "exames_faltantes": exames_faltantes,
        "exames_presentes": exames_presentes
    }

    if status_liberado:
        resposta_final["mensagem"] = "Todos os exames obrigatórios foram enviados. Liberação concedida."
    else:
        resposta_final["mensagem"] = f"Faltam exames obrigatórios: {', '.join(exames_faltantes)}"
    
    return resposta_final
