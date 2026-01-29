# Observability (Loki + Grafana)

This folder provides a ready-to-run local stack for logs and dashboards.

## What it includes
- Loki (log storage)
- Promtail (log shipper)
- Grafana (dashboards + alerts)

## Prerequisites
- Docker + Docker Compose
- Backend logs written to a file (default: back-end/logs/app.log)

## Backend settings (required)
Set these in back-end/.env (or export as env vars):

- LOG_FORMAT=json
- LOG_FILE=logs/app.log
- LOG_LEVEL=INFO

Restart the backend after applying the env vars.

## Start stack
From repo root:

```bash
cd ops/observability
docker compose up -d
```

Grafana will be at:
- http://localhost:3001
- user: admin
- pass: admin

## Dashboards
- A basic dashboard is provisioned: "ProntuAI - Logs"
- It shows request rate, error rate, RPA failures, and a log panel.

## Alerts
An alert rule is provisioned (Grafana alerting) for error logs.
You must configure a notification channel in Grafana UI:
- Alerting -> Contact points

## Notes
- Promtail is reading: ../../back-end/logs/app.log
- If you move the log file, update promtail-config.yml
- To reset Grafana data, remove the volume: docker volume rm observability_grafana-data
