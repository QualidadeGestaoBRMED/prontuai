# ProntuAI

Plataforma de validação de documentos médicos com IA para a BR MED.
Fluxo principal: upload → OCR → regras BRNET → comparação inteligente (embeddings + GPT).

## Estrutura
prontuai/
├─ front-end/   # Next.js (App Router)
└─ back-end/    # FastAPI (Python)


- Detalhes do front: ver front-end/README.md

- Detalhes do back: ver back-end/README.md

## Como rodar (bem rápido)

Front: cd front-end && npm install && npm run dev → http://localhost:3000

Back: cd back-end && pip install -r requirements.txt && uvicorn main:app --reload → http://localhost:8000

## Observações

Autenticação via Google (NextAuth) restrita a @grupobrmed.com.br (ver front-end).

Integração com BRNET e OCR ficam no back-end.

Cada subprojeto tem seu próprio README com instruções completas.