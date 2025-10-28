import os
import pickle
import numpy as np
import pandas as pd
import faiss
from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Carrega variáveis de ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = os.getenv("MODELO_EMBEDDING", "text-embedding-3-large")

if not OPENAI_API_KEY:
    logging.error("A variável de ambiente OPENAI_API_KEY não está definida.")
    raise ValueError("OPENAI_API_KEY não encontrada.")

client = OpenAI(api_key=OPENAI_API_KEY);

# Caminhos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
BASE_TXT_PATH = os.path.join(PROJECT_ROOT, "base.txt")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INDEX_PATH = os.path.join(DATA_DIR, "faq_index.faiss")
DATA_PATH = os.path.join(DATA_DIR, "faq_data.pkl")

@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(5))
def gerar_embedding(texto: str) -> np.ndarray:
    """Gera embedding para um texto usando a API da OpenAI."""
    try:
        resp = client.embeddings.create(input=[texto], model=EMBED_MODEL)
        return np.array(resp.data[0].embedding, dtype="float32")
    except Exception as e:
        logging.error(f"Erro ao gerar embedding para o texto: '{texto[:50]}...': {e}")
        raise

def criar_base_vetorial():
    """Lê o arquivo base.txt, gera embeddings para chunks e cria o índice FAISS."""
    logging.info("Iniciando a criação da base vetorial com chunking...")

    # 1. Ler os dados
    try:
        df = pd.read_csv(BASE_TXT_PATH, sep='\t', engine='python')
        logging.info(f"Arquivo '{BASE_TXT_PATH}' lido com sucesso. {len(df)} registros encontrados.")
    except FileNotFoundError:
        logging.error(f"Arquivo '{BASE_TXT_PATH}' não encontrado.")
        return
    except Exception as e:
        logging.error(f"Erro ao ler o arquivo CSV: {e}")
        return

    # 2. Gerar embeddings para chunks
    logging.info("Gerando embeddings para os chunks...")
    embeddings = []
    base_conhecimento_chunks = []

    for _, row in df.iterrows():
        pergunta = row['Pergunta']
        resposta = row['Resposta Padrão']
        
        # Estratégia de Chunking
        chunks = [pergunta]  # A pergunta é o primeiro chunk
        # Quebra a resposta em parágrafos/linhas significativas
        answer_chunks = [line.strip() for line in resposta.split('\n') if line.strip()]
        chunks.extend(answer_chunks)

        for chunk in chunks:
            if not chunk: continue
            try:
                embedding = gerar_embedding(chunk)
                embeddings.append(embedding)
                base_conhecimento_chunks.append({
                    "chunk_text": chunk,
                    "original_question": pergunta,
                    "original_answer": resposta
                })
            except Exception:
                logging.warning(f"Não foi possível gerar embedding para o chunk: '{chunk[:50]}...'. Pulando.")
                continue
    
    if not embeddings:
        logging.error("Nenhum embedding foi gerado. Abortando.")
        return

    embeddings_matrix = np.vstack(embeddings)
    dimensao = embeddings_matrix.shape[1]
    logging.info(f"Embeddings gerados com sucesso. Total de chunks: {len(base_conhecimento_chunks)}. Dimensão: {dimensao}")

    # 3. Criar e treinar o índice FAISS
    logging.info("Criando e treinando o índice FAISS (IndexL2)...")
    index = faiss.IndexFlatL2(dimensao)
    index.add(embeddings_matrix)
    logging.info(f"Índice FAISS criado e treinado com {index.ntotal} vetores.")

    # 4. Salvar o índice e os dados
    os.makedirs(DATA_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_PATH)
    logging.info(f"Índice FAISS salvo em '{INDEX_PATH}'.")

    with open(DATA_PATH, "wb") as f:
        pickle.dump(base_conhecimento_chunks, f)
    logging.info(f"Base de conhecimento (chunks) salva em '{DATA_PATH}'.")

    logging.info("Processo de criação da base vetorial concluído com sucesso!")

if __name__ == "__main__":
    criar_base_vetorial()