# Guia de Migração: Docling OCR → AWS Textract
## ProntuAI Back-end - Análise Técnica Completa

**Data Criação:** 2025-11-11
**Última Atualização:** 2025-11-12
**Versão:** 3.0 FINAL
**Autor:** Documentação Técnica BRMED
**Status:** ✅ **MIGRAÇÃO COMPLETA E FUNCIONANDO EM PRODUÇÃO**

---

## 🎯 STATUS DA MIGRAÇÃO

### ✅ MIGRAÇÃO CONCLUÍDA COM SUCESSO! 🎉

**Data Conclusão:** 12/11/2025
**Tempo Total:** ~4 horas
**Status:** Sistema 100% operacional com AWS Textract

---

### ✅ Fase 1: PREPARAÇÃO (Feature Toggle) - **CONCLUÍDA**
**Data:** 12/11/2025
**Tempo:** ~2 horas

**Implementações Realizadas:**
- ✅ boto3 adicionado ao requirements.txt (versão 1.40.71 instalada)
- ✅ PyPDF2 adicionado para reparo de PDFs (versão 3.0.1)
- ✅ Variáveis AWS configuradas em .env e config.py (incluindo AWS_S3_BUCKET)
- ✅ Clientes Textract + S3 inicializados condicionalmente em ocr_service.py
- ✅ Função `textract_to_markdown()` implementada
- ✅ Função `reparar_pdf_para_textract()` implementada com PyPDF2
- ✅ Pipeline `ocr_pipeline()` modificado com feature toggle
- ✅ Limpeza de GPU condicional (apenas para Docling)
- ✅ Sistema operando em modo dual (Docling + Textract)

**Configuração AWS:**
```bash

# Feature Toggle: use "true" para ativar Textract, "false" para usar Docling
USE_TEXTRACT=true
```

**Arquivos Modificados (Fase 1):**
- `requirements.txt` - boto3>=1.34.0, PyPDF2>=3.0.0
- `.env` - Variáveis AWS completas
- `app/core/config.py` - Settings AWS + S3
- `app/services/ocr_service.py` - Clientes AWS, funções de reparo e processamento

---

### ✅ Fase 2: IMPLEMENTAÇÃO API ASSÍNCRONA - **CONCLUÍDA**
**Data:** 12/11/2025
**Tempo:** ~1 hora

**Problema Identificado:**
- `detect_document_text` (API síncrona) não suporta PDFs, apenas imagens
- Necessário usar `start_document_text_detection` (API assíncrona) + S3

**Implementações Realizadas:**
- ✅ Função `aguardar_job_textract()` - Polling com timeout de 2 minutos
- ✅ Função `coletar_resultados_textract()` - Coleta paginada de blocos
- ✅ Função `processar_arquivo_textract()` reescrita com fluxo completo:
  1. Reparo de PDF com PyPDF2 (remove criptografia/proteções)
  2. Upload para S3 com nome único: `textract-temp/{timestamp}_{uuid}_{filename}`
  3. Start job assíncrono: `start_document_text_detection()`
  4. Aguarda conclusão: polling com `get_document_text_detection()`
  5. Coleta resultados paginados
  6. Limpeza automática: remove arquivo do S3

**Testes de Permissões AWS:**
- ✅ Script `test_aws_credentials.py` criado
- ✅ Script `test_aws_bucket_access.py` criado
- ✅ Bucket `brmed-exam-ocr` validado com operações: Upload, Read, Delete
- ✅ Todas as permissões S3 funcionando

**Arquivos Modificados (Fase 2):**
- `app/services/ocr_service.py` - Linhas 210-400: API assíncrona completa

---

### ✅ Fase 3: CORREÇÃO BACKEND/FRONTEND - **CONCLUÍDA**
**Data:** 12/11/2025
**Tempo:** ~1 hora

**Problema Identificado:**
- Frontend esperava estrutura `DocumentProcessingResult` com `ocr_result`, `brmed_result`, `validation_result`
- Backend retornava estrutura antiga sem compatibilidade TypeScript
- Erro: `result.result.ocr_result.exames_extraidos.map is not a function`

**Implementações Backend:**
- ✅ Estrutura de resposta corrigida em `workflow_service.py`:
  ```python
  resposta_final = {
      "cpf": cpf_final,
      "ocr_result": {
          "text": markdown_content,
          "exames_extraidos": exames_enviados  # Array
      },
      "brmed_result": {
          "exames_obrigatorios": exames_obrigatorios  # Array
      },
      "validation_result": {
          "exames_faltantes": [...],
          "exames_extras": [...],
          "analysis": "..."
      },
      "status": "success" | "error"
  }
  ```

**Implementações Frontend:**
- ✅ Validações defensivas com `Array.isArray()` em TODOS os `.map()`:
  - `components/document-details-modal.tsx` - 8 correções
  - `components/document-details-modal-checagem.tsx` - 8 correções
  - `lib/pdf-generator.ts` - 4 correções
- ✅ Proteção contra estrutura antiga no localStorage
- ✅ Fallback gracioso para arrays vazios

**Arquivos Modificados (Fase 3):**
- Backend: `app/services/workflow_service.py` - Linhas 227-265
- Frontend: 3 arquivos com 20+ correções de validação

---

### 🎯 RESULTADO FINAL

**Status Atual:**
- ✅ Sistema 100% operacional com AWS Textract
- ✅ PDFs processados via S3 + API assíncrona
- ✅ Frontend exibindo resultados corretamente
- ✅ Sem erros de runtime
- ✅ Limpeza automática de arquivos temporários
- ✅ Reparo automático de PDFs problemáticos

**Performance:**
- Upload S3: ~2 segundos (PDF de 0.9MB)
- Processamento Textract: ~3-5 segundos
- Total por documento: ~7-10 segundos

**Custos AWS (estimativa):**
- Textract: $1.50 por 1000 páginas
- S3: Desprezível (arquivos temporários removidos imediatamente)

---

## Índice

