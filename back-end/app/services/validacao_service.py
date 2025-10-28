import os
from typing import List, Dict, Any
import logging
from app.core.config import settings
from tenacity import retry, wait_exponential, stop_after_attempt
import numpy as np
import faiss
import json
import pickle
from datetime import datetime
from app.core.clients import client

logger = logging.getLogger(__name__)

# Caminhos para o índice de similaridade de exames
EXAM_SIMILARITY_INDEX_PATH = os.path.join(settings.BASE_DIR, "data", "exam_similarity_index.faiss")
EXAM_SIMILARITY_DATA_PATH = os.path.join(settings.BASE_DIR, "data", "exam_similarity_data.pkl")

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def gerar_embedding(texto: str) -> np.ndarray:
    """Gera embedding para um texto usando a API da OpenAI."""
    resp = None # Initialize resp to None
    try:
        resp = await client.embeddings.create(
            input=[texto],
            model=settings.MODELO_EMBEDDING
        )
        return np.array(resp.data[0].embedding, dtype="float32").reshape(1, -1)
    except AttributeError as ae:
        logger.error(f"AttributeError ao processar embedding para '{texto[:50]}...': {ae}. Resposta completa: {resp}")
        raise # Re-raise to allow retry
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

async def comparar_exames_com_rag(exames_ocr: list[str], exames_brnet: list[str]) -> Dict[str, Any]:
    """
    Compara listas de exames usando o índice de similaridade e, se necessário, LLM para desempate.
    """
    contexto_rag = ""
    if exam_similarity_index and exam_similarity_data:
        # 1. Recuperação (Retrieval): Busca sinônimos para todos os exames obrigatórios.
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

async def validar_exames(cpf: str, exames_obrigatorios: List[str], exames_enviados: List[str], exames_brnet: List[str]) -> Dict[str, Any]:
    """Pipeline de validação: compara, salva auditoria e retorna resultado."""
    comparacao_final = await comparar_exames_com_rag(exames_enviados, exames_brnet)

    if isinstance(comparacao_final, dict) and "erro" in comparacao_final:
        return {"status_liberado": False, "mensagem": comparacao_final["erro"], "exames_comparativo": [], "auditoria_salva_em": "", "erro": comparacao_final["erro"]}

    # Processa o resultado da comparação para determinar o status final
    status_liberado = True
    exames_faltantes = []
    exames_presentes = []
    exames_comparativo = []

    # Primeiro, adicione todos os exames obrigatórios com seu status
    for item in comparacao_final:
        if item["status"] == "encontrado":
            exames_comparativo.append({"exame": item["exame"], "status": "encontrado", "justificativa": item.get("justificativa", "")})
            exames_presentes.append(item["exame"])
        elif item["status"] == "faltante":
            exames_comparativo.append({"exame": item["exame"], "status": "faltante", "justificativa": item.get("justificativa", "")})
            exames_faltantes.append(item["exame"])
        elif item["status"] == "extra_no_ocr":
            exames_comparativo.append({"exame": item["exame"], "status": "extra_no_ocr", "justificativa": item.get("justificativa", "")})

    status_liberado = len(exames_faltantes) == 0

    caminho_auditoria = salvar_auditoria(cpf, exames_obrigatorios, exames_enviados, comparacao_final)
    
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
