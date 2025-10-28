# app/services

Esta pasta deve conter a lógica de negócio da aplicação, separada da camada de API.

Sugestão de arquivos:
- `ocr_service.py`: Funções para processar OCR, salvar markdown, extrair informações via LLM.
- `rag_service.py`: Funções para busca vetorial, montagem de prompt e resposta do FAQ.
- `brmed_service.py`: Funções para automação Playwright e consulta BRMED.
- `cache_service.py`: (Opcional) Funções utilitárias para cache Redis.

Cada serviço deve ser independente de framework web e focado em regras de negócio e integração com recursos externos.
