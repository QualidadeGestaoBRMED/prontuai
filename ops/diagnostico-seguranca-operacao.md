# Diagnostico de seguranca e operacao (ProntuAI)

Data: 2026-01-29
Escopo: backend (FastAPI), OCR (Textract), API ProntuAI/BRMED, DB (Neon), storage (S3), front-end (Next/Vercel), jobs/fila, logs/auditoria.

## 1) Arquitetura (alto nivel)
- Front-end: Next (Vercel) -> API backend (notebook local via Nginx/Ngrok)
- Backend: FastAPI + jobs em background
- OCR: AWS Textract (sync/async) + S3 temp
- Consulta de exames obrigatorios: API ProntuAI/BRMED
- Validacao: LLM + regras locais
- DB: Postgres (Neon)
- Logs: arquivo local + stdout (JSON opcional)

## 2) Dados sensiveis
- CPF, nome, laudos, exames, historico de atendimento
- Tokens JWT, credenciais BRNET, AWS, OpenAI

## 3) Pontos criticos / riscos
1. Dependencia da API externa de exames obrigatorios (latencia/indisponibilidade)
2. Backend em notebook local (energia, rede, reboot, falta de autoscaling)
3. Fila/jobs sem persistencia forte (perda de job em restart)
4. Logs com dados sensiveis (risco LGPD)
5. Credenciais no .env local (risco de vazamento)
6. Rate limit e uploads (abuso ou estouro de recursos)
7. Dependencia externa (Neon/Textract/OpenAI) -> latencia/indisponibilidade

## 4) Controles existentes
- Middleware com request_id
- Auditoria (POST/PATCH/DELETE) com request_id
- OCR via Textract, com fallback
- Consulta externa via API autenticada

## 5) Lacunas a enderecar (antes de producao)
- Persistencia de jobs e reprocessamento idempotente
- Observabilidade real (dashboard, alertas, logs estruturados)
- Politicas de retencao/mascara de dados em logs
- Backups e plano de recovery
- Documentacao de operacao (runbook)

## 6) Recomendacoes (prioridade para hoje)
### Alta
- Ativar LOG_FORMAT=json + Loki/Grafana
- Timeouts e retries controlados para API externa
- Paginar listagens e evitar fetch pesado
- Rate limit no upload (por IP e por usuario)
- Nginx com timeouts, body size limit, e headers seguros

### Media
- Guardar jobs em Redis ou fila persistente
- Alertas de erro e latencia anormal
- Mascarar CPF nos logs (ou apenas em ambientes externos)

### Baixa
- Feature flags para regras novas
- Melhorar UX com estados de degradacao (ex: API externa indisponivel)

## 7) Risco residual se for para producao hoje
- Downtime se o notebook cair
- API externa pode ficar indisponivel ou lenta
- Escalabilidade limitada pelos limites de OCR e da API externa
- Latencia em horario de pico

## 8) Mitigacoes rapidas para hoje
- Rodar em horario controlado
- Alertas de erro (Grafana + log)
- Monitoramento de fila e tempo medio
- Comunicacao clara no front para falhas da API externa

