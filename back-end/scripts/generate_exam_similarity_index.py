
import os
import pickle
import numpy as np
import pandas as pd
import faiss
from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt
import logging
import unicodedata

def normalizar_exame(exame: str) -> str:
    """Remove acentos, caixa e caracteres especiais para comparar exames."""
    nfkd = unicodedata.normalize('NFKD', exame)
    return ''.join([c for c in nfkd if not unicodedata.combining(c)]).upper().strip()

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Carrega variáveis de ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = os.getenv("MODELO_EMBEDDING", "text-embedding-3-large")

if not OPENAI_API_KEY:
    logging.error("A variável de ambiente OPENAI_API_KEY não está definida.")
    raise ValueError("OPENAI_API_KEY não encontrada.")

client = OpenAI(api_key=OPENAI_API_KEY)

# Caminhos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
SIMILAR_EXAMS_CSV_PATH = os.path.join(PROJECT_ROOT, "exames_similares_final.csv")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INDEX_PATH = os.path.join(DATA_DIR, "exam_similarity_index.faiss")
DATA_PATH = os.path.join(DATA_DIR, "exam_similarity_data.pkl")

@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(5))
def gerar_embedding(texto: str) -> np.ndarray:
    """Gera embedding para um texto usando a API da OpenAI."""
    try:
        resp = client.embeddings.create(input=[texto], model=EMBED_MODEL)
        return np.array(resp.data[0].embedding, dtype="float32")
    except Exception as e:
        logging.error(f"Erro ao gerar embedding para o texto: '{texto[:50]}...': {e}")
        raise

def criar_indice_similaridade_exames():
    """Lê o arquivo CSV de exames similares, gera embeddings e cria o índice FAISS."""
    logging.info("Iniciando a criação do índice de similaridade de exames...")

    # 1. Ler os dados
    try:
        df = pd.read_csv(SIMILAR_EXAMS_CSV_PATH, sep=',', engine='python')
        logging.info(f"Arquivo '{SIMILAR_EXAMS_CSV_PATH}' lido com sucesso. {len(df)} registros encontrados.")
    except FileNotFoundError:
        logging.error(f"Arquivo '{SIMILAR_EXAMS_CSV_PATH}' não encontrado.")
        return
    except Exception as e:
        logging.error(f"Erro ao ler o arquivo CSV: {e}")
        return

    # 2. Gerar embeddings
    logging.info("Gerando embeddings para os exames e seus similares...")
    embeddings = []
    exames_data = []

    for _, row in df.iterrows():
        exame_principal = row['Exame']
        similares = str(row['Similares']).split(',') # Garante que é string e divide
        
        # Crie um texto para embedding que represente o exame principal e seus similares
        texto_para_embedding = f"Exame: {normalizar_exame(exame_principal)}. Similares: {', '.join([normalizar_exame(s) for s in similares])}"
        
        try:
            embedding = gerar_embedding(texto_para_embedding)
            embeddings.append(embedding)
            exames_data.append({
                "exame_principal": exame_principal,
                "similares": similares,
                "texto_embedding": texto_para_embedding # Armazena o texto usado para embedding
            })
        except Exception:
            logging.warning(f"Não foi possível gerar embedding para o exame: '{exame_principal}'. Pulando.")
            continue
    
    if not embeddings:
        logging.error("Nenhum embedding foi gerado. Abortando.")
        return

    embeddings_matrix = np.vstack(embeddings)
    dimensao = embeddings_matrix.shape[1]
    logging.info(f"Embeddings gerados com sucesso. Total de exames: {len(exames_data)}. Dimensão: {dimensao}")

    # 3. Criar e treinar o índice FAISS
    logging.info("Criando e treinando o índice FAISS (IndexFlatL2)...")
    index = faiss.IndexFlatL2(dimensao)
    index.add(embeddings_matrix)
    logging.info(f"Índice FAISS criado e treinado com {index.ntotal} vetores.")

    # 4. Salvar o índice e os dados
    os.makedirs(DATA_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_PATH)
    logging.info(f"Índice FAISS salvo em '{INDEX_PATH}'.")

    with open(DATA_PATH, "wb") as f:
        pickle.dump(exames_data, f)
    logging.info(f"Dados de similaridade de exames salvos em '{DATA_PATH}'.")

    logging.info("Processo de criação do índice de similaridade de exames concluído com sucesso!")

if __name__ == "__main__":
    criar_indice_similaridade_exames()
