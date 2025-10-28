import faiss
import os

# Construindo caminhos a partir do diretório do script para robustez
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '.'))
INDEX_PATH = os.path.join(PROJECT_ROOT, "data", "faq_index.faiss")

print(f"--- Inspecionando o índice FAISS em {INDEX_PATH} ---")

if not os.path.exists(INDEX_PATH):
    print(f"ERRO: Arquivo de índice não encontrado em {INDEX_PATH}")
else:
    try:
        index = faiss.read_index(INDEX_PATH)
        print("Índice carregado com sucesso!")
        print(f"  - Tipo de índice: {type(index)}")
        print(f"  - Número de vetores no índice: {index.ntotal}")
        print(f"  - Dimensão dos vetores: {index.d}")
        # Verifica se o índice é treinado em métrica L2 ou IP
        if hasattr(index, 'metric_type'):
            metric = 'L2 (Euclidean)' if index.metric_type == faiss.METRIC_L2 else 'IP (Inner Product/Cosine)'
            print(f"  - Métrica de distância: {metric}")
        else:
            # Para índices mais simples como IndexFlatL2, o tipo está no nome da classe
            if 'L2' in str(type(index)):
                 print("  - Métrica de distância: L2 (Euclidean)")
            elif 'IP' in str(type(index)):
                 print("  - Métrica de distância: IP (Inner Product/Cosine)")
            else:
                print("  - Métrica de distância: Não foi possível determinar automaticamente.")

    except Exception as e:
        print(f"Ocorreu um erro ao carregar ou inspecionar o índice: {e}")

print("--- Inspeção do índice concluída ---")