0. [🎯 Status da Migração](#-status-da-migração) ⭐ **NOVO**
1. [Visão Geral do Projeto](#1-visão-geral-do-projeto)
2. [Arquitetura Atual do Sistema](#2-arquitetura-atual-do-sistema)
3. [Implementação Atual do OCR (Docling)](#3-implementação-atual-do-ocr-docling)
4. [Fluxo de Dados Completo](#4-fluxo-de-dados-completo)
5. [Contratos de Entrada e Saída](#5-contratos-de-entrada-e-saída)
6. [Pontos de Integração](#6-pontos-de-integração)
7. [Dependências e Requisitos](#7-dependências-e-requisitos)
8. [Lógica de Extração (CPF e Exames)](#8-lógica-de-extração-cpf-e-exames)
9. [Armazenamento e Auditoria](#9-armazenamento-e-auditoria)
10. [Logging e Tratamento de Erros](#10-logging-e-tratamento-de-erros)
11. [Testes Atuais](#11-testes-atuais)
12. [**MIGRAÇÃO: Arquivos a Modificar**](#12-migração-arquivos-a-modificar)
13. [**MIGRAÇÃO: Mudanças Necessárias**](#13-migração-mudanças-necessárias)
14. [**MIGRAÇÃO: Estratégia Faseada**](#14-migração-estratégia-faseada)
15. [**MIGRAÇÃO: Riscos e Considerações**](#15-migração-riscos-e-considerações)
16. [**MIGRAÇÃO: Exemplo de Implementação**](#16-migração-exemplo-de-implementação)
17. [**✅ MIGRAÇÃO: Implementação Realizada**](#17-migração-implementação-realizada) ⭐ **NOVO**
18. [**📋 Como Testar a Migração**](#18-como-testar-a-migração) ⭐ **NOVO**
19. [Referências Técnicas](#19-referências-técnicas)

---

## 1. Visão Geral do Projeto

### 1.1 O que é o ProntuAI?

**ProntuAI** é uma plataforma de processamento inteligente de documentos médicos para a BRMED (empresa de medicina ocupacional). O sistema valida documentos de exames médicos de pacientes através de:

1. **Extração via OCR**: Converte documentos em texto estruturado
2. **Consulta BRNET**: Busca exames obrigatórios no sistema de autorizações BRMED
3. **Validação Inteligente**: Compara exames usando similaridade vetorial (FAISS) + GPT

### 1.2 Tecnologias Principais

| Camada | Tecnologia |
|--------|------------|
| **Framework** | FastAPI + Python 3.11+ |
| **OCR Atual** | Docling 2.0.0 + PyTorch 2.4.1 (CUDA) |
| **IA/LLM** | OpenAI GPT-4o-mini + text-embedding-3-large |
| **Busca Vetorial** | FAISS (GPU) com L2 distance |
| **Web Scraping** | Playwright (chromium) |
| **Servidor** | Uvicorn (ASGI) |

### 1.3 Estrutura de Diretórios

```
back-end/
├── app/
│   ├── api/                    # Rotas FastAPI
│   │   ├── v1_ocr.py          # Endpoint OCR standalone
│   │   ├── v1_brmed.py        # Endpoint workflow completo
│   │   ├── v1_validacao.py    # Endpoint validação
│   │   └── v1_faq.py          # Endpoint FAQ RAG
│   ├── services/              # Lógica de negócio
│   │   ├── ocr_service.py     # ⚠️ ARQUIVO PRINCIPAL PARA MIGRAÇÃO
│   │   ├── brmed_service.py   # Automação Playwright
│   │   ├── validacao_service.py # Comparação de exames
│   │   ├── faq_service.py     # Sistema de FAQ
│   │   └── workflow_service.py # Orquestração do pipeline
│   ├── core/                  # Configuração compartilhada
│   │   ├── config.py          # ⚠️ Adicionar variáveis AWS
│   │   ├── clients.py         # Cliente OpenAI (shared)
│   │   └── logging.py         # Configuração de logs
│   └── models/                # Modelos de dados (vazio)
├── data/                      # Índices FAISS
│   ├── faq_index.faiss        # FAQ (L2 distance)
│   ├── faq_data.pkl
│   ├── exam_similarity_index.faiss # Sinônimos de exames
│   └── exam_similarity_data.pkl
├── scripts/                   # Scripts de geração de índices
├── tests/                     # Suite de testes pytest
│   └── test_ocr.py           # ⚠️ Atualizar mocks
├── ocr_resultados/           # ⚠️ Saída de markdown do OCR (12MB)
├── auditoria_validacao/      # Logs de validação (JSON)
├── resultados/               # Saída BRMED (JSON + texto)
├── logs/                     # Logs da aplicação
├── requirements.txt          # ⚠️ Remover Docling/PyTorch, adicionar boto3
├── .env                      # ⚠️ Adicionar credenciais AWS
└── main.py                   # Inicialização FastAPI
```

---

## 2. Arquitetura Atual do Sistema

### 2.1 Pipeline Completo (End-to-End)

```
┌─────────────────────────────────────────────────────────────────┐
│ FRONTEND (Next.js)                                               │
│ POST /v1/processar-documento                                    │
│ Body: FormData(arquivo) + exames_obrigatorios: JSON string     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ API ENDPOINT: v1_brmed.py:12                                    │
│ processar_documento_completo_api()                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ WORKFLOW SERVICE: workflow_service.py:130                       │
│ processar_documento_completo()                                  │
│                                                                 │
│  ╔═══════════════════════════════════════════════════════╗     │
│  ║ STEP 1: OCR (Progresso: 10-30%)                      ║     │
│  ║ ▶ ocr_service.ocr_pipeline(arquivo)                  ║     │
│  ║                                                       ║     │
│  ║   Input:  FastAPI UploadFile                         ║     │
│  ║   Output: {cpf, exames[], markdown_content}          ║     │
│  ║                                                       ║     │
│  ║   Subprocessos:                                       ║     │
│  ║   1. Conversão Docling (PDF → Markdown)              ║     │
│  ║   2. Extração CPF (Regex + LLM fallback)             ║     │
│  ║   3. Extração Exames (OpenAI GPT)                    ║     │
│  ║   4. Salvamento markdown (ocr_resultados/)           ║     │
│  ╚═══════════════════════════════════════════════════════╝     │
│                             │                                   │
│                             ▼                                   │
│  ╔═══════════════════════════════════════════════════════╗     │
│  ║ STEP 2: BRMED Query (Progresso: 40-60%)              ║     │
│  ║ ▶ brmed_service.consultar_exames_brmed(cpf)          ║     │
│  ║                                                       ║     │
│  ║   Playwright automation → BRNET web scraping         ║     │
│  ║   Retorna: Lista de exames obrigatórios do paciente  ║     │
│  ║                                                       ║     │
│  ║   Fallback CPF:                                       ║     │
│  ║   - Se falhar, extrai TODOS os CPFs do markdown      ║     │
│  ║   - Tenta cada CPF alternativo até sucesso           ║     │
│  ╚═══════════════════════════════════════════════════════╝     │
│                             │                                   │
│                             ▼                                   │
│  ╔═══════════════════════════════════════════════════════╗     │
│  ║ STEP 3: Validação (Progresso: 70-90%)                ║     │
│  ║ ▶ validacao_service.validar_exames()                 ║     │
│  ║                                                       ║     │
│  ║   1. Busca sinônimos no FAISS (exam_similarity)      ║     │
│  ║   2. Comparação via OpenAI GPT com contexto RAG      ║     │
│  ║   3. Status: encontrado | faltante | extra_no_ocr    ║     │
│  ║   4. Salvamento auditoria (JSON)                     ║     │
│  ╚═══════════════════════════════════════════════════════╝     │
│                             │                                   │
│                             ▼                                   │
│  ╔═══════════════════════════════════════════════════════╗     │
│  ║ STEP 4: Resposta Final (Progresso: 90-100%)          ║     │
│  ║                                                       ║     │
│  ║   Retorna: {                                          ║     │
│  ║     cpf_processado,                                   ║     │
│  ║     exames_ocr,                                       ║     │
│  ║     exames_brnet,                                     ║     │
│  ║     analise_comparacao,                               ║     │
│  ║     tabela_comparacao[],                              ║     │
│  ║     decisao_final,                                    ║     │
│  ║     erro                                              ║     │
│  ║   }                                                   ║     │
│  ╚═══════════════════════════════════════════════════════╝     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Serviços Independentes

O sistema também expõe endpoints individuais:

| Endpoint | Arquivo | Propósito |
|----------|---------|-----------|
| `POST /v1/ocr` | `v1_ocr.py:7` | OCR standalone (não usado pelo front) |
| `POST /v1/brmed` | `v1_brmed.py:93` | Consulta BRMED standalone |
| `POST /v1/validacao` | `v1_validacao.py:8` | Validação standalone |
| `POST /v1/faq` | `v1_faq.py:8` | Sistema FAQ RAG (não relacionado ao OCR) |

---

## 3. Implementação Atual do OCR (Docling)

### 3.1 Arquivo Principal: `app/services/ocr_service.py`

**Total de Linhas:** 218
**Funções Principais:** 6

### 3.2 Mapeamento de Funções

| Função | Linhas | Tipo | Descrição | Impacto Migração |
|--------|--------|------|-----------|------------------|
| `processar_arquivo_docling()` | 73-92 | Sync | **CORE**: Conversão Docling PDF→Markdown | 🔴 **SUBSTITUIR** |
| `ocr_pipeline()` | 129-185 | Async | Orquestração principal do OCR | 🟡 **MODIFICAR** |
| `extrair_cpf_regex()` | 117-127 | Sync | Extração CPF via regex (markdown) | 🟢 **MANTER** |
| `extrair_cpf_ia()` | 51-70 | Sync | Fallback LLM para CPF | 🟢 **MANTER** |
| `extrair_exames_ia()` | 94-115 | Sync | Extração exames via GPT | 🟢 **MANTER** |
| `extrair_todos_cpfs_ia()` | 196-219 | Async | Extração múltiplos CPFs (fallback workflow) | 🟢 **MANTER** |

### 3.3 Uso do Docling (Linhas Específicas)

#### Imports (Linhas 6-7)
```python
from docling.document_converter import DocumentConverter
import torch  # Para CUDA memory cleanup
```

#### Configuração (Linhas 75-89)
```python
def processar_arquivo_docling(file) -> str:
    """
    Converte documento (PDF/imagem) em markdown usando Docling 2.0

    Args:
        file: Caminho do arquivo no disco

    Returns:
        str: Conteúdo markdown extraído
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption

    # Configuração do pipeline
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True  # OCR habilitado
    pipeline_options.do_table_structure = False  # Desabilitado por performance
    pipeline_options.table_structure_options.do_cell_matching = False

    # Inicialização do conversor
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    # Conversão
    resultado = converter.convert(file)
    markdown = resultado.document.export_to_markdown()

    return markdown
```

#### Limpeza de Memória GPU (Linha 182)
```python
# Dentro de ocr_pipeline(), após processamento
if torch.cuda.is_available():
    torch.cuda.empty_cache()
```

### 3.4 Variável de Ambiente PyTorch (Linha 3)
```python
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
```

**Motivo:** Docling usa modelos PyTorch para OCR, exigindo gerenciamento de memória CUDA.

---

## 4. Fluxo de Dados Completo

### 4.1 Fluxo Interno do `ocr_pipeline()`

```python
async def ocr_pipeline(file: UploadFile, salvar_markdown: bool = True) -> Dict[str, Any]:
    """
    Pipeline completo de OCR com 8 etapas

    Linha 129-185 em ocr_service.py
    """

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 1: Salvar UploadFile em disco (Linhas 134-138)
    # ═══════════════════════════════════════════════════════════════
    conteudo = await file.read()  # Leitura assíncrona
    _, extensao = os.path.splitext(file.filename)

    with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as temp:
        temp.write(conteudo)
        temp_path = temp.name

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 2: Conversão Docling (Linha 141)
    # ⚠️ PRINCIPAL PONTO DE SUBSTITUIÇÃO PARA TEXTRACT
    # ═══════════════════════════════════════════════════════════════
    markdown = processar_arquivo_docling(temp_path)
    # Saída típica: ~850 bytes (simples) até ~6KB (complexo)

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 3: Limpar arquivo temporário (Linha 144)
    # ═══════════════════════════════════════════════════════════════
    os.unlink(temp_path)

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 4: Salvar markdown em disco [OPCIONAL] (Linhas 148-156)
    # ═══════════════════════════════════════════════════════════════
    if salvar_markdown:
        os.makedirs("ocr_resultados", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_nome = os.path.splitext(file.filename)[0]
        caminho_md = f"ocr_resultados/ocr_{base_nome}_{timestamp}.md"

        with open(caminho_md, "w", encoding="utf-8") as f:
            f.write(markdown)

        logger.info(f"[OCR] Markdown salvo em: {caminho_md}")

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 5: Extrair CPF via Regex (Linhas 159-161)
    # ═══════════════════════════════════════════════════════════════
    cpf_extraido = extrair_cpf_regex(markdown)
    # Prioridade 1: Padrão UF/CPF (ex: CE/12345678901)
    # Prioridade 2: CPF formatado (111.222.333-44)

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 6: Extrair Exames via OpenAI (Linhas 164-167)
    # ═══════════════════════════════════════════════════════════════
    resposta_exames = extrair_exames_ia(markdown)
    exames_extraidos = resposta_exames.get("exames", [])
    # LLM identifica headers (##) e extrai nomes de exames
    # Retorna: ["HEMOGRAMA", "GLICOSE", "UREIA"]

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 7: Limpeza de Memória GPU (Linha 182)
    # ⚠️ REMOVER NA MIGRAÇÃO (específico do PyTorch)
    # ═══════════════════════════════════════════════════════════════
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 8: Retornar Resultado (Linhas 169-179)
    # ═══════════════════════════════════════════════════════════════
    return {
        "cpf": cpf_extraido,                    # str ou None
        "exames": exames_extraidos,             # list[str]
        "markdown_content": markdown,           # str (texto completo)
        "markdown_salvo_em": caminho_md if salvar_markdown else None,
        "erro": None  # ou mensagem de erro se falhar
    }
```

### 4.2 Formato do Markdown Gerado pelo Docling

**Exemplo Real** (`ocr_resultados/ocr_periodico_ana_20251029_085353.md`):

```markdown
Cliente

:ANABEATRIZDESOUSADASILVA

Solicitante ：

Convenio

:ArcelormittalBrasil S.A

Idade

：49A1M4D

Unidade

:QualityFortaleza

## HEMOGRAMA

Metodo:Contagem automatizada atraves deimpedancia eletrica ecitometria de fluxo

## Observacao

## Eritrograma

ValoresdeReferenci

Hematocrito

38，5号

36,0A.46,0

Hemoglobina

11，6g/dL

12,0A16,0g/dL

Hemaclas

3.650.000/mm3

4.000.000A5.500.000/mm3
```

**Características Importantes:**
- Headers de exames com prefixo `##` (markdown H2)
- Texto não estruturado com espaçamento irregular
- Caracteres especiais (：，号)
- Tamanho médio: 850 bytes - 6KB

---

## 5. Contratos de Entrada e Saída

### 5.1 Input: `ocr_pipeline()`

```python
async def ocr_pipeline(
    file: UploadFile,           # FastAPI UploadFile object
    salvar_markdown: bool = True # Salvar markdown no disco?
) -> Dict[str, Any]:
```

**Propriedades do `UploadFile` Utilizadas:**
- `file.filename` → Nome original do arquivo
- `await file.read()` → Conteúdo binário do arquivo
- `file` → Objeto completo (passado para Docling após salvar em /tmp)

### 5.2 Output: `ocr_pipeline()`

```python
{
    "cpf": "12345678901",  # str | None - CPF sem formatação

    "exames": [            # list[str] - Nomes de exames extraídos
        "HEMOGRAMA",
        "GLICOSE",
        "UREIA"
    ],

    "markdown_content": "## HEMOGRAMA\n...",  # str - Markdown completo

    "markdown_salvo_em": "ocr_resultados/ocr_file_20251111.md",  # str | None

    "erro": None  # str | None - Mensagem de erro se falhar
}
```

**Nota Crítica:** Este contrato **DEVE ser mantido** na migração para preservar compatibilidade com `workflow_service.py` e `v1_ocr.py`.

### 5.3 Consumidores do Output

#### Workflow Service (Linha 154-157)
```python
ocr_resultado = await ocr_service.ocr_pipeline(arquivo)

cpf_inicial = ocr_resultado.get("cpf")
exames_enviados = ocr_resultado.get("exames", [])
markdown_content = ocr_resultado.get("markdown_content", "")  # Para fallback CPF
```

#### API OCR (Linha 15)
```python
resultado = await ocr_service.ocr_pipeline(arquivo)
return resultado  # Retorno direto ao cliente
```

---

## 6. Pontos de Integração

### 6.1 Chamadas Diretas ao OCR Service

```
ocr_service.py
    ↑
    │ import from app.services import ocr_service
    │
    ├─── workflow_service.py:4 (import)
    │    └─── workflow_service.py:154 (chamada)
    │         └─── await ocr_service.ocr_pipeline(arquivo)
    │
    └─── v1_ocr.py:2 (import)
         └─── v1_ocr.py:15 (chamada)
              └─── await ocr_service.ocr_pipeline(arquivo)
```

### 6.2 Fluxo de Dados Entre Serviços

```
Frontend (Next.js)
    ↓ POST /v1/processar-documento
v1_brmed.py:processar_documento_completo_api()
    ↓ workflow_service.processar_documento_completo()
    │
    ├─► ocr_service.ocr_pipeline() ────────┐
    │   Retorna: {cpf, exames[], markdown} │
    │                                       │
    ├─► brmed_service.consultar_exames_brmed(cpf) ─► Usa CPF do OCR
    │   │ Fallback: ocr_service.extrair_todos_cpfs_ia(markdown) ─► Usa markdown do OCR
    │   Retorna: {exames_brnet[]}
    │
    └─► validacao_service.validar_exames(
            cpf,
            exames_obrigatorios,  # Do frontend
            exames_enviados,      # Do OCR
            exames_brnet          # Do BRMED
        )
        Retorna: {status_liberado, exames_comparativo[], mensagem}
```

### 6.3 Dependência do Markdown Content

**Uso Crítico:** O campo `markdown_content` é usado pelo **mecanismo de fallback de CPF** no workflow:

```python
# workflow_service.py:184-201
if "erro" in brmed_resultado or not exames_brnet_extraidos:
    # Se falhar com CPF inicial, tenta todos os CPFs do documento
    cpfs_alternativos = await ocr_service.extrair_todos_cpfs_ia(
        markdown_content,  # ⚠️ Requer markdown do OCR
        exclude_cpf=cpf_inicial
    )

    for alt_cpf in cpfs_alternativos:
        brmed_resultado = await brmed_service.consultar_exames_brmed(alt_cpf)
        if "exames" in brmed_resultado:
            cpf_processado = alt_cpf
            break
```

**Implicação para Migração:** Mesmo que o Textract retorne JSON, deve-se preservar/gerar um campo de texto plano para esta lógica funcionar.

---

## 7. Dependências e Requisitos

### 7.1 Dependências Python (requirements.txt)

#### Dependências Relacionadas ao OCR (A REMOVER)

```txt
# Linha 2 - CUDA index para PyTorch
--extra-index-url https://download.pytorch.org/whl/cu124

# Linha 3 - PyTorch (usado pelo Docling)
torch==2.4.1

# Linha 4 - TorchVision (dependência do Docling)
torchvision==0.19.1

# Linha 25 - Docling OCR (BIBLIOTECA PRINCIPAL)
docling==2.0.0
```

**Tamanho Total:** ~3.5GB
**Requisito de Hardware:** GPU NVIDIA com CUDA 12.4

#### Dependências a ADICIONAR (AWS Textract)

```txt
# AWS SDK para Python
boto3>=1.34.0
```

**Tamanho Total:** ~50MB
**Requisito de Hardware:** Nenhum (API cloud)

### 7.2 Variáveis de Ambiente

#### Atuais (`.env`)

```env
OPENAI_API_KEY=your_key
BRMED_USERNAME=your_user
BRMED_PASSWORD=your_pass
MODELO_GPT=gpt-4o-mini
MODELO_EMBEDDING=text-embedding-3-large
```

#### A Adicionar (AWS Textract)

```env
# Credenciais AWS
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Opcional: S3 bucket para staging (se usar async Textract)
AWS_S3_BUCKET=prontuai-textract-staging
```

### 7.3 Imports a Substituir

#### Arquivo: `app/services/ocr_service.py`

**Remover:**
```python
from docling.document_converter import DocumentConverter  # Linha 6
import torch  # Linha 7
```

**Adicionar:**
```python
import boto3
from botocore.exceptions import ClientError
```

**Dentro de `processar_arquivo_docling()` (Linhas 75-77):**

**Remover:**
```python
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import PdfFormatOption
```

**Adicionar:**
```python
# Inicialização do cliente Textract (fazer no início do arquivo)
textract_client = boto3.client(
    'textract',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)
```

---

## 8. Lógica de Extração (CPF e Exames)

### 8.1 Extração de CPF

#### Método Primário: Regex (Linhas 117-127)

```python
def extrair_cpf_regex(markdown: str) -> str:
    """
    Extrai CPF de texto markdown com 2 prioridades

    ⚠️ Esta função trabalha com texto plano (markdown)
    ⚠️ Na migração, garantir que Textract gere texto compatível
    """

    # Prioridade 1: Padrão UF/CPF (mais confiável)
    # Exemplo: "CE/12345678901"
    uf_cpf_match = re.search(r'\b[A-Z]{2}/(\d{11})\b', markdown)
    if uf_cpf_match:
        return uf_cpf_match.group(1)  # Retorna apenas os 11 dígitos

    # Prioridade 2: CPF formatado genérico
    # Exemplos: "123.456.789-01", "123 456 789 01", "12345678901"
    generic_cpf_match = re.search(
        r'\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b',
        markdown
    )
    if generic_cpf_match:
        # Remove pontuação, mantém apenas dígitos
        return re.sub(r'\D', '', generic_cpf_match.group(0))

    return None
```

**Estratégia de Migração:**
- **Opção A (Recomendada):** Converter blocos Textract em texto plano e manter regex
- **Opção B:** Reescrever regex para trabalhar diretamente com JSON do Textract
- **Opção C:** Usar apenas LLM (menos confiável, mais caro)

#### Método Fallback: OpenAI GPT (Linhas 51-70)

```python
def extrair_cpf_ia(markdown: str) -> str:
    """
    Fallback LLM quando regex não encontra CPF

    ⚠️ Este método é agnóstico ao formato - funciona com qualquer texto
    ⚠️ Não requer mudanças na migração (continua recebendo texto)
    """

    prompt = f"""
    Extraia o CPF do paciente no seguinte documento médico.
    Retorne APENAS o CPF sem formatação (11 dígitos).

    Documento:
    {markdown}

    Retorne no formato JSON: {{"cpf": "12345678901"}}
    """

    resposta = client.chat.completions.create(
        model=settings.MODELO_GPT,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0
    )

    resultado = json.loads(resposta.choices[0].message.content)
    return resultado.get("cpf")
```

### 8.2 Extração de Exames

#### Método Único: OpenAI GPT (Linhas 94-115)

```python
def extrair_exames_ia(markdown: str) -> Dict[str, Any]:
    """
    Extrai lista de nomes de exames usando LLM

    ⚠️ Depende de headers markdown (##) gerados pelo Docling
    ⚠️ Na migração, converter Textract para formato similar
    """

    # Prompt definido em PROMPT_EXTRAIR_EXAMES (Linhas 24-37)
    prompt = f"""
    Você é um assistente especializado em extrair informações de documentos médicos.

    Analise o seguinte documento em formato Markdown e identifique TODOS os nomes
    dos exames médicos realizados.

    Documento:
    {markdown}

    Regras:
    - Procure por headers com ## (exemplo: "## HEMOGRAMA")
    - Se houver formato "EXAME - DATA", extraia apenas o nome do exame
    - Retorne TODOS os exames encontrados em MAIÚSCULAS
    - Retorne no formato JSON: {{"exames": ["HEMOGRAMA", "GLICOSE"]}}
    """

    resposta = client.chat.completions.create(
        model=settings.MODELO_GPT,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0
    )

    return json.loads(resposta.choices[0].message.content)
```

**Consideração para Migração:**
- O LLM é **flexível** e pode interpretar diferentes formatos
- **Recomendação:** Converter blocos Textract em markdown com headers `##` para consistência
- **Alternativa:** Ajustar prompt para trabalhar com texto plano sem formatação

### 8.3 Extração de Múltiplos CPFs (Fallback Workflow)

**Função:** `extrair_todos_cpfs_ia()` (Linhas 196-219)

```python
async def extrair_todos_cpfs_ia(
    markdown: str,
    exclude_cpf: Optional[str] = None
) -> List[str]:
    """
    Extrai TODOS os CPFs encontrados no documento
    Usado quando CPF inicial falha na consulta BRMED

    ⚠️ Função mantém-se inalterada (recebe texto, retorna lista)
    """

    prompt = f"""
    Extraia TODOS os CPFs encontrados no seguinte documento médico.
    Retorne cada CPF sem formatação (apenas 11 dígitos).

    Documento:
    {markdown}

    Formato JSON: {{"cpfs": ["12345678901", "98765432100"]}}
    """

    resposta = await client.chat.completions.create(...)
    resultado = json.loads(resposta.choices[0].message.content)
    cpfs = resultado.get("cpfs", [])

    # Filtrar CPF que já foi tentado
    if exclude_cpf:
        cpfs = [cpf for cpf in cpfs if cpf != exclude_cpf]

    return cpfs
```

---

## 9. Armazenamento e Auditoria

### 9.1 Diretório de Saída: `ocr_resultados/`

**Localização:** `/home/brmed/Área de trabalho/prontuai/back-end/ocr_resultados/`

**Conteúdo Atual:**
- 300+ arquivos markdown
- Tamanho total: ~12MB
- Formato: `ocr_{nome_original}_{timestamp}.md`

**Exemplo de Nomes:**
```
ocr_periodico_ana_20251029_085353.md
ocr_exames_joao_20251030_162650.md
ocr_documento_20251111_094512.md
```

**Lógica de Salvamento** (ocr_service.py:148-156):
```python
if salvar_markdown:
    os.makedirs("ocr_resultados", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_nome = os.path.splitext(file.filename)[0]
    caminho_md = f"ocr_resultados/ocr_{base_nome}_{timestamp}.md"

    with open(caminho_md, "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info(f"[OCR] Markdown salvo em: {caminho_md}")
```

### 9.2 Decisão de Migração: Formato de Auditoria

**Opções:**

#### Opção A: Manter Markdown (Recomendada)
```python
# Converter Textract JSON → Markdown
markdown = textract_to_markdown(textract_response)

# Salvar como antes
with open(caminho_md, "w", encoding="utf-8") as f:
    f.write(markdown)
```

**Vantagens:**
- Compatibilidade com ferramentas existentes
- Formato legível para humanos
- Não quebra lógica de regex/LLM

**Desvantagens:**
- Perda de metadados estruturados do Textract
- Conversão adicional necessária

#### Opção B: Salvar JSON Textract
```python
# Salvar resposta bruta do Textract
caminho_json = f"ocr_resultados/ocr_{base_nome}_{timestamp}.json"
with open(caminho_json, "w", encoding="utf-8") as f:
    json.dump(textract_response, f, indent=2)
```

**Vantagens:**
- Preserva todas as informações (bounding boxes, confiança, etc.)
- Possibilita análises futuras

**Desvantagens:**
- Incompatível com ferramentas existentes que esperam markdown
- Requer atualização de scripts de auditoria

#### Opção C: Dual Storage (Ideal)
```python
# Salvar ambos os formatos
markdown = textract_to_markdown(textract_response)

# 1. Markdown (compatibilidade)
with open(f"ocr_resultados/ocr_{base_nome}_{timestamp}.md", "w") as f:
    f.write(markdown)

# 2. JSON (dados completos)
with open(f"ocr_resultados/ocr_{base_nome}_{timestamp}.json", "w") as f:
    json.dump(textract_response, f, indent=2)
```

**Vantagens:**
- Melhor dos dois mundos
- Auditoria completa

**Desvantagens:**
- Maior uso de espaço em disco (~2x)

### 9.3 Outros Diretórios de Saída

```
back-end/
├── ocr_resultados/          # OCR outputs (markdown)
├── auditoria_validacao/     # Validation audit logs (JSON)
│   └── validacao_{cpf}_{timestamp}.json
├── resultados/              # BRMED scraping outputs
│   ├── {cpf}_{timestamp}.json
│   └── {cpf}_{timestamp}.txt
└── logs/                    # Application logs
    └── app.log
```

**Impacto da Migração:** Nenhum (diretórios não relacionados ao OCR)

---

## 10. Logging e Tratamento de Erros

### 10.1 Configuração de Logs

**Arquivo:** `app/core/logging.py`

```python
import logging
from app.core.config import settings

# Formato de log
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Configuração de handlers
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(settings.LOG_FILE),  # logs/app.log
        logging.StreamHandler()  # Console (stdout)
    ]
)

logger = logging.getLogger(__name__)
```

### 10.2 Eventos de Log no OCR Service

**Logs a Preservar na Migração:**

```python
# Linha 131
logger.info(f"[OCR] Iniciando pipeline OCR para arquivo: {file.filename}")

# Linha 139
logger.info(f"[OCR] Iniciando conversão Docling para: {file.filename}")
# ⚠️ ATUALIZAR: "Iniciando conversão Textract para: ..."

# Linha 142
logger.info(f"[OCR] Conversão Docling concluída. Markdown gerado: {len(markdown)} caracteres")
# ⚠️ ATUALIZAR: "Conversão Textract concluída. ..."

# Linha 156
logger.info(f"[OCR] Markdown salvo em: {caminho_md}")

# Linha 159
logger.info("[OCR] Extraindo CPF via regex...")

# Linha 161
logger.info(f"[OCR] CPF extraído: {cpf_extraido if cpf_extraido else 'Nenhum CPF encontrado'}")

# Linha 164
logger.info("[OCR] Iniciando extração de exames via OpenAI GPT...")

# Linha 167
logger.info(f"[OCR] Exames extraídos: {len(exames_extraidos)} encontrados - {exames_extraidos}")

# Linha 183
logger.info(f"[OCR] Pipeline OCR concluído para: {file.filename}")
```

### 10.3 Tratamento de Erros

#### OCR Service (Silencioso)
```python
try:
    markdown = processar_arquivo_docling(temp_path)
    # ... processamento ...
except Exception as e:
    logger.error(f"[OCR] Erro no processamento: {str(e)}")
    return {"erro": f"Erro no OCR: {str(e)}"}
```

**Comportamento:** NÃO lança exceções, retorna dict com campo `"erro"`.

#### API Layer (HTTPException)
```python
# v1_ocr.py:15-17
resultado = await ocr_service.ocr_pipeline(arquivo)

if "erro" in resultado:
    logger.error(f"Erro no OCR: {resultado['erro']}")
    raise HTTPException(status_code=500, detail=resultado["erro"])

return resultado
```

#### Workflow Layer (Fallback CPF)
```python
# workflow_service.py:184
if "erro" in brmed_resultado:
    # Tenta CPFs alternativos extraídos do markdown
    cpfs_alt = await ocr_service.extrair_todos_cpfs_ia(markdown_content)
    # ...
```

**Recomendação para Migração:** Manter o mesmo padrão de erro (dict com campo `"erro"`).

---

## 11. Testes Atuais

### 11.1 Arquivo de Testes: `tests/test_ocr.py`

**Total de Linhas:** 41
**Casos de Teste:** 3

### 11.2 Estrutura dos Testes

```python
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import UploadFile
from io import BytesIO

# ══════════════════════════════════════════════════════════════
# TESTE 1: Pipeline OCR com Sucesso (Linhas 7-18)
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@patch("app.services.ocr_service.processar_arquivo_docling", return_value="## HEMOGRAMA\n## GLICOSE")
@patch("app.services.ocr_service.extrair_info_ia", return_value={"cpf": "12345678901", "exames": ["HEMOGRAMA", "GLICOSE"]})
async def test_ocr_pipeline_success(mock_extrair, mock_processar):
    """
    Testa pipeline completo com mocks

    ⚠️ MIGRAÇÃO: Atualizar mock de processar_arquivo_docling
                 para processar_arquivo_textract
    """
    from app.services.ocr_service import ocr_pipeline

    # Mock de UploadFile
    file_content = b"fake pdf content"
    upload_file = UploadFile(filename="test.pdf", file=BytesIO(file_content))

    # Execução
    resultado = await ocr_pipeline(upload_file, salvar_markdown=False)

    # Asserções
    assert resultado["cpf"] == "12345678901"
    assert len(resultado["exames"]) == 2
    assert "HEMOGRAMA" in resultado["exames"]

# ══════════════════════════════════════════════════════════════
# TESTE 2: Fallback de CPF (Linhas 21-31)
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@patch("app.services.ocr_service.processar_arquivo_docling", return_value="CPF: 123.456.789-01")
@patch("app.services.ocr_service.extrair_info_ia", return_value={"cpf": None, "exames": []})
async def test_ocr_pipeline_fallback_cpf(mock_extrair, mock_processar):
    """
    Testa extração de CPF via regex quando LLM retorna None

    ⚠️ MIGRAÇÃO: Mock permanece o mesmo (testa regex, não Docling)
    """
    from app.services.ocr_service import ocr_pipeline

    upload_file = UploadFile(filename="test.pdf", file=BytesIO(b"content"))
    resultado = await ocr_pipeline(upload_file, salvar_markdown=False)

    # Verifica que regex capturou o CPF
    assert resultado["cpf"] == "12345678901"  # Sem formatação

# ══════════════════════════════════════════════════════════════
# TESTE 3: Endpoint API (Linhas 34-41)
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_ocr_route(client):
    """
    Testa endpoint POST /v1/ocr

    ⚠️ MIGRAÇÃO: Atualizar mock interno
    """
    with patch("app.services.ocr_service.ocr_pipeline", new_callable=AsyncMock) as mock_pipeline:
        mock_pipeline.return_value = {"cpf": "12345678901", "exames": ["HEMOGRAMA"]}

        response = client.post("/v1/ocr", files={"arquivo": ("test.pdf", b"content", "application/pdf")})

        assert response.status_code == 200
        assert response.json()["cpf"] == "12345678901"
```

### 11.3 Mocks a Atualizar

**Antes (Docling):**
```python
@patch("app.services.ocr_service.processar_arquivo_docling", return_value="## HEMOGRAMA")
```

**Depois (Textract):**
```python
@patch("app.services.ocr_service.processar_arquivo_textract", return_value="## HEMOGRAMA")
# OU, se retornar JSON:
@patch("app.services.ocr_service.processar_arquivo_textract", return_value={
    "Blocks": [
        {"BlockType": "LINE", "Text": "HEMOGRAMA", ...},
        # ...
    ]
})
```

---

## 12. MIGRAÇÃO: Arquivos a Modificar

### 12.1 Tabela Resumida

| Arquivo | Impacto | Linhas a Alterar | Descrição |
|---------|---------|------------------|-----------|
| `app/services/ocr_service.py` | 🔴 **ALTO** | 6-7, 73-92, 182 | Substituir Docling por Textract |
| `requirements.txt` | 🔴 **ALTO** | 2-4, 25 | Remover torch/docling, adicionar boto3 |
| `app/core/config.py` | 🟡 **MÉDIO** | Adicionar ~5 linhas | Variáveis AWS |
| `.env` | 🟡 **MÉDIO** | Adicionar 3-4 linhas | Credenciais AWS |
| `tests/test_ocr.py` | 🟢 **BAIXO** | 8, 22 | Atualizar nomes de mocks |

### 12.2 Arquivos NÃO Impactados (Compatibilidade Mantida)

- `app/services/workflow_service.py` - Usa contrato `ocr_pipeline()`
- `app/services/brmed_service.py` - Independente
- `app/services/validacao_service.py` - Independente
- `app/services/faq_service.py` - Independente
- `app/api/v1_ocr.py` - Usa contrato `ocr_pipeline()`
- `app/api/v1_brmed.py` - Via workflow
- `main.py` - Sem mudanças

---

## 13. MIGRAÇÃO: Mudanças Necessárias

### 13.1 Arquivo: `app/services/ocr_service.py`

#### Mudança 1: Imports (Linhas 6-7)

**REMOVER:**
```python
from docling.document_converter import DocumentConverter
import torch
```

**ADICIONAR:**
```python
import boto3
from botocore.exceptions import ClientError
```

#### Mudança 2: Inicialização Cliente (Adicionar após imports)

**ADICIONAR:**
```python
# Inicializar cliente Textract
textract_client = boto3.client(
    'textract',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)
```

#### Mudança 3: Função de Conversão (Linhas 73-92)

**SUBSTITUIR:**
```python
def processar_arquivo_docling(file) -> str:
    """Converte documento via Docling"""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    resultado = converter.convert(file)
    markdown = resultado.document.export_to_markdown()

    return markdown
```

**POR:**
```python
def processar_arquivo_textract(file_path: str) -> str:
    """
    Converte documento via AWS Textract

    Args:
        file_path: Caminho do arquivo no disco

    Returns:
        str: Conteúdo markdown extraído
    """
    logger.info(f"[OCR] Chamando AWS Textract para: {file_path}")

    try:
        # Ler arquivo binário
        with open(file_path, 'rb') as document:
            documento_bytes = document.read()

        # Chamar Textract (síncrono, até 5MB)
        response = textract_client.detect_document_text(
            Document={'Bytes': documento_bytes}
        )

        # Converter resposta JSON em markdown
        markdown = textract_to_markdown(response)

        logger.info(f"[OCR] Textract concluído. Markdown gerado: {len(markdown)} caracteres")
        return markdown

    except ClientError as e:
        logger.error(f"[OCR] Erro Textract: {e}")
        raise
    except Exception as e:
        logger.error(f"[OCR] Erro inesperado: {e}")
        raise
```

#### Mudança 4: Função de Conversão JSON→Markdown (NOVA)

**ADICIONAR:**
```python
def textract_to_markdown(textract_response: dict) -> str:
    """
    Converte resposta JSON do Textract em markdown
    Preserva formato compatível com lógica de extração existente

    Args:
        textract_response: Resposta completa do detect_document_text()

    Returns:
        str: Texto em formato markdown
    """
    lines = []

    for block in textract_response.get('Blocks', []):
        if block['BlockType'] == 'LINE':
            text = block['Text']

            # Detectar possíveis headers de exames (texto curto, maiúsculas)
            if len(text.split()) <= 4 and text.isupper():
                # Formatar como header markdown (##)
                lines.append(f"\n## {text}\n")
            else:
                # Texto normal
                lines.append(text)

    markdown = '\n'.join(lines)
    return markdown
```

**Nota:** Esta é uma conversão básica. Ajustar conforme necessário baseado em testes com documentos reais.

#### Mudança 5: Chamada na Pipeline (Linha 141)

**SUBSTITUIR:**
```python
markdown = processar_arquivo_docling(temp_path)
```

**POR:**
```python
markdown = processar_arquivo_textract(temp_path)
```

#### Mudança 6: Remover Limpeza GPU (Linha 182)

**REMOVER:**
```python
if torch.cuda.is_available():
    torch.cuda.empty_cache()
```

#### Mudança 7: Atualizar Logs (Linhas 139, 142)

**SUBSTITUIR:**
```python
logger.info(f"[OCR] Iniciando conversão Docling para: {file.filename}")
# ...
logger.info(f"[OCR] Conversão Docling concluída. Markdown gerado: {len(markdown)} caracteres")
```

**POR:**
```python
logger.info(f"[OCR] Iniciando conversão Textract para: {file.filename}")
# ...
logger.info(f"[OCR] Conversão Textract concluída. Markdown gerado: {len(markdown)} caracteres")
```

### 13.2 Arquivo: `requirements.txt`

**REMOVER:**
```txt
--extra-index-url https://download.pytorch.org/whl/cu124  # Linha 2
torch==2.4.1                                             # Linha 3
torchvision==0.19.1                                      # Linha 4
docling==2.0.0                                           # Linha 25
```

**ADICIONAR:**
```txt
boto3>=1.34.0
botocore>=1.34.0
```

### 13.3 Arquivo: `app/core/config.py`

**ADICIONAR (após outras configurações):**
```python
# Configurações AWS Textract
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
AWS_S3_BUCKET: Optional[str] = os.getenv("AWS_S3_BUCKET")  # Para documentos >5MB
```

### 13.4 Arquivo: `.env`

**ADICIONAR:**
```env
# AWS Textract
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1

# Opcional: Para processamento assíncrono de documentos grandes
AWS_S3_BUCKET=prontuai-textract-staging
```

### 13.5 Arquivo: `tests/test_ocr.py`

**SUBSTITUIR (Linha 8):**
```python
@patch("app.services.ocr_service.processar_arquivo_docling", return_value="## HEMOGRAMA\n## GLICOSE")
```

**POR:**
```python
@patch("app.services.ocr_service.processar_arquivo_textract", return_value="## HEMOGRAMA\n## GLICOSE")
```

**SUBSTITUIR (Linha 22):**
```python
@patch("app.services.ocr_service.processar_arquivo_docling", return_value="CPF: 123.456.789-01")
```

**POR:**
```python
@patch("app.services.ocr_service.processar_arquivo_textract", return_value="CPF: 123.456.789-01")
```

---

## 14. MIGRAÇÃO: Estratégia Faseada

### Fase 1: PREPARAÇÃO (Não-Quebrante) ⏱️ 2-3 horas

**Objetivo:** Adicionar suporte ao Textract SEM remover Docling.

#### Tarefas:
1. ✅ Adicionar `boto3` ao `requirements.txt` (manter docling)
   ```bash
   pip install boto3
   ```

2. ✅ Adicionar variáveis AWS ao `.env` e `config.py`
   ```bash
   # Criar credenciais AWS no IAM Console
   # Adicionar ao .env local
   ```

3. ✅ Criar função `processar_arquivo_textract()` **em paralelo** a `processar_arquivo_docling()`
   ```python
   # Em ocr_service.py, adicionar nova função sem remover a antiga
   def processar_arquivo_textract(file_path: str) -> str:
       # Implementação completa (ver seção 13.1)
       pass

   def textract_to_markdown(textract_response: dict) -> str:
       # Conversão JSON→Markdown (ver seção 13.1)
       pass
   ```

4. ✅ Criar flag de feature toggle em `config.py`
   ```python
   USE_TEXTRACT: bool = os.getenv("USE_TEXTRACT", "false").lower() == "true"
   ```

5. ✅ Modificar `ocr_pipeline()` para suportar ambos:
   ```python
   async def ocr_pipeline(file, salvar_markdown=True):
       # ... (salvar temp file) ...

       if settings.USE_TEXTRACT:
           markdown = processar_arquivo_textract(temp_path)
       else:
           markdown = processar_arquivo_docling(temp_path)  # Fallback

       # ... (resto do pipeline) ...
   ```

**Validação:**
```bash
# Testar com Docling (default)
pytest tests/test_ocr.py

# Testar com Textract
export USE_TEXTRACT=true
pytest tests/test_ocr.py
```

---

### Fase 2: IMPLEMENTAÇÃO E TESTES ⏱️ 1-2 dias

**Objetivo:** Validar Textract em ambiente de desenvolvimento.

#### Tarefas:
1. ✅ Testar conversão Textract→Markdown com documentos reais
   ```bash
   # Usar documentos do ocr_resultados/ como baseline
   python scripts/test_textract_conversion.py
   ```

2. ✅ Ajustar lógica `textract_to_markdown()` baseado em resultados
   - Verificar detecção de headers (##)
   - Validar formatação de CPF (padrão UF/CPF)
   - Comparar com markdown do Docling

3. ✅ Testar extração de CPF via regex
   ```bash
   # Rodar testes de CPF com ambos os motores
   pytest tests/test_ocr.py::test_ocr_pipeline_fallback_cpf -v
   ```

4. ✅ Testar extração de exames via OpenAI
   ```bash
   # Verificar se LLM identifica exames corretamente
   pytest tests/test_ocr.py::test_ocr_pipeline_success -v
   ```

5. ✅ Testar pipeline completo em dev
   ```bash
   # Subir servidor local
   uvicorn main:app --reload

   # No frontend, fazer upload de documentos teste
   # Comparar resultados com Docling vs Textract
   ```

6. ✅ Benchmark de performance e custo
   ```python
   # Medir:
   # - Tempo de processamento (Textract vs Docling)
   # - Custo estimado ($1.50/1000 páginas)
   # - Taxa de sucesso de extração (CPF + exames)
   ```

**Critérios de Sucesso:**
- ✅ Taxa de extração de CPF ≥ 95% (comparado com Docling)
- ✅ Taxa de extração de exames ≥ 90%
- ✅ Tempo de processamento < 10 segundos (para docs típicos)
- ✅ Zero erros críticos no pipeline

---

### Fase 3: MIGRAÇÃO GRADUAL ⏱️ 1 semana

**Objetivo:** Transição progressiva para Textract em produção.

#### Estratégia Canary Deployment:

**Semana 1 - Dia 1-2: 10% de tráfego**
```python
# Em ocr_pipeline()
import random

if random.random() < 0.10 or settings.USE_TEXTRACT:
    markdown = processar_arquivo_textract(temp_path)
else:
    markdown = processar_arquivo_docling(temp_path)
```

**Monitoramento:**
- Logs de erro (`logs/app.log`)
- Taxa de sucesso BRMED (workflow)
- Feedback de usuários (via front-end)

**Semana 1 - Dia 3-4: 50% de tráfego**
```python
if random.random() < 0.50 or settings.USE_TEXTRACT:
    markdown = processar_arquivo_textract(temp_path)
else:
    markdown = processar_arquivo_docling(temp_path)
```

**Semana 1 - Dia 5-7: 100% de tráfego**
```python
# Remover lógica condicional
markdown = processar_arquivo_textract(temp_path)
```

**Rollback Plan:**
```python
# Se houver problemas críticos:
USE_TEXTRACT=false  # Volta para Docling imediatamente
```

---

### Fase 4: LIMPEZA E OTIMIZAÇÃO ⏱️ 2-3 horas

**Objetivo:** Remover código legado e otimizar.

#### Tarefas:
1. ✅ Remover função `processar_arquivo_docling()`
   ```python
   # Deletar função completa (Linhas 73-92)
   ```

2. ✅ Remover imports Docling e PyTorch
   ```python
   # Remover de ocr_service.py:
   # - from docling.document_converter import DocumentConverter
   # - import torch
   # - os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ...
   ```

3. ✅ Remover limpeza de memória GPU
   ```python
   # Deletar (Linha 182):
   # if torch.cuda.is_available():
   #     torch.cuda.empty_cache()
   ```

4. ✅ Remover dependências do `requirements.txt`
   ```bash
   # Remover:
   # --extra-index-url https://download.pytorch.org/whl/cu124
   # torch==2.4.1
   # torchvision==0.19.1
   # docling==2.0.0
   ```

5. ✅ Atualizar testes (remover mocks antigos)
   ```python
   # Em test_ocr.py, garantir que todos os mocks usam processar_arquivo_textract
   ```

6. ✅ Atualizar documentação
   ```bash
   # Atualizar:
   # - CLAUDE.md (front-end + back-end)
   # - README.md (se existir)
   # - Comentários no código
   ```

7. ✅ Otimizar conversão Textract→Markdown
   ```python
   # Baseado em métricas de produção:
   # - Melhorar detecção de headers
   # - Adicionar suporte a tabelas (se necessário)
   # - Otimizar uso de API (batch processing?)
   ```

**Validação Final:**
```bash
# Reinstalar dependências limpas
pip uninstall torch torchvision docling -y
pip install -r requirements.txt

# Rodar suite completa de testes
pytest

# Verificar build
python -m compileall app/

# Deploy em produção
```

---

## 15. MIGRAÇÃO: Riscos e Considerações

### 15.1 Riscos Técnicos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| **Markdown diferente do Docling** | 🟡 Média | 🔴 Alto | Fase 2: Testar extensivamente; ajustar `textract_to_markdown()` |
| **Regex CPF incompatível** | 🟢 Baixa | 🔴 Alto | Manter fallback LLM; testar padrão UF/CPF |
| **Headers não detectados** | 🟡 Média | 🟡 Médio | LLM é flexível; ajustar prompt se necessário |
| **Limite 5MB Textract síncrono** | 🟢 Baixa | 🟡 Médio | Implementar async para docs >5MB (Fase 4) |
| **Latência de rede** | 🟢 Baixa | 🟢 Baixo | Textract geralmente mais rápido que GPU local |

### 15.2 Riscos de Custo

**Estimativas AWS Textract:**
- **Preço:** $1.50 por 1,000 páginas (detect_document_text)
- **Volume Mensal:** Estimar baseado em histórico (ex: 500 docs/mês)
- **Custo Mensal:** ~$0.75 USD (assumindo 1 página por doc)

**Comparação com Docling:**
- **Custo Atual:** Hardware GPU (custo fixo já pago) + eletricidade
- **Custo Futuro:** Pay-per-use (variável)

**Recomendação:** Monitorar uso nos primeiros meses; configurar billing alerts na AWS.

### 15.3 Riscos Operacionais

| Risco | Mitigação |
|-------|-----------|
| **Falha de autenticação AWS** | Validar credenciais em Fase 1; implementar retry logic |
| **Quota Textract excedida** | Configurar rate limiting; solicitar aumento de quota à AWS |
| **Dependência de serviço externo** | Manter Docling como fallback durante Fase 3; SLA da AWS: 99.9% |
| **Perda de auditoria** | Implementar dual storage (markdown + JSON) - ver 9.2 |

### 15.4 Considerações de Performance

**Benchmarks Esperados:**

| Métrica | Docling (GPU) | Textract (API) | Delta |
|---------|---------------|----------------|-------|
| **Tempo de processamento** | 5-15s | 2-5s | ✅ 2-3x mais rápido |
| **Latência de rede** | 0ms (local) | 100-300ms | ⚠️ Adicional |
| **Throughput** | Limitado por GPU | Limitado por quota | ⚠️ Variável |
| **Confiabilidade** | 95% (depende de doc) | 98%+ (AWS SLA) | ✅ Melhor |

**Otimizações Futuras:**
- **Batch Processing:** Processar múltiplos docs em paralelo (Fase 4)
- **Caching:** Cachear resultado para docs duplicados
- **Async Textract:** Para documentos >5MB, usar `start_document_text_detection()`

### 15.5 Considerações de Qualidade

**Pontos de Atenção:**

1. **Formatação de CPF:**
   - Docling: Preserva formato original (CE/12345678901)
   - Textract: Pode separar em blocos diferentes
   - **Solução:** Ajustar regex ou usar LLM como fallback

2. **Detecção de Headers:**
   - Docling: Exporta markdown nativo com `##`
   - Textract: Retorna blocos LINE sem hierarquia
   - **Solução:** Heurística em `textract_to_markdown()` (texto curto + maiúsculas = header)

3. **Tabelas Médicas:**
   - Docling: Suporte limitado (desabilitado por performance)
   - Textract: Suporte robusto com `analyze_document()` (mais caro: $50/1000 páginas)
   - **Decisão:** Começar com `detect_document_text()`; avaliar upgrade se necessário

### 15.6 Checklist de Validação Pós-Migração

```markdown
## Validação Completa - Textract Migration

### Funcional
- [ ] CPF extraído corretamente (regex + LLM fallback)
- [ ] Exames extraídos corretamente (comparar com baseline Docling)
- [ ] Pipeline completo funciona (OCR → BRMED → Validação)
- [ ] Fallback de múltiplos CPFs funciona
- [ ] Markdown salvo em ocr_resultados/

### Performance
- [ ] Tempo de processamento < 10s (média)
- [ ] Taxa de erro < 5%
- [ ] Sem timeouts ou erros de rede

### Custo
- [ ] Billing alerts configurados (AWS)
- [ ] Uso mensal < orçamento definido
- [ ] Nenhum custo inesperado

### Operacional
- [ ] Logs de erro funcionando
- [ ] Auditoria preservada (markdown + JSON opcional)
- [ ] Monitoramento configurado
- [ ] Rollback plan testado (USE_TEXTRACT=false)

### Código
- [ ] Docling removido do requirements.txt
- [ ] PyTorch removido
- [ ] Imports atualizados
- [ ] Testes passando (100%)
- [ ] Nenhum código comentado/legacy
```

---

## 16. MIGRAÇÃO: Exemplo de Implementação

### 16.1 Código Completo da Função Textract

```python
# ══════════════════════════════════════════════════════════════
# app/services/ocr_service.py - VERSÃO MIGRADA
# ══════════════════════════════════════════════════════════════

import os
import re
import json
import tempfile
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile

from app.core.config import settings
from app.core.clients import client  # OpenAI client

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# INICIALIZAÇÃO DO CLIENTE TEXTRACT
# ──────────────────────────────────────────────────────────────
textract_client = boto3.client(
    'textract',
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)

# ──────────────────────────────────────────────────────────────
# PROMPTS PARA LLM (Mantidos do código original)
# ──────────────────────────────────────────────────────────────
PROMPT_EXTRAIR_EXAMES = """
Você é um assistente especializado em extrair informações de documentos médicos.

Analise o seguinte documento e identifique TODOS os nomes dos exames médicos realizados.

Documento:
{markdown}

Regras:
- Procure por headers com ## (exemplo: "## HEMOGRAMA")
- Se houver formato "EXAME - DATA", extraia apenas o nome do exame
- Retorne TODOS os exames encontrados em MAIÚSCULAS
- Retorne no formato JSON: {{"exames": ["HEMOGRAMA", "GLICOSE"]}}
"""

PROMPT_EXTRAIR_CPF = """
Extraia o CPF do paciente no seguinte documento médico.
Retorne APENAS o CPF sem formatação (11 dígitos).

Documento:
{markdown}

Retorne no formato JSON: {{"cpf": "12345678901"}}
"""

PROMPT_EXTRAIR_TODOS_CPFS = """
Extraia TODOS os CPFs encontrados no seguinte documento médico.
Retorne cada CPF sem formatação (apenas 11 dígitos).

Documento:
{markdown}

Formato JSON: {{"cpfs": ["12345678901", "98765432100"]}}
"""

# ══════════════════════════════════════════════════════════════
# FUNÇÃO PRINCIPAL: CONVERSÃO TEXTRACT
# ══════════════════════════════════════════════════════════════
def processar_arquivo_textract(file_path: str) -> str:
    """
    Converte documento em markdown usando AWS Textract

    Args:
        file_path: Caminho do arquivo no disco (/tmp/...)

    Returns:
        str: Conteúdo em formato markdown

    Raises:
        ClientError: Erro de API da AWS
        Exception: Outros erros de processamento
    """
    logger.info(f"[OCR] Chamando AWS Textract para: {file_path}")

    try:
        # Ler arquivo binário
        with open(file_path, 'rb') as document:
            documento_bytes = document.read()

        # Validar tamanho (limite síncrono: 5MB)
        tamanho_mb = len(documento_bytes) / (1024 * 1024)
        if tamanho_mb > 5:
            logger.warning(f"[OCR] Arquivo grande ({tamanho_mb:.2f}MB). Considere usar processamento assíncrono.")

        # Chamar Textract (detect_document_text para OCR simples)
        response = textract_client.detect_document_text(
            Document={'Bytes': documento_bytes}
        )

        # Converter resposta JSON em markdown
        markdown = textract_to_markdown(response)

        logger.info(f"[OCR] Textract concluído. Markdown gerado: {len(markdown)} caracteres")
        return markdown

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"[OCR] Erro Textract ({error_code}): {error_message}")
        raise Exception(f"Erro AWS Textract: {error_message}")

    except Exception as e:
        logger.error(f"[OCR] Erro inesperado no Textract: {str(e)}")
        raise

# ══════════════════════════════════════════════════════════════
# CONVERSÃO: TEXTRACT JSON → MARKDOWN
# ══════════════════════════════════════════════════════════════
def textract_to_markdown(textract_response: dict) -> str:
    """
    Converte resposta JSON do Textract em markdown

    Estratégia:
    - Blocos LINE com texto curto + maiúsculas → Headers (##)
    - Outros blocos LINE → Texto normal
    - Preserva estrutura para compatibilidade com regex e LLM

    Args:
        textract_response: Resposta completa de detect_document_text()

    Returns:
        str: Texto formatado em markdown
    """
    lines = []
    blocks = textract_response.get('Blocks', [])

    logger.info(f"[OCR] Processando {len(blocks)} blocos do Textract")

    for block in blocks:
        # Apenas processar blocos de linha (ignorar PAGE e WORD)
        if block['BlockType'] != 'LINE':
            continue

        text = block.get('Text', '').strip()
        if not text:
            continue

        # Heurística: Detectar headers de exames
        # Critérios: 1-4 palavras, maioritariamente maiúsculas
        palavras = text.split()
        eh_maiuscula = sum(1 for c in text if c.isupper()) / len(text) if text else 0

        if len(palavras) <= 4 and eh_maiuscula > 0.7:
            # Provável header de exame
            lines.append(f"\n## {text}\n")
            logger.debug(f"[OCR] Header detectado: {text}")
        else:
            # Texto normal
            lines.append(text)

    markdown = '\n'.join(lines)
    return markdown

# ══════════════════════════════════════════════════════════════
# EXTRAÇÃO DE CPF VIA REGEX (Mantida do original)
# ══════════════════════════════════════════════════════════════
def extrair_cpf_regex(markdown: str) -> Optional[str]:
    """
    Extrai CPF de texto markdown usando regex

    Prioridades:
    1. Padrão UF/CPF (ex: CE/12345678901)
    2. CPF formatado (111.222.333-44 ou similar)

    Args:
        markdown: Texto markdown

    Returns:
        str: CPF sem formatação (11 dígitos) ou None
    """
    logger.info("[OCR] Extraindo CPF via regex...")

    # Prioridade 1: UF/CPF
    uf_cpf_match = re.search(r'\b[A-Z]{2}/(\d{11})\b', markdown)
    if uf_cpf_match:
        cpf = uf_cpf_match.group(1)
        logger.info(f"[OCR] CPF encontrado (padrão UF/CPF): {cpf}")
        return cpf

    # Prioridade 2: CPF genérico formatado
    generic_cpf_match = re.search(
        r'\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b',
        markdown
    )
    if generic_cpf_match:
        cpf = re.sub(r'\D', '', generic_cpf_match.group(0))
        logger.info(f"[OCR] CPF encontrado (padrão genérico): {cpf}")
        return cpf

    logger.warning("[OCR] Nenhum CPF encontrado via regex")
    return None

# ══════════════════════════════════════════════════════════════
# EXTRAÇÃO VIA LLM (Mantidas do original)
# ══════════════════════════════════════════════════════════════
def extrair_cpf_ia(markdown: str) -> Optional[str]:
    """Extrai CPF via OpenAI GPT (fallback)"""
    try:
        prompt = PROMPT_EXTRAIR_CPF.format(markdown=markdown)

        resposta = client.chat.completions.create(
            model=settings.MODELO_GPT,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )

        resultado = json.loads(resposta.choices[0].message.content)
        return resultado.get("cpf")

    except Exception as e:
        logger.error(f"[OCR] Erro na extração de CPF via IA: {e}")
        return None

def extrair_exames_ia(markdown: str) -> Dict[str, Any]:
    """Extrai lista de exames via OpenAI GPT"""
    try:
        logger.info("[OCR] Iniciando extração de exames via OpenAI GPT...")

        prompt = PROMPT_EXTRAIR_EXAMES.format(markdown=markdown)

        resposta = client.chat.completions.create(
            model=settings.MODELO_GPT,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )

        resultado = json.loads(resposta.choices[0].message.content)
        exames = resultado.get("exames", [])

        logger.info(f"[OCR] Exames extraídos: {len(exames)} encontrados - {exames}")
        return resultado

    except Exception as e:
        logger.error(f"[OCR] Erro na extração de exames via IA: {e}")
        return {"exames": []}

async def extrair_todos_cpfs_ia(
    markdown: str,
    exclude_cpf: Optional[str] = None
) -> List[str]:
    """Extrai TODOS os CPFs do documento (para fallback workflow)"""
    try:
        prompt = PROMPT_EXTRAIR_TODOS_CPFS.format(markdown=markdown)

        resposta = await client.chat.completions.create(
            model=settings.MODELO_GPT,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )

        resultado = json.loads(resposta.choices[0].message.content)
        cpfs = resultado.get("cpfs", [])

        # Filtrar CPF já testado
        if exclude_cpf:
            cpfs = [cpf for cpf in cpfs if cpf != exclude_cpf]

        logger.info(f"[OCR] CPFs alternativos encontrados: {len(cpfs)} - {cpfs}")
        return cpfs

    except Exception as e:
        logger.error(f"[OCR] Erro na extração de múltiplos CPFs: {e}")
        return []

# ══════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL (Modificado para Textract)
# ══════════════════════════════════════════════════════════════
async def ocr_pipeline(
    file: UploadFile,
    salvar_markdown: bool = True
) -> Dict[str, Any]:
    """
    Pipeline completo de OCR com AWS Textract

    Etapas:
    1. Salvar UploadFile em /tmp
    2. Processar com Textract (converter para markdown)
    3. Deletar arquivo temporário
    4. Salvar markdown em disco (opcional)
    5. Extrair CPF (regex + LLM fallback)
    6. Extrair exames (LLM)
    7. Retornar resultado

    Args:
        file: FastAPI UploadFile object
        salvar_markdown: Se True, salva markdown em ocr_resultados/

    Returns:
        dict: {
            "cpf": str | None,
            "exames": list[str],
            "markdown_content": str,
            "markdown_salvo_em": str | None,
            "erro": str | None
        }
    """
    logger.info(f"[OCR] Iniciando pipeline OCR para arquivo: {file.filename}")

    try:
        # ─────────────────────────────────────────────────────────
        # ETAPA 1: Salvar em arquivo temporário
        # ─────────────────────────────────────────────────────────
        conteudo = await file.read()
        _, extensao = os.path.splitext(file.filename)

        with tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as temp:
            temp.write(conteudo)
            temp_path = temp.name

        logger.info(f"[OCR] Arquivo temporário criado: {temp_path}")

        # ─────────────────────────────────────────────────────────
        # ETAPA 2: Processar com Textract
        # ─────────────────────────────────────────────────────────
        logger.info(f"[OCR] Iniciando conversão Textract para: {file.filename}")
        markdown = processar_arquivo_textract(temp_path)
        logger.info(f"[OCR] Conversão Textract concluída. Markdown gerado: {len(markdown)} caracteres")

        # ─────────────────────────────────────────────────────────
        # ETAPA 3: Deletar arquivo temporário
        # ─────────────────────────────────────────────────────────
        os.unlink(temp_path)
        logger.info(f"[OCR] Arquivo temporário deletado: {temp_path}")

        # ─────────────────────────────────────────────────────────
        # ETAPA 4: Salvar markdown (opcional, para auditoria)
        # ─────────────────────────────────────────────────────────
        caminho_md = None
        if salvar_markdown:
            os.makedirs("ocr_resultados", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_nome = os.path.splitext(file.filename)[0]
            caminho_md = f"ocr_resultados/ocr_{base_nome}_{timestamp}.md"

            with open(caminho_md, "w", encoding="utf-8") as f:
                f.write(markdown)

            logger.info(f"[OCR] Markdown salvo em: {caminho_md}")

        # ─────────────────────────────────────────────────────────
        # ETAPA 5: Extrair CPF (regex → fallback LLM)
        # ─────────────────────────────────────────────────────────
        logger.info("[OCR] Extraindo CPF via regex...")
        cpf_extraido = extrair_cpf_regex(markdown)

        if not cpf_extraido:
            logger.warning("[OCR] Regex falhou, tentando LLM...")
            cpf_extraido = extrair_cpf_ia(markdown)

        logger.info(f"[OCR] CPF extraído: {cpf_extraido if cpf_extraido else 'Nenhum CPF encontrado'}")

        # ─────────────────────────────────────────────────────────
        # ETAPA 6: Extrair exames (LLM)
        # ─────────────────────────────────────────────────────────
        logger.info("[OCR] Iniciando extração de exames via OpenAI GPT...")
        resposta_exames = extrair_exames_ia(markdown)
        exames_extraidos = resposta_exames.get("exames", [])
        logger.info(f"[OCR] Exames extraídos: {len(exames_extraidos)} encontrados - {exames_extraidos}")

        # ─────────────────────────────────────────────────────────
        # ETAPA 7: Retornar resultado (contrato mantido)
        # ─────────────────────────────────────────────────────────
        logger.info(f"[OCR] Pipeline OCR concluído para: {file.filename}")

        return {
            "cpf": cpf_extraido,
            "exames": exames_extraidos,
            "markdown_content": markdown,
            "markdown_salvo_em": caminho_md,
            "erro": None
        }

    except Exception as e:
        logger.error(f"[OCR] Erro no pipeline: {str(e)}", exc_info=True)
        return {
            "cpf": None,
            "exames": [],
            "markdown_content": "",
            "markdown_salvo_em": None,
            "erro": f"Erro no processamento OCR: {str(e)}"
        }
```

### 16.2 Exemplo de Teste Unitário Atualizado

```python
# ══════════════════════════════════════════════════════════════
# tests/test_ocr.py - VERSÃO MIGRADA
# ══════════════════════════════════════════════════════════════

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import UploadFile
from io import BytesIO

# ──────────────────────────────────────────────────────────────
# TESTE 1: Pipeline com Sucesso
# ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@patch("app.services.ocr_service.processar_arquivo_textract", return_value="## HEMOGRAMA\n## GLICOSE")
@patch("app.services.ocr_service.extrair_exames_ia", return_value={"exames": ["HEMOGRAMA", "GLICOSE"]})
@patch("app.services.ocr_service.extrair_cpf_regex", return_value="12345678901")
async def test_ocr_pipeline_textract_success(mock_cpf, mock_exames, mock_textract):
    """
    Testa pipeline completo com Textract
    """
    from app.services.ocr_service import ocr_pipeline

    # Mock de UploadFile
    file_content = b"fake pdf content"
    upload_file = UploadFile(filename="test.pdf", file=BytesIO(file_content))

    # Execução
    resultado = await ocr_pipeline(upload_file, salvar_markdown=False)

    # Asserções
    assert resultado["cpf"] == "12345678901"
    assert len(resultado["exames"]) == 2
    assert "HEMOGRAMA" in resultado["exames"]
    assert "GLICOSE" in resultado["exames"]
    assert resultado["erro"] is None

    # Verificar que Textract foi chamado
    mock_textract.assert_called_once()

# ──────────────────────────────────────────────────────────────
# TESTE 2: Conversão Textract → Markdown
# ──────────────────────────────────────────────────────────────
def test_textract_to_markdown():
    """
    Testa conversão de resposta JSON do Textract em markdown
    """
    from app.services.ocr_service import textract_to_markdown

    # Mock de resposta Textract
    textract_response = {
        "Blocks": [
            {
                "BlockType": "LINE",
                "Text": "HEMOGRAMA",
                "Confidence": 99.5
            },
            {
                "BlockType": "LINE",
                "Text": "Metodo: Contagem automatizada",
                "Confidence": 98.2
            },
            {
                "BlockType": "LINE",
                "Text": "GLICOSE",
                "Confidence": 99.8
            }
        ]
    }

    # Execução
    markdown = textract_to_markdown(textract_response)

    # Asserções
    assert "## HEMOGRAMA" in markdown
    assert "## GLICOSE" in markdown
    assert "Metodo: Contagem automatizada" in markdown

# ──────────────────────────────────────────────────────────────
# TESTE 3: Fallback CPF com Textract
# ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@patch("app.services.ocr_service.processar_arquivo_textract", return_value="CPF: 123.456.789-01")
@patch("app.services.ocr_service.extrair_exames_ia", return_value={"exames": []})
async def test_ocr_pipeline_textract_fallback_cpf(mock_exames, mock_textract):
    """
    Testa extração de CPF via regex com output do Textract
    """
    from app.services.ocr_service import ocr_pipeline

    upload_file = UploadFile(filename="test.pdf", file=BytesIO(b"content"))
    resultado = await ocr_pipeline(upload_file, salvar_markdown=False)

    # Verifica que regex capturou o CPF (sem formatação)
    assert resultado["cpf"] == "12345678901"
```

### 16.3 Exemplo de Configuração AWS (config.py)

```python
# ══════════════════════════════════════════════════════════════
# app/core/config.py - ADIÇÕES PARA AWS
# ══════════════════════════════════════════════════════════════

import os
from typing import Optional

class Settings:
    # ... (configurações existentes) ...

    # ──────────────────────────────────────────────────────────
    # AWS Textract Configuration
    # ──────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

    # Opcional: S3 bucket para staging de documentos grandes (>5MB)
    AWS_S3_BUCKET: Optional[str] = os.getenv("AWS_S3_BUCKET")

    # Feature toggle (para transição gradual)
    USE_TEXTRACT: bool = os.getenv("USE_TEXTRACT", "true").lower() == "true"

    # Validação de credenciais
    @property
    def aws_configured(self) -> bool:
        """Verifica se credenciais AWS estão configuradas"""
        return bool(
            self.AWS_ACCESS_KEY_ID and
            self.AWS_SECRET_ACCESS_KEY
        )

settings = Settings()

# Validar no startup
if settings.USE_TEXTRACT and not settings.aws_configured:
    raise ValueError(
        "AWS Textract habilitado mas credenciais não configuradas. "
        "Defina AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY no .env"
    )
```

---

## 17. ✅ MIGRAÇÃO: Implementação Realizada

### 17.1 Resumo da Implementação

**Status:** ✅ **FASE 1 CONCLUÍDA** - Feature Toggle Implementado
**Data de Conclusão:** 12/11/2025
**Tempo Total:** ~2 horas

A migração foi implementada com sucesso usando a estratégia de **Feature Toggle**, permitindo alternar entre Docling e Textract sem quebrar o sistema existente.

### 17.2 Código Implementado

#### 17.2.1 Cliente AWS Textract (ocr_service.py:24-37)

```python
# Inicializar cliente AWS Textract (usado quando USE_TEXTRACT=true)
textract_client = None
if settings.USE_TEXTRACT:
    try:
        textract_client = boto3.client(
            'textract',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        logger.info("[OCR] Cliente AWS Textract inicializado com sucesso")
    except Exception as e:
        logger.error(f"[OCR] Erro ao inicializar cliente Textract: {e}")
        logger.warning("[OCR] Fallback para Docling será usado")
```

#### 17.2.2 Conversão Textract→Markdown (ocr_service.py:114-156)

```python
def textract_to_markdown(textract_response: dict) -> str:
    """
    Converte resposta JSON do AWS Textract em formato markdown.
    Preserva formato compatível com a lógica de extração existente (regex CPF + LLM exames).

    Args:
        textract_response: Resposta completa do detect_document_text()

    Returns:
        str: Texto em formato markdown compatível com o pipeline atual

    Estratégia de conversão:
    - Blocks tipo LINE são convertidos em linhas de texto
    - Texto curto em maiúsculas (≤ 4 palavras) vira header markdown (##)
    - Preserva padrões UF/CPF para detecção via regex
    """
    lines = []

    for block in textract_response.get('Blocks', []):
        if block['BlockType'] == 'LINE':
            text = block['Text'].strip()

            if not text:
                continue

            # Detectar possíveis headers de exames:
            # - Texto curto (até 4 palavras)
            # - Maioria em maiúsculas (pelo menos 50% dos caracteres alfabéticos)
            words = text.split()
            if len(words) <= 4:
                alpha_chars = [c for c in text if c.isalpha()]
                upper_chars = [c for c in text if c.isupper()]

                # Se pelo menos 50% das letras são maiúsculas, considerar como header
                if alpha_chars and len(upper_chars) / len(alpha_chars) >= 0.5:
                    lines.append(f"\n## {text}\n")
                    continue

            # Texto normal
            lines.append(text)

    markdown = '\n'.join(lines)
    return markdown
```

#### 17.2.3 Processamento via Textract (ocr_service.py:159-213)

```python
def processar_arquivo_textract(file_path: str) -> str:
    """
    Processa documento via AWS Textract e retorna markdown extraído.
    Usa método síncrono (detect_document_text) para documentos até 5MB.

    Args:
        file_path: Caminho absoluto do arquivo no disco

    Returns:
        str: Conteúdo em formato markdown

    Raises:
        ClientError: Erro na chamada da API Textract
        Exception: Outros erros inesperados
    """
    logger.info(f"[OCR] Chamando AWS Textract (detect_document_text) para: {file_path}")

    try:
        # Ler arquivo binário
        with open(file_path, 'rb') as document:
            documento_bytes = document.read()

        # Verificar tamanho (limite de 5MB para método síncrono)
        tamanho_mb = len(documento_bytes) / (1024 * 1024)
        logger.info(f"[OCR] Tamanho do documento: {tamanho_mb:.2f} MB")

        if tamanho_mb > 5:
            logger.warning(f"[OCR] Documento excede 5MB. Considere usar método assíncrono do Textract.")

        # Chamar Textract (síncrono, sem necessidade de S3)
        response = textract_client.detect_document_text(
            Document={'Bytes': documento_bytes}
        )

        # Verificar resposta
        num_blocks = len(response.get('Blocks', []))
        logger.info(f"[OCR] Textract retornou {num_blocks} blocos de texto")

        # Converter resposta JSON em markdown
        markdown = textract_to_markdown(response)

        logger.info(f"[OCR] Conversão concluída. Markdown gerado: {len(markdown)} caracteres")
        return markdown

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"[OCR] Erro Textract [{error_code}]: {error_message}")
        raise
    except FileNotFoundError as e:
        logger.error(f"[OCR] Arquivo não encontrado: {file_path}")
        raise
    except Exception as e:
        logger.error(f"[OCR] Erro inesperado ao processar com Textract: {e}")
        raise
```

#### 17.2.4 Pipeline com Feature Toggle (ocr_service.py:251-282)

```python
async def ocr_pipeline(file, salvar_markdown=True) -> Dict[str, Any]:
    """
    Pipeline completo: processa arquivo, extrai info, aplica fallbacks, salva markdown.

    Suporta dois motores de OCR via feature toggle (USE_TEXTRACT):
    - Textract (AWS): quando USE_TEXTRACT=true
    - Docling (local): quando USE_TEXTRACT=false (padrão)
    """
    logger.info(f"[OCR] Iniciando pipeline OCR para arquivo: {file.filename}")

    # Determinar qual motor usar
    usar_textract = settings.USE_TEXTRACT and textract_client is not None
    motor_ocr = "AWS Textract" if usar_textract else "Docling (local)"
    logger.info(f"[OCR] Motor selecionado: {motor_ocr}")

    # Corrige o manuseio de UploadFile do FastAPI
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as temp:
        content = await file.read()
        temp.write(content)
        temp_path = temp.name

    logger.info(f"[OCR] Iniciando conversão com {motor_ocr} para: {file.filename}")
    try:
        # Feature Toggle: escolher motor de OCR
        if usar_textract:
            markdown = processar_arquivo_textract(temp_path)
        else:
            markdown = processar_arquivo_docling(temp_path)

        logger.info(f"[OCR] Conversão concluída. Markdown gerado: {len(markdown)} caracteres")
    finally:
        os.remove(temp_path)

    # ... (resto do pipeline permanece igual)

    # Libera memória da GPU após cada processamento (apenas para Docling)
    if not usar_textract and torch.cuda.is_available():
        torch.cuda.empty_cache()
        logger.info(f"[OCR] Memória GPU liberada (Docling)")

    logger.info(f"[OCR] Pipeline OCR concluído para: {file.filename}")
    return info
```

### 17.3 Configurações

#### 17.3.1 Variáveis de Ambiente (.env)

```env
# Configurações existentes
OPENAI_API_KEY="sk-proj-..."
BRMED_USERNAME=thiago.simoes
BRMED_PASSWORD=brmed10

# AWS Textract Configuration (para migração do OCR)
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1

# Feature Toggle: use "true" para ativar Textract, "false" para usar Docling (padrão)
USE_TEXTRACT=false
```

#### 17.3.2 Settings (app/core/config.py:20-26)

```python
class Settings:
    # ... (configurações existentes)

    # AWS Textract Configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # Feature Toggle: OCR Engine Selection
    USE_TEXTRACT = os.getenv("USE_TEXTRACT", "false").lower() == "true"
```

#### 17.3.3 Dependências (requirements.txt:28-29)

```txt
# AWS SDK (para migração do OCR para Textract)
boto3>=1.34.0  # AWS Textract para processamento de documentos
```

**Versão instalada:** boto3 1.40.71

### 17.4 Alterações de Código

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `requirements.txt` | 28-29 | Adicionado boto3>=1.34.0 |
| `.env` | 5-11 | Variáveis AWS + USE_TEXTRACT |
| `app/core/config.py` | 20-26 | Settings AWS + feature flag |
| `app/services/ocr_service.py` | 14-16 | Imports boto3 + ClientError |
| `app/services/ocr_service.py` | 24-37 | Inicialização cliente Textract |
| `app/services/ocr_service.py` | 114-156 | Função textract_to_markdown() |
| `app/services/ocr_service.py` | 159-213 | Função processar_arquivo_textract() |
| `app/services/ocr_service.py` | 251-282 | Pipeline com feature toggle |
| `app/services/ocr_service.py` | 319-322 | Limpeza GPU condicional |

### 17.5 Compatibilidade

**Contratos Mantidos:**
- ✅ `ocr_pipeline()` mantém assinatura e retorno idênticos
- ✅ Formato de resposta JSON permanece inalterado
- ✅ Markdown gerado compatível com regex CPF
- ✅ Markdown gerado compatível com LLM extração de exames
- ✅ Workflow service não requer alterações
- ✅ Testes existentes continuam funcionando

**Arquivos NÃO Modificados:**
- `app/services/workflow_service.py`
- `app/services/brmed_service.py`
- `app/services/validacao_service.py`
- `app/api/v1_ocr.py`
- `app/api/v1_brmed.py`
- `main.py`
- Todos os testes

---

## 18. 📋 Como Testar a Migração

### 18.1 Pré-requisitos

**Antes de Começar:**
1. ✅ boto3 instalado no venv (versão 1.40.71)
2. ⏳ Credenciais AWS IAM configuradas
3. ⏳ Permissões Textract no IAM

### 18.2 Configurar Credenciais AWS

#### Passo 1: Criar Usuário IAM

```bash
# No Console AWS (IAM):
# 1. Criar novo usuário: prontuai-textract
# 2. Anexar política: AmazonTextractFullAccess
# 3. Criar access key (tipo: Application)
# 4. Copiar AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY
```

#### Passo 2: Atualizar .env

```bash
# Editar /home/brmed/Área de trabalho/prontuai/back-end/.env

# Substituir placeholders por credenciais reais:
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1

# Manter Textract desabilitado por enquanto
USE_TEXTRACT=false
```

### 18.3 Testar Modo Docling (Baseline)

**Objetivo:** Confirmar que o sistema continua funcionando como antes.

```bash
# 1. Ativar venv
cd /home/brmed/Área\ de\ trabalho/prontuai/back-end
source venv/bin/activate

# 2. Verificar configuração
cat .env | grep USE_TEXTRACT
# Deve mostrar: USE_TEXTRACT=false

# 3. Subir servidor
uvicorn main:app --reload

# 4. No frontend (nova janela de terminal):
cd /home/brmed/Área\ de\ trabalho/prontuai/front-end
npm run dev

# 5. Testar upload de documento médico
# - Acessar http://localhost:3000/submissao
# - Fazer upload de PDF teste
# - Verificar extração de CPF e exames
# - Confirmar logs: "[OCR] Motor selecionado: Docling (local)"
```

**Critérios de Sucesso:**
- ✅ Upload funciona normalmente
- ✅ CPF extraído corretamente
- ✅ Exames extraídos corretamente
- ✅ Logs mostram "Docling (local)"

### 18.4 Testar Modo Textract (Nova Feature)

**Objetivo:** Validar integração com AWS Textract.

```bash
# 1. Ativar Textract no .env
nano .env
# Alterar: USE_TEXTRACT=true

# 2. Reiniciar servidor (Ctrl+C e subir novamente)
uvicorn main:app --reload

# 3. Verificar inicialização nos logs
# Deve aparecer: "[OCR] Cliente AWS Textract inicializado com sucesso"

# 4. No frontend, fazer upload do MESMO documento usado no teste anterior

# 5. Verificar logs do servidor:
# - "[OCR] Motor selecionado: AWS Textract"
# - "[OCR] Chamando AWS Textract (detect_document_text)"
# - "[OCR] Tamanho do documento: X.XX MB"
# - "[OCR] Textract retornou N blocos de texto"
# - "[OCR] Conversão concluída. Markdown gerado: N caracteres"

# 6. Comparar resultados com Docling
```

**Critérios de Sucesso:**
- ✅ Cliente Textract inicializado sem erros
- ✅ Documento processado com sucesso
- ✅ CPF extraído corretamente (validar padrão UF/CPF)
- ✅ Exames extraídos corretamente
- ✅ Resultados similares ou melhores que Docling

### 18.5 Testar Fallback de Erro

**Objetivo:** Validar comportamento quando Textract falha.

```bash
# 1. Configurar credenciais inválidas no .env
AWS_ACCESS_KEY_ID=INVALID_KEY
USE_TEXTRACT=true

# 2. Reiniciar servidor

# 3. Verificar logs:
# Deve aparecer: "[OCR] Erro ao inicializar cliente Textract"
# E: "[OCR] Fallback para Docling será usado"

# 4. Upload de documento deve funcionar normalmente com Docling
```

**Critérios de Sucesso:**
- ✅ Sistema detecta credenciais inválidas
- ✅ Fallback para Docling automático
- ✅ Usuário não percebe erro (sistema continua funcionando)

### 18.6 Comparação: Docling vs Textract

**Criar tabela comparativa:**

| Critério | Docling | Textract | Vencedor |
|----------|---------|----------|----------|
| **Tempo de processamento** | ___ seg | ___ seg | ? |
| **CPF detectado** | ✅/❌ | ✅/❌ | ? |
| **Exames detectados** | N exames | N exames | ? |
| **Qualidade do markdown** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ? |
| **Custo por documento** | $0.00 | $0.0015 | ? |
| **Tamanho máximo** | Ilimitado | 5MB | Docling |
| **Requer GPU** | Sim | Não | Textract |

**Documentos de Teste Sugeridos:**
1. PDF com padrão CE/12345678901 (CPF após UF)
2. PDF com CPF formatado 123.456.789-01
3. PDF com múltiplos exames (HEMOGRAMA, GLICEMIA, etc.)
4. PDF com qualidade de imagem baixa (testar OCR)
5. PDF com 3-4 páginas (testar performance)

### 18.7 Benchmark de Custo

**Textract Pricing:**
- detect_document_text: $1.50 por 1000 páginas ($0.0015 por página)
- analyze_document: $50 por 1000 páginas ($0.05 por página)

**Estimativa para ProntuAI:**
```bash
# Assumindo 1000 documentos/mês, média de 2 páginas
1000 docs × 2 páginas × $0.0015 = $3.00/mês

# Comparado com Docling:
- Custo de GPU RTX 3050 (depreciação + energia): ~$20/mês
- Economia potencial: $17/mês
```

**Cálculo de ROI:**
```bash
# Quando Textract compensa?
# Se processar > 13.333 páginas/mês:
# $20 / $0.0015 = 13.333 páginas/ponto de equilíbrio
```

### 18.8 Scripts de Teste Automatizado

#### Script 1: Teste Rápido de Alternância

```bash
#!/bin/bash
# test_toggle.sh - Testa alternância entre motores

echo "=== Teste de Feature Toggle ==="

# Teste 1: Docling
echo "USE_TEXTRACT=false" > .env.test
export $(cat .env.test | xargs)
python3 -c "from app.services.ocr_service import textract_client; print('Textract:', textract_client)"

# Teste 2: Textract
echo "USE_TEXTRACT=true" > .env.test
echo "AWS_ACCESS_KEY_ID=test" >> .env.test
echo "AWS_SECRET_ACCESS_KEY=test" >> .env.test
export $(cat .env.test | xargs)
python3 -c "from app.services.ocr_service import textract_client; print('Textract:', textract_client)"

rm .env.test
```

#### Script 2: Comparação de Saída

```python
# compare_outputs.py - Compara markdown gerado por ambos motores

import asyncio
from app.services.ocr_service import ocr_pipeline
from fastapi import UploadFile
import io

async def compare_ocr_engines(pdf_path: str):
    """Compara Docling vs Textract no mesmo documento"""

    # Ler PDF
    with open(pdf_path, 'rb') as f:
        content = f.read()

    # Teste com Docling
    print("=== Testando Docling ===")
    settings.USE_TEXTRACT = False
    upload_file = UploadFile(filename="test.pdf", file=io.BytesIO(content))
    result_docling = await ocr_pipeline(upload_file, salvar_markdown=False)

    # Teste com Textract
    print("=== Testando Textract ===")
    settings.USE_TEXTRACT = True
    upload_file = UploadFile(filename="test.pdf", file=io.BytesIO(content))
    result_textract = await ocr_pipeline(upload_file, salvar_markdown=False)

    # Comparar
    print("\n=== COMPARAÇÃO ===")
    print(f"CPF Docling: {result_docling['cpf']}")
    print(f"CPF Textract: {result_textract['cpf']}")
    print(f"Exames Docling: {result_docling['exames']}")
    print(f"Exames Textract: {result_textract['exames']}")

    # Calcular similaridade
    exames_match = set(result_docling['exames']) == set(result_textract['exames'])
    print(f"\nExames idênticos: {'✅ SIM' if exames_match else '❌ NÃO'}")

# Executar
asyncio.run(compare_ocr_engines("path/to/test.pdf"))
```

### 18.9 Checklist de Validação Final

Antes de marcar Fase 2 como concluída:

- [ ] Credenciais AWS configuradas e testadas
- [ ] Cliente Textract inicializa sem erros
- [ ] Documento de teste processado com sucesso
- [ ] CPF extraído corretamente (padrão UF/CPF)
- [ ] Exames extraídos corretamente
- [ ] Markdown compatível com pipeline existente
- [ ] Fallback para Docling funciona em caso de erro
- [ ] Performance aceitável (< 10 segundos por página)
- [ ] Custo estimado dentro do orçamento
- [ ] Comparação Docling vs Textract documentada
- [ ] Logs mostram motor correto sendo usado
- [ ] Sistema continua funcionando com USE_TEXTRACT=false

### 18.10 Próximos Passos Após Validação

**Se todos os testes passarem:**
1. Documentar resultados na seção "Status da Migração"
2. Marcar Fase 2 como concluída
3. Planejar Fase 3 (deploy em produção)
4. Considerar remoção do Docling (opcional, após período de observação)

**Se houver problemas:**
1. Documentar issues encontradas
2. Ajustar função `textract_to_markdown()` conforme necessário
3. Re-testar com documentos problemáticos
4. Considerar manter Docling como padrão por mais tempo

---

## 19. Referências Técnicas

### 19.1 Documentação AWS Textract

| Recurso | URL |
|---------|-----|
| **API Reference** | https://docs.aws.amazon.com/textract/latest/dg/API_Reference.html |
| **detect_document_text** | https://docs.aws.amazon.com/textract/latest/dg/API_DetectDocumentText.html |
| **analyze_document** | https://docs.aws.amazon.com/textract/latest/dg/API_AnalyzeDocument.html |
| **Pricing** | https://aws.amazon.com/textract/pricing/ |
| **Best Practices** | https://docs.aws.amazon.com/textract/latest/dg/best-practices.html |

### 19.2 Estrutura de Resposta Textract

```json
{
  "DocumentMetadata": {
    "Pages": 1
  },
  "Blocks": [
    {
      "BlockType": "PAGE",
      "Geometry": {...},
      "Id": "1",
      "Relationships": [...]
    },
    {
      "BlockType": "LINE",
      "Id": "2",
      "Text": "HEMOGRAMA",
      "Confidence": 99.5,
      "Geometry": {
        "BoundingBox": {
          "Width": 0.15,
          "Height": 0.02,
          "Left": 0.1,
          "Top": 0.1
        }
      }
    },
    {
      "BlockType": "WORD",
      "Id": "3",
      "Text": "HEMOGRAMA",
      "Confidence": 99.5
    }
  ]
}
```

**Tipos de Blocos:**
- `PAGE`: Representa uma página
- `LINE`: Linha de texto (usado na conversão markdown)
- `WORD`: Palavra individual

### 17.3 Comparação Técnica Detalhada

| Aspecto | Docling 2.0 | AWS Textract |
|---------|-------------|--------------|
| **Tipo** | Biblioteca Python local | API cloud (REST) |
| **Modelo** | PyTorch (open-source) | Proprietário AWS |
| **GPU** | Obrigatório (CUDA 12.4) | Não necessário |
| **Instalação** | pip install (~3.5GB) | pip install boto3 (~50MB) |
| **Latência** | 5-15s (local) | 2-5s + 100-300ms (rede) |
| **Custo** | Hardware + eletricidade | $1.50/1000 páginas |
| **Escalabilidade** | Limitado por GPU | Ilimitado (quota) |
| **Saída Nativa** | Markdown | JSON (estruturado) |
| **Tabelas** | Suporte limitado | Excelente (analyze_document) |
| **Idiomas** | Múltiplos | 26 idiomas (incluindo pt-BR) |
| **SLA** | N/A (local) | 99.9% (AWS) |

### 17.4 Caminhos Completos de Arquivos

```
/home/brmed/Área de trabalho/prontuai/back-end/
├── app/
│   ├── services/
│   │   └── ocr_service.py              [218 linhas] 🔴 MODIFICAR
│   ├── api/
│   │   ├── v1_ocr.py                   [21 linhas] 🟢 MANTER
│   │   └── v1_brmed.py                 [137 linhas] 🟢 MANTER
│   └── core/
│       └── config.py                   [20 linhas] 🟡 ADICIONAR
├── tests/
│   └── test_ocr.py                     [41 linhas] 🟡 ATUALIZAR
├── requirements.txt                    [31 linhas] 🔴 MODIFICAR
├── .env                                🟡 ADICIONAR
└── ocr_resultados/                     [12MB, 300+ arquivos] 📁 PRESERVAR
```

### 17.5 Comandos Úteis

```bash
# ──────────────────────────────────────────────────────────────
# Instalação
# ──────────────────────────────────────────────────────────────
pip install boto3
pip uninstall torch torchvision docling -y

# ──────────────────────────────────────────────────────────────
# Testes
# ──────────────────────────────────────────────────────────────
pytest tests/test_ocr.py -v
pytest tests/test_ocr.py::test_ocr_pipeline_success -v

# ──────────────────────────────────────────────────────────────
# Execução Local
# ──────────────────────────────────────────────────────────────
uvicorn main:app --reload
uvicorn main:app --host 0.0.0.0 --port 8000

# ──────────────────────────────────────────────────────────────
# Verificação de Logs
# ──────────────────────────────────────────────────────────────
tail -f logs/app.log
grep "Textract" logs/app.log

# ──────────────────────────────────────────────────────────────
# Validar Credenciais AWS (CLI)
# ──────────────────────────────────────────────────────────────
aws configure list
aws textract help

# ──────────────────────────────────────────────────────────────
# Comparar Tamanhos de Dependências
# ──────────────────────────────────────────────────────────────
pip show torch torchvision docling | grep "Location\|Size"
pip show boto3 | grep "Location\|Size"
```

### 17.6 Troubleshooting Comum

| Problema | Causa | Solução |
|----------|-------|---------|
| **ImportError: No module named 'boto3'** | boto3 não instalado | `pip install boto3` |
| **ClientError: AccessDenied** | Credenciais AWS inválidas | Verificar AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY |
| **ClientError: InvalidImageFormatException** | Formato de arquivo não suportado | Textract suporta: PDF, PNG, JPEG, TIFF |
| **ClientError: ProvisionedThroughputExceededException** | Quota excedida | Reduzir taxa de requisições ou solicitar aumento de quota |
| **Timeout ao processar** | Documento muito grande | Usar processamento assíncrono (start_document_text_detection) |
| **CPF não encontrado** | Regex incompatível com Textract | Ajustar heurística em textract_to_markdown() ou usar LLM |
| **Headers não detectados** | Blocos LINE sem hierarquia | Melhorar lógica em textract_to_markdown() (ver 16.1) |

### 17.7 Checklist de Implantação

```markdown
## Checklist Final - Migração Textract

### Pré-Migração
- [ ] Backup do código atual (git commit)
- [ ] Backup do ambiente virtual (pip freeze > requirements.backup.txt)
- [ ] Documentar baseline de performance (tempo, taxa de sucesso)
- [ ] Criar credenciais AWS IAM (permissões textract:*)
- [ ] Configurar billing alerts na AWS

### Fase 1 - Preparação
- [ ] Adicionar boto3 ao requirements.txt
- [ ] Criar função processar_arquivo_textract()
- [ ] Criar função textract_to_markdown()
- [ ] Adicionar feature toggle (USE_TEXTRACT)
- [ ] Testar localmente (USE_TEXTRACT=true)

### Fase 2 - Testes
- [ ] Testar com 10+ documentos reais
- [ ] Comparar resultados Docling vs Textract
- [ ] Validar extração de CPF (>95% sucesso)
- [ ] Validar extração de exames (>90% sucesso)
- [ ] Medir tempo de processamento

### Fase 3 - Deployment
- [ ] Deploy em staging (100% Textract)
- [ ] Testes de integração (workflow completo)
- [ ] Canary deployment em produção (10% → 50% → 100%)
- [ ] Monitorar logs de erro
- [ ] Validar custo AWS (primeiras 24h)

### Fase 4 - Limpeza
- [ ] Remover código Docling (processar_arquivo_docling)
- [ ] Remover imports torch/docling
- [ ] Remover dependências requirements.txt
- [ ] Atualizar testes (remover mocks antigos)
- [ ] Atualizar documentação (CLAUDE.md, README.md)
- [ ] Git commit final ("feat: migrate OCR from Docling to AWS Textract")

### Pós-Migração
- [ ] Monitorar custos AWS (primeira semana)
- [ ] Verificar taxa de erro (comparar com baseline)
- [ ] Coletar feedback de usuários
- [ ] Otimizar textract_to_markdown() se necessário
- [ ] Documentar lições aprendidas
```

---

## Conclusão

Este documento fornece uma análise técnica completa do sistema de OCR do ProntuAI e um guia detalhado para migração de **Docling** para **AWS Textract**.

**Próximos Passos Recomendados:**

1. **Revisar Seções 12-16** (Migração) em detalhe
2. **Validar Estratégia** com stakeholders técnicos
3. **Criar Branch de Migração** (`git checkout -b feature/textract-migration`)
4. **Seguir Fase 1** (Preparação) para implementação não-quebrante
5. **Agendar Testes** em ambiente de desenvolvimento

**Contato para Dúvidas:**
- Documentação Técnica BRMED
- Equipe de Engenharia ProntuAI

**Última Atualização:** 2025-11-12

---

## 📝 Notas de Versão

### Versão 2.0 (12/11/2025)
- ✅ **FASE 1 CONCLUÍDA**: Feature Toggle implementado com sucesso
- ➕ Adicionada seção "Status da Migração" no topo do documento
- ➕ Adicionada seção "Implementação Realizada" com código completo
- ➕ Adicionada seção "Como Testar a Migração" com instruções detalhadas
- ➕ Incluídos scripts de teste automatizado
- ➕ Incluído checklist de validação
- ➕ Incluída análise de custo e ROI
- ✏️ Atualizado índice com novas seções

### Versão 1.0 (11/11/2025)
- 📄 Documentação inicial de análise técnica completa
- 📋 Estratégia de migração faseada planejada
- 📊 Análise de contratos e pontos de integração

---

**AVISO:** Este é um documento vivo. Atualizar conforme a migração progride e novos aprendizados surgem.
