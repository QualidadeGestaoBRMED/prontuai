import os
import logging
import pickle
import numpy as np
import faiss
from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt

# ─── Configuração de Logging ─────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# ─── Variáveis de ambiente ────────────────────────────────────────────────────
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
EMBED_MODEL        = os.getenv("MODELO_EMBEDDING", "text-embedding-3-large")
CHAT_MODEL         = os.getenv("MODELO_GPT", "gpt-3.5-turbo")
K_VIZINHOS         = int(os.getenv("K_VIZINHOS_FAQ", 5))
# CORREÇÃO FINAL: O índice usa L2, então usamos um threshold para L2 e a lógica correta.
THRESHOLD_L2       = float(os.getenv("THRESHOLD_L2", 1.5))

# Construindo caminhos a partir do diretório do script para robustez
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
INDEX_PATH = os.path.join(PROJECT_ROOT, "data", "faq_index.faiss")
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "faq_data.pkl")
SYSTEM_PROMPT_PATH = os.path.join(PROJECT_ROOT, "system_prompt.txt")

if OPENAI_API_KEY is None:
    logger.error("Você deve definir a variável de ambiente OPENAI_API_KEY.")
    raise SystemExit(1)

# ─── Cliente OpenAI ───────────────────────────────────────────────────────────
client = OpenAI(api_key=OPENAI_API_KEY)

# ─── Carrega System Prompt ────────────────────────────────────────────────────
try:
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read().strip()
        logger.info(f"System prompt carregado de '{SYSTEM_PROMPT_PATH}'.")
except FileNotFoundError:
    SYSTEM_PROMPT = "Você é um assistente prestativo."
    logger.warning(f"Arquivo '{SYSTEM_PROMPT_PATH}' não encontrado. Usando prompt padrão.")

# ─── Carrega índice FAISS e metadados ─────────────────────────────────────────
try:
    index = faiss.read_index(INDEX_PATH)
    with open(DATA_PATH, "rb") as f:
        base_conhecimento = pickle.load(f)
    logger.info("Índice FAISS e base de conhecimento carregados com sucesso.")
    logger.info(f"Dimensão do índice FAISS: {index.d}")
except Exception as e:
    logger.exception(f"Erro ao inicializar FAQ service: {e}")
    raise

# ─── Função de geração de embedding com retry ───────────────────────────────────
@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
def gerar_embedding(texto: str) -> np.ndarray:
    """
    Chama o endpoint de embeddings e retorna o vetor.
    """
    resp = client.embeddings.create(
        input=[texto],
        model=EMBED_MODEL
    )
    vec = np.array(resp.data[0].embedding, dtype="float32")
    # CORREÇÃO FINAL: A normalização foi removida pois o índice é L2.
    return vec.reshape(1, -1)

# ─── Monta o prompt do chat com RAG ────────────────────────────────────────────
def montar_mensagens(pergunta: str, blocos_contexto: list, historico: list) -> list:
    """
    Retorna lista de mensagens para o chat completions, incluindo system, contexto,
    histórico e última pergunta do usuário.
    """
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if blocos_contexto:
        contexto = "\n\n".join(blocos_contexto)
        msgs.append({
            "role": "system",
            "content": f"Contexto relevante:\n\n{contexto}"
        })
    if historico:
        for msg in historico:
            if msg.get("role") in ("user", "assistant"):
                msgs.append(msg)
    msgs.append({"role": "user", "content": pergunta})
    return msgs

# ─── Pipeline principal de busca e resposta ───────────────────────────────────
def buscar_e_responder(pergunta: str, historico: list = None) -> dict:
    """
    Pipeline de busca e resposta com lógica corrigida para L2.
    """
    historico = historico or []
    blocos, perguntas_usadas, respostas_usadas = [], [], []
    rag_scores = []

    if len(pergunta.strip()) > 3:
        emb = gerar_embedding(pergunta)
        if emb.shape[1] != index.d:
            raise ValueError(f"Disparidade de dimensão! Embedding: {emb.shape[1]}, Índice: {index.d}.")

        D, I = index.search(emb, K_VIZINHOS)
        rag_scores = [f'{s:.4f}' for s in D[0]]

        # CORREÇÃO FINAL: Lógica de filtro para L2 (score < threshold).
        for score, idx in zip(D[0], I[0]):
            if idx != -1 and score < THRESHOLD_L2:
                try:
                    item = base_conhecimento[idx]
                    perguntas_usadas.append(item["Pergunta"])
                    respostas_usadas.append(item["Resposta Padrão"])
                    blocos.append(f"Pergunta: {item['Pergunta']}\nResposta: {item['Resposta Padrão']}")
                except KeyError:
                    logger.error(f"DEBUG: O item do índice {idx} não contém a chave 'Pergunta' ou 'Resposta Padrão'.")
                    logger.error(f"DEBUG: Conteúdo do item: {item}")
                    logger.error(f"DEBUG: Chaves disponíveis no item: {item.keys()}")
                    continue

    if blocos:
        mensagens = montar_mensagens(pergunta, blocos, historico)
    else:
        mensagens = montar_mensagens(pergunta, [], historico) # Envia sem contexto RAG

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=mensagens,
        temperature=0.7 
    )
    conteudo = response.choices[0].message.content
    usage = response.usage

    logger.info(
        f"Tokens prompt: {usage.prompt_tokens} | "
        f"Tokens completion: {usage.completion_tokens} | "
        f"Total: {usage.total_tokens}"
    )
    logger.info(f"Scores RAG: {rag_scores}")

    if blocos:
        logger.info(f"Perguntas base utilizadas: {perguntas_usadas}")
        conteudo = f"* {conteudo}"

    return {
        "pergunta_usuario": pergunta,
        "rag_utilizado": bool(blocos),
        "perguntas_base": perguntas_usadas,
        "respostas_base": respostas_usadas,
        "resposta_gerada": conteudo
    }

# ─── Exemplo de uso ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("Erro: A variável de ambiente OPENAI_API_KEY não está definida.")
    else:
        test_question = "O que é AET?"
        try:
            resultado = buscar_e_responder(test_question)
            print("Pergunta:", test_question)
            print("\nResposta final:", resultado["resposta_gerada"])
            if resultado["rag_utilizado"]:
                print("\n— Com base em FAQs:")
                for p, r in zip(resultado["perguntas_base"], resultado["respostas_base"]):
                    print(f"  • {p} → {r}")
        except Exception as e:
            print(f"Ocorreu um erro durante o teste: {e}")
