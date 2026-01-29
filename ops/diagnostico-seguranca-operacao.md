# Diagnostico de seguranca e operacao (ProntuAI)

Data: 2026-01-29
Escopo: backend (FastAPI), OCR (Textract), RPA (Playwright/BRNET), DB (Neon), storage (S3), front-end (Next/Vercel), jobs/fila, logs/auditoria.

## 1) Arquitetura (alto nivel)
- Front-end: Next (Vercel) -> API backend (notebook local via Nginx/Ngrok)
- Backend: FastAPI + jobs em background
- OCR: AWS Textract (sync/async) + S3 temp
- RPA: Playwright para BRNET
- Validacao: LLM + regras locais
- DB: Postgres (Neon)
- Logs: arquivo local + stdout (JSON opcional)

## 2) Dados sensiveis
- CPF, nome, laudos, exames, historico de atendimento
- Tokens JWT, credenciais BRNET, AWS, OpenAI

## 3) Pontos criticos / riscos
1. RPA e o elo mais fragil (HTML muda, login expira, captcha, timeouts)
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
- RPA com lock global e limites de concorrencia

## 5) Lacunas a enderecar (antes de producao)
- Persistencia de jobs e reprocessamento idempotente
- Observabilidade real (dashboard, alertas, logs estruturados)
- Politicas de retencao/mascara de dados em logs
- Backups e plano de recovery
- Documentacao de operacao (runbook)

## 6) Recomendacoes (prioridade para hoje)
### Alta
- Ativar LOG_FORMAT=json + Loki/Grafana
- Concurrency de RPA = 1, retries controlados, timeouts seguros
- Paginar listagens e evitar fetch pesado
- Rate limit no upload (por IP e por usuario)
- Nginx com timeouts, body size limit, e headers seguros

### Media
- Guardar jobs em Redis ou fila persistente
- Alertas de erro e latencia anormal
- Mascarar CPF nos logs (ou apenas em ambientes externos)

### Baixa
- Feature flags para regras novas
- Melhorar UX com estados de degradacao (ex: BRNET indisponivel)

## 7) Risco residual se for para producao hoje
- Downtime se o notebook cair
- RPA pode falhar com mudanca de HTML
- Escalabilidade limitada (1 RPA, poucos OCR concorrentes)
- Latencia em horario de pico

## 8) Mitigacoes rapidas para hoje
- Rodar em horario controlado
- Alertas de erro (Grafana + log)
- Monitoramento de fila e tempo medio
- Comunicacao clara no front para falhas do BRNET

