import pickle
import os

file_path = "/home/brmed/Área de trabalho/API_IA/data/faq_data.pkl"
print(f"--- Inspecionando o conteúdo de {file_path} ---")ll

if not os.path.exists(file_path):
    print(f"ERRO: Arquivo não encontrado em {file_path}")
else:
    try:
        with open(file_path, "rb") as f:
            data = pickle.load(f)
        
        if isinstance(data, list) and data:
            print(f"O arquivo contém uma lista com {len(data)} entradas.")
            print("--- Exibindo as 5 primeiras entradas ---")
            for i, item in enumerate(data[:5]):
                print(f"--- Entrada {i} ---")
                if isinstance(item, dict):
                    # Use repr() to get a safe, escaped representation of the strings
                    pergunta = item.get('Pergunta', 'N/A')
                    resposta = item.get('Resposta Padrão', 'N/A')
                    print(f"  Pergunta: {repr(pergunta)}")
                    print(f"  Resposta Padrão: {repr(resposta)}")
                else:
                    print(f"  A entrada não é um dicionário: {repr(item)}")
                print("-" * 20)
        else:
            print(f"O arquivo não contém uma lista ou está vazio. Tipo de dado: {type(data)}")
            print(f"Conteúdo: {repr(data)}")
            
    except Exception as e:
        print(f"Ocorreu um erro ao ler o arquivo pickle: {e}")

print("--- Inspeção concluída ---")
