# Observabilidade ProntuAI (Loki + Grafana + Prometheus)

Stack completa de observabilidade para rodar junto ao backend (EC2 ou local):

- **Loki + Promtail** — logs estruturados do backend, com filtros por `user_email` e `request_id`
- **Prometheus** — métricas da API (`/metrics`), de negócio (OCR, workflow, API externa) e da máquina
- **node_exporter** — CPU/RAM/disco da EC2
- **cAdvisor** — CPU/memória por container
- **Grafana** — dashboards provisionados + alertas

## 1. Configuração do backend (obrigatório)

No `.env` do backend (`back-end/.env` local, ou o `.env` do deploy na EC2):

```
# Logs estruturados (Loki/Grafana filtram por campos)
LOG_FORMAT=json
LOG_FILE=logs/app.log
LOG_LEVEL=INFO

# Métricas Prometheus em /metrics
METRICS_ENABLED=true

# Erros/exceções no Sentry (crie o projeto em sentry.io — free tier atende)
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

Reinicie o backend após aplicar. A dependência `prometheus-fastapi-instrumentator`
entra no próximo build da imagem (já está no `requirements.txt`).

> **Segurança**: `/metrics` fica exposto na API. O Prometheus coleta pela porta
> interna (`127.0.0.1:8080` no host). Se o nginx público faz proxy para o backend,
> bloqueie a rota: `location /metrics { deny all; }`.

## 2. Configuração da stack

Crie `ops/observability/.env`:

```
# Caminho dos logs do backend NO HOST (na EC2, o diretório montado pelo compose do backend)
BACKEND_LOGS_PATH=/caminho/para/back-end/logs

# Troque a senha do Grafana!
GRAFANA_ADMIN_PASSWORD=uma-senha-forte

# Mantenha 127.0.0.1 — nunca exponha Grafana/Loki/Prometheus publicamente
OBS_BIND_ADDRESS=127.0.0.1

# Rede docker do compose do backend (o Prometheus coleta /metrics direto do
# container). Descubra com:
#   docker inspect prontuai-backend --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}'
BACKEND_DOCKER_NETWORK=back-end_default
```

> O compose do backend precisa estar rodando antes de subir esta stack
> (a rede externa `BACKEND_DOCKER_NETWORK` precisa existir).

## 3. Subir a stack

```bash
cd ops/observability
docker compose up -d
```

Serviços (todos em 127.0.0.1):
- Grafana: http://localhost:3001 (admin / $GRAFANA_ADMIN_PASSWORD)
- Prometheus: http://localhost:9090
- Loki: http://localhost:3100

### Acesso na EC2

Como as portas ficam em 127.0.0.1, acesse via túnel SSH:

```bash
ssh -L 3001:127.0.0.1:3001 usuario@ec2-host
# depois abra http://localhost:3001
```

Alternativa: publicar o Grafana atrás do nginx existente com HTTPS + autenticação.

## 4. Dashboards provisionados

- **ProntuAI - Logs & Auditoria** — busca de logs com filtros `user_email`/`request_id`
- **ProntuAI - Aplicação (API / Negócio / Qualidade)** — RPS, latência p95, 5xx,
  documentos processados/hora, duração do OCR por motor, timeouts/fallbacks do
  Textract, consultas à API externa e qualidade de entrega (score de confiança,
  exames faltantes, aprovação/rejeição na revisão humana)
- **ProntuAI - Infra (EC2)** — CPU/RAM/disco da máquina e memória por container

## 5. Alertas provisionados

| Alerta | Condição | Severidade |
|---|---|---|
| Backend sem scrape | `up == 0` por 2 min | critical |
| Erros nos logs | rate de `level=ERROR` > 0 por 2 min | warning |
| Taxa de 5xx | > 5% por 5 min | critical |
| OCR degradado | p95 > 5 min por 10 min | warning |
| Fallback Docling | qualquer ocorrência na última hora | warning |
| Qualidade degradada | mediana do score de confiança < 60 por 30 min | warning |
| Disco | > 85% por 5 min | warning |
| Memória | > 90% por 5 min | critical |

**Destino das notificações** (e-mail/Slack) deve ser configurado uma vez na UI:
Alerting → Contact points → default.

## 6. Checklist de implantação na EC2

1. [ ] `LOG_FORMAT=json` + `METRICS_ENABLED=true` no `.env` do backend; reiniciar
2. [ ] Criar projeto no sentry.io e setar `SENTRY_DSN`
3. [ ] Rebuild/pull da imagem do backend (nova dependência de métricas)
4. [ ] Criar `ops/observability/.env` com `BACKEND_LOGS_PATH` e senha do Grafana
5. [ ] `docker compose up -d` em `ops/observability`
6. [ ] Conferir targets em http://localhost:9090/targets (todos UP)
7. [ ] Bloquear `/metrics` no nginx público, se houver proxy para o backend
8. [ ] Configurar contact point (e-mail/Slack) no Grafana Alerting
9. [ ] (Recomendado) Alarme CloudWatch `StatusCheckFailed` + auto-recover na EC2 —
       cobre o caso em que a instância inteira cai junto com o Grafana
10. [ ] Verificar folga de RAM: a stack consome ~1–1,5 GB

## Notas

- Painéis de **Negócio** (documentos processados, OCR, API externa) só populam
  após o primeiro documento processado — antes disso mostram "No Data".
- Painel **Memória por container**: exige que o Docker do host use o storage
  driver clássico (overlay2, padrão na EC2). Se `docker info` mostrar
  `io.containerd.snapshotter.v1` (comum em desktop de dev), o cAdvisor não
  suporta e o painel fica sem dados — limitação conhecida do cAdvisor.

- Retenção do Loki: 7 dias (`retention_period: 168h` em `loki-config.yml`);
  Prometheus: 30 dias (`--storage.tsdb.retention.time`)
- Para resetar o Grafana: `docker volume rm observability_grafana-data`
- Se mover o arquivo de log, atualize `BACKEND_LOGS_PATH` (compose) — o caminho
  interno `/var/log/prontuai/app.log` do promtail-config.yml não muda
