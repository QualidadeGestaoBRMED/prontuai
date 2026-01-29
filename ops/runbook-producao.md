# Runbook de producao (ProntuAI)

## Objetivo
Guia rapido para operar o backend no notebook local com front na Vercel.

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
- BRMED_RPA_CONCURRENCY=1
- DOCUMENT_PROCESS_CONCURRENCY=2
- OCR_CONCURRENCY=2

## 3) Health check
- Backend: http://localhost:8000/health
- Logs: Grafana http://localhost:3001

## 4) Incidente: RPA falhando
Sintoma: brmed_failed, tabela nao encontrada.
Acoes:
1) Ver log e debug html/screenshot em back-end/resultados/
2) Testar CPF manualmente no BRNET
3) Reprocessar (se necessario) em horario alternativo
4) Se persistir, desligar RPA e manter OCR + pendente para revisao

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

