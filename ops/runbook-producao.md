# Runbook de producao (ProntuAI)

## Objetivo
Guia rapido para operar o backend na VPS com frontend apontando para `api.prontuai.grupobrmed.com.br`.

## 1) Start/Stop
### Backend
```
cd back-end
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Observabilidade (logs)
```
cd ops/observability
docker compose up -d
```

### Stop
```
# backend: Ctrl+C
cd ops/observability
docker compose down
```

## 2) Variaveis essenciais
- LOG_FORMAT=json
- LOG_FILE=logs/app.log
- LOG_LEVEL=INFO
- AUDIT_LOG_ENABLED=true
- DOCUMENT_PROCESS_CONCURRENCY=2
- OCR_CONCURRENCY=2

## 3) Health check
- Backend local na VPS: http://127.0.0.1:8080/health
- Backend público: https://api.prontuai.grupobrmed.com.br/health
- Logs: Grafana http://localhost:3001

## 4) Incidente: API ProntuAI falhando
Sintoma: prontuai_api_failed ou erro 502 na consulta de exames obrigatórios.
Acoes:
1) Ver logs da chamada externa e status HTTP retornado
2) Conferir PRONTUAI_API_BASE_URL, PRONTUAI_SERVICE_TOKEN e PRONTUAI_CLIENT_NAME
3) Reprocessar após normalização da API externa

## 5) Incidente: OCR lento
1) Conferir Textract status
2) Ver tamanhos de PDF e tempo por MB
3) Ajustar OCR_CONCURRENCY

## 6) Incidente: API lenta
1) Ver logs (request.completed com duration_ms)
2) Conferir DB latencia
3) Reduzir concorrencia temporariamente

## 7) Backup e recovery
- Backup do banco Neon (manual via painel)
- Export periodico de documentos, logs e auditoria

## 8) Rollback
- Manter zip do backend anterior
- Se quebra, voltar commit/tag anterior
