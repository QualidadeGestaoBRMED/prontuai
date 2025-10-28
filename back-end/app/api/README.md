# app/api

Esta pasta deve conter os módulos de rotas da API FastAPI, organizados por domínio de negócio.

Sugestão de arquivos:
- `v1_ocr.py`: Rotas relacionadas ao OCR e extração de dados de documentos.
- `v1_faq.py`: Rotas relacionadas ao FAQ/RAG (Perguntas e Respostas).
- `v1_brmed.py`: Rotas relacionadas à automação e consulta BRMED.

Cada arquivo deve definir um `APIRouter` e importar os serviços necessários da pasta `services`.
