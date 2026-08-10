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
Sintoma: prontuai_api_failed ou erro 502 na consulta de exames obrigatorios.
Acoes:
1) Ver logs da chamada externa e status HTTP retornado
2) Conferir PRONTUAI_API_BASE_URL, PRONTUAI_SERVICE_TOKEN e PRONTUAI_CLIENT_NAME
3) Reprocessar apos normalizacao da API externa

## 5) Incidente: OCR lento
1) Conferir Textract status
2) Ver tamanhos de PDF e tempo por MB
3) Ajustar OCR_CONCURRENCY

## 6) Incidente: API lenta
1) Ver logs (request.completed com duration_ms)
2) Conferir DB latencia
3) Reduzir concorrencia temporariamente

## 7) Backup e recovery
- Banco Postgres roda na propria VPS (container `prontuai-db`), num compose
  file **separado** do backend (`back-end/docker-compose.db.yml`, nao
  `docker-compose.aws.yml`) para que deploy/rollback/panic-restore do backend
  nunca derrubem o banco junto. Acessivel pela rede interna do Docker (rede
  externa `prontuai-db-net`); a 5432 tambem tem bind de teste em
  `127.0.0.1` no host (nunca `0.0.0.0`, nunca aberta na security group) so
  para permitir acesso via tunel SSH enquanto o setup esta em validacao —
  ver "Acesso ao banco" em `ops/deploy/aws-vps-ghcr.md`.
- Backup automatico diario via systemd timer (`ops/deploy/systemd/`), rodando
  `ops/deploy/backup_postgres.sh`: `pg_dump -Fc` do container -> upload para
  bucket S3-compativel (AWS S3 ou Cloudflare R2 — mesma API), com checksum.
  Ver `ops/deploy/systemd/README.md` para instalar/verificar.
- Restore/drill: `ops/deploy/restore_postgres.sh <s3://.../arquivo.dump>`
  restaura por padrao num banco descartavel (`<db>_restore_drill`), nunca em
  producao, a menos que rode com `RESTORE_INTO_PROD=1 ... --into-prod` e
  confirmacao explicita. Fazer esse drill pelo menos trimestralmente.
- Retencao: local (`BACKUP_RETENTION_DAYS`, default 35 dias) + lifecycle rule
  no bucket (configurar manualmente, o script nao apaga nada remoto).
- Export periodico de documentos, logs e auditoria (mantido como antes).
- Volume de dados do Postgres (`./pgdata` no compose) deve ficar num device/EBS
  dedicado e criptografado, separado do volume raiz da instancia.

## 8) Rollback
- Manter zip do backend anterior
- Se quebra, voltar commit/tag anterior
