import os
# Set environment variable for PyTorch memory management
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import tempfile
from docling.document_converter import DocumentConverter
import torch
import re
import json
from openai import OpenAI
from typing import Dict, Any, List, Optional

from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Prompt detalhado para LLM
MODELO_GPT = settings.MODELO_GPT

# Prompt detalhado para LLM
PROMPT_EXTRAIR_EXAMES = """
Você é um assistente de extração de dados altamente preciso.
Sua tarefa é extrair a lista de nomes de exames de um texto.
Considere como exame qualquer linha que contenha uma lista clara de exames ou procedimentos realizados, linhas no formato 'NOME DO EXAME - DATA',
ou qualquer header do tipo '## NOME DO EXAME'. Extraia o nome do exame do header, ignorando o prefixo '##' e espaços.
Nesses casos, extraia apenas o nome antes do hífen como exame.
Se o texto não contiver uma lista clara de exames ou procedimentos, retorne uma lista vazia.
Não infira exames a partir de menções genéricas como 'exame de sangue'.
Responda APENAS com um objeto JSON válido, sem nenhum texto adicional antes ou depois.
O formato do JSON deve ser: {"exames": ["<exame1>", "<exame2>"]}.
Se nenhum exame for encontrado, use uma lista vazia [] para a chave "exames".
Não invente exames e ignore informações irrelevantes.
Retorne os nomes dos exames em caixa alta.
"""

PROMPT_EXTRAIR_CPF = """
Você é um assistente de extração de dados altamente preciso.
Sua tarefa é extrair o CPF (apenas números, sem pontuação) de um texto.
ATENÇÃO: Se houver um CPF imediatamente após uma sigla de UF (por exemplo, CE/67495788372, SP/12345678901, etc),
você DEVE priorizar e retornar esse CPF, ignorando outros CPFs que possam aparecer no texto.
Se houver mais de um padrão UF/CPF, retorne o primeiro que aparecer.
Se não houver nenhum CPF após UF, aí sim retorne o primeiro CPF de 11 dígitos encontrado.
Responda APENAS com um objeto JSON válido, sem nenhum texto adicional antes ou depois.
O formato do JSON deve ser: {"cpf": "<cpf_extraido>"}.
Se o CPF não for encontrado, use o valor null para a chave "cpf".
"""

def extrair_cpf_ia(markdown: str) -> str:
    """Extrai CPF do markdown usando LLM."""
    user_prompt = f"""Texto:\n{markdown}"""
    try:
        response = client.chat.completions.create(
            model=MODELO_GPT,
            messages=[
                {"role": "system", "content": PROMPT_EXTRAIR_CPF},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("cpf")
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"Erro ao extrair CPF via IA: {e}")
        return None


def processar_arquivo_docling(file) -> str:
    """Processa o arquivo com Docling e retorna o markdown extraído."""
    converter = DocumentConverter()
    resultado = converter.convert(file)
    markdown = resultado.document.export_to_markdown()
    return markdown

def extrair_exames_ia(markdown: str) -> Dict[str, Any]:
    """Extrai apenas exames do markdown usando LLM."""
    user_prompt = f"""Texto:
{markdown}"""
    try:
        response = client.chat.completions.create(
            model=MODELO_GPT,
            messages=[
                {"role": "system", "content": PROMPT_EXTRAIR_EXAMES},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        if "exames" not in data:
            return {"exames": [], "erro": "Resposta da IA não contém a chave 'exames'."}
        return data
    except json.JSONDecodeError:
        return {"exames": [], "erro": "Falha ao decodificar o JSON da resposta da IA."}
    except Exception as e:
        return {"exames": [], "erro": f"Ocorreu um erro inesperado: {e}"}

def extrair_cpf_regex(markdown: str) -> str:
    # Tenta encontrar o padrão UF/CPF primeiro (ex: CE/12345678900)
    uf_cpf_match = re.search(r'\b[A-Z]{2}/(\d{11})\b', markdown)
    if uf_cpf_match:
        return uf_cpf_match.group(1)

    # Fallback: tenta encontrar qualquer CPF de 11 dígitos
    generic_cpf_match = re.search(r'\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b', markdown)
    if generic_cpf_match:
        return re.sub(r'\D', '', generic_cpf_match.group(0))
    return None

async def ocr_pipeline(file, salvar_markdown=True) -> Dict[str, Any]:
    """Pipeline completo: processa arquivo, extrai info, aplica fallbacks, salva markdown."""
    # Corrige o manuseio de UploadFile do FastAPI
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as temp:
        content = await file.read()  # Lê o conteúdo do UploadFile de forma assíncrona
        temp.write(content)    # Escreve o conteúdo no arquivo temporário
        temp_path = temp.name

    try:
        markdown = processar_arquivo_docling(temp_path)
    finally:
        os.remove(temp_path) # Garante que o arquivo temporário seja removido

    # Salvar markdown
    caminho_md = None
    if salvar_markdown:
        os.makedirs("ocr_resultados", exist_ok=True)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_nome = os.path.splitext(file.filename)[0]
        caminho_md = f"ocr_resultados/ocr_{base_nome}_{timestamp}.md"
        with open(caminho_md, "w", encoding="utf-8") as f:
            f.write(markdown)
            
    # Extrair CPF localmente
    cpf_extraido = extrair_cpf_regex(markdown)

    # Extrair exames via IA
    exames_info = extrair_exames_ia(markdown)
    exames_extraidos = exames_info.get("exames", [])

    info = {
        "cpf": cpf_extraido,
        "exames": exames_extraidos,
        "markdown_content": markdown # Adiciona o markdown para o orquestrador usar
    }

    if "erro" in exames_info:
        info["erro"] = exames_info["erro"]

    if caminho_md:
        info["markdown_salvo_em"] = caminho_md
    # Libera memória da GPU após cada processamento
    torch.cuda.empty_cache()
    return info

PROMPT_EXTRAIR_TODOS_CPFS = """
Você é um assistente de extração de dados altamente preciso.
Sua tarefa é extrair TODOS os CPFs (apenas números, sem pontuação) de um texto.
Retorne uma lista de CPFs encontrados.
Responda APENAS com um objeto JSON válido, sem nenhum texto adicional antes ou depois.
O formato do JSON deve ser: {\"cpfs\": [\"<cpf1>\", \"<cpf2>\"]}.
Se nenhum CPF for encontrado, use uma lista vazia [] para a chave \"cpfs\".
"""

async def extrair_todos_cpfs_ia(markdown: str, exclude_cpf: Optional[str] = None) -> List[str]:
    """Extrai todos os CPFs do markdown usando LLM, opcionalmente excluindo um CPF."""
    user_prompt = f"""Texto:\n{markdown}"""
    if exclude_cpf:
        user_prompt += f"\nExcluir CPF: {exclude_cpf}"

    try:
        response = client.chat.completions.create(
            model=MODELO_GPT,
            messages=[
                {"role": "system", "content": PROMPT_EXTRAIR_TODOS_CPFS},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        cpfs = [cpf for cpf in data.get("cpfs", []) if cpf != exclude_cpf]
        return cpfs
    except json.JSONDecodeError:
        return []
    except Exception as e:
        print(f"Erro ao extrair todos os CPFs via IA: {e}")
        return [] 