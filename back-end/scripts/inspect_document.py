

import asyncio
import argparse
import json
import io
import os
import sys
from fastapi import UploadFile

# Adiciona o diretório raiz do projeto ao sys.path
# para que possamos importar módulos do aplicativo (app)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services import ocr_service

async def inspect_document(file_path: str):
    """Carrega um arquivo, executa o pipeline de OCR e imprime o resultado."""
    if not os.path.exists(file_path):
        print(f"Erro: Arquivo não encontrado em '{file_path}'")
        return

    print(f"Inspecionando o arquivo: {os.path.basename(file_path)}...")

    try:
        with open(file_path, 'rb') as f:
            # Simula o objeto UploadFile que o serviço espera
            file_content = io.BytesIO(f.read())
            upload_file = UploadFile(
                filename=os.path.basename(file_path),
                file=file_content
            )

            # Executa o pipeline sem salvar o markdown de resultado
            resultado = await ocr_service.ocr_pipeline(upload_file, salvar_markdown=False)

            # Imprime o resultado em um formato JSON legível
            print("\n--- Resultado da Extração ---")
            print(json.dumps(resultado, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"\nOcorreu um erro durante o processamento: {e}")

def main():
    """Função principal para analisar argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description="Inspeciona um documento (PDF, imagem, etc.) para extrair CPF e exames."
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="O caminho absoluto ou relativo para o arquivo do documento."
    )

    args = parser.parse_args()
    asyncio.run(inspect_document(args.file_path))

if __name__ == "__main__":
    main()

