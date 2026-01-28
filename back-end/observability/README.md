# Observabilidade (Loki / Grafana / Datadog)

Este pacote deixa pronto o export de logs do backend para Loki ou Datadog, além de dashboards iniciais com filtros por `user_email` e `request_id`.

## Pré-requisito (logs estruturados)
Defina no backend:

```
LOG_FORMAT=json
LOG_FILE=logs/app.log
```

Isso garante que Loki/Datadog consigam filtrar por campos como `user_email`, `request_id`, `path`, `method` e `status_code`.

---

## Loki + Grafana (local)

Suba a stack de observabilidade:

```
cd back-end/observability

docker compose -f docker-compose.loki.yml up -d
```

- Grafana: http://localhost:3001 (admin / admin)
- Loki: http://localhost:3100

O dashboard `ProntuAI - Logs & Auditoria` é provisionado automaticamente.

### Filtros no Grafana
No dashboard, use os filtros (text box) para:
- `user_email`
- `request_id`

Exemplos:
- `user_email = gabriel.rodrigues@grupobrmed.com.br`
- `request_id = 6b1c2d0a-...`

---

## Datadog (SaaS)

Crie o arquivo `.env` com:

```
DD_API_KEY=xxx
DD_SITE=datadoghq.com
DD_ENV=production
DD_SERVICE=prontuai-backend
```

Suba o agente:

```
cd back-end/observability

docker compose -f docker-compose.datadog.yml up -d
```

O agente já coleta o arquivo `logs/app.log`.

### Dashboard Datadog
Use o JSON em `datadog/dashboards/prontuai-logs.json` e importe no Datadog.
Ele cria filtros por:
- `@user_email`
- `@request_id`

---

## Observação importante
Campos como `user_email` e `request_id` ficam dentro do JSON do log. Em Loki, o dashboard usa `| json` para filtrar. Em Datadog, filtros são feitos via `@user_email` e `@request_id`.
