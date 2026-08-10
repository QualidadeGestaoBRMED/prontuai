# Diagnostico de seguranca e operacao (ProntuAI)

Data: 2026-01-29
Escopo: backend (FastAPI), OCR (Textract), API ProntuAI/BRMED, DB (Postgres self-hosted na VPS), storage (S3), front-end (Next/Vercel), jobs/fila, logs/auditoria.

## 1) Arquitetura (alto nivel)
- Front-end: Next (Vercel) -> API backend (notebook local via Nginx/Ngrok)
- Backend: FastAPI + jobs em background
- OCR: AWS Textract (sync/async) + S3 temp
- Consulta de exames obrigatorios: API ProntuAI/BRMED
- Validacao: LLM + regras locais
- DB: Postgres self-hosted (container `prontuai-db` na mesma VPS EC2 do backend, rede interna do Docker; 5432 tambem com bind de teste em 127.0.0.1, acesso externo so via tunel SSH, enquanto valida esse setup)
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
7. Dependencia externa (Textract/OpenAI) -> latencia/indisponibilidade
8. DB e backend na mesma instancia EC2: perda da instancia (disco, falha de
   hardware, zona de disponibilidade) ainda derruba os dois — sem failover
   automatico nem standby/replica. Mitigado por backup diario num bucket
   S3-compativel (fora da VPS) + volume EBS dedicado. O risco de operacao/deploy (deploy ou rollback do backend
   arrastar o banco por engano) foi eliminado ao separar o Postgres em
   compose file proprio (`docker-compose.db.yml`), fora do alcance do
   `docker-compose.yml`/`docker-compose.aws.yml` do backend.
9. Sem TLS "em transito" dentro do host entre backend e Postgres — aceitavel
   porque o trafego backend<->DB fica so na rede interna do Docker (nao
   publicada), independente do bind de teste em 127.0.0.1 usado so para
   tunel SSH de operador humano. Reavaliar se algum dia o DB precisar ser
   acessado de fora do container por outro servico.
10. Volume do Postgres precisa estar num EBS criptografado (dado de saude:
    CPF, laudos, historico de atendimento) — confirmar que a criptografia
    default do EBS esta habilitada na conta/regiao antes de criar o volume.
11. Bind de teste da 5432 em 127.0.0.1 (`docker-compose.db.yml`) existe so
    para permitir tunel SSH durante a validacao deste setup. Nao e exposicao
    publica (nunca publicar em 0.0.0.0 nem abrir 5432 na security group),
    mas e superficie a mais que o "sem porta nenhuma" anterior — remover o
    bloco `ports:` quando o acesso direto deixar de ser necessario.

## 4) Controles existentes
- Middleware com request_id
- Auditoria (POST/PATCH/DELETE) com request_id
- OCR via Textract, com fallback
- Consulta externa via API autenticada
- Postgres acessivel pela rede interna do Docker; acesso humano externo so
  via tunel SSH (5432 em bind 127.0.0.1, nunca publica). Backup diario
  automatizado para bucket S3-compativel com checksum, e script de restore
  para drill periodico (ver `ops/deploy/backup_postgres.sh`,
  `ops/deploy/restore_postgres.sh`)

## 5) Lacunas a enderecar (antes de producao)
- Persistencia de jobs e reprocessamento idempotente
- Observabilidade real (dashboard, alertas, logs estruturados)
- Politicas de retencao/mascara de dados em logs
- Documentacao de operacao (runbook)
- Confirmar criptografia do EBS do volume de dados do Postgres antes de criar
- Configurar lifecycle rule de expiracao no bucket de backup (o script so
  cuida da retencao local)
- Rodar o primeiro drill de restore (`ops/deploy/restore_postgres.sh`) para
  validar o procedimento antes de depender dele num incidente real

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

