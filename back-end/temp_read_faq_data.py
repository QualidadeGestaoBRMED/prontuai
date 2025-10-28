
import pickle
import os

file_path = "/home/brmed/Área de trabalho/API_IA/data/faq_data.pkl"

if os.path.exists(file_path):
    with open(file_path, "rb") as f:
        data = pickle.load(f)
    
    pgr_entries = [item for item in data if "PGR" in item.get("Pergunta", "") or "PGR" in item.get("Resposta Padrão", "")]
    
    if pgr_entries:
        print("Found entries related to 'PGR':")
        for entry in pgr_entries:
            print(f"  Pergunta: {entry.get('Pergunta')}")
            print(f"  Resposta: {entry.get('Resposta Padrão')}")
            print("-" * 20)
    else:
        print("No entries related to 'PGR' found in faq_data.pkl.")
else:
    print(f"File not found: {file_path}")
