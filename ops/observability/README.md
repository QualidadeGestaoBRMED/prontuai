# Observabilidade do ProntuAI

A telemetria não é mais processada nesta máquina. Todos os sinais saem por um
único canal **OTLP autenticado** para o `otel-collector` da **VPS Oracle**, onde
ficam o Tempo, o Loki, o Prometheus e o Grafana — compartilhados entre os
projetos do time.

```
EC2 (backend)                          VPS Oracle (dashboard)
┌────────────────────────────┐         ┌──────────────────────────────────┐
│ backend                    │         │ otel-collector :4317/:4318       │
│  ├─ métricas ──┐           │  OTLP   │   bearertokenauth                │
│  ├─ traces ────┼─ OTLP ────┼────────►│     ├─ traces  → Tempo           │
│  ├─ logs ──────┘           │  + token│     ├─ logs    → Loki            │
│  └─ app.log (local, roda-  │         │     └─ métricas→ :8889 (scrape)  │
│     do; ninguém lê)        │         │                                  │
│                            │         │ Prometheus · Tempo · Loki        │
│ otel-agent ────────────────┼────────►│ Grafana :3001                    │
│  └─ scrape local de        │         └──────────────────────────────────┘
│     node_exporter,         │
│     cAdvisor, pg-exporter  │
└────────────────────────────┘
```

Esta pasta contém **só o lado da EC2**. A configuração do lado Oracle está em
`otel/` na raiz do repo, montada pelo `docker-compose.yml` da raiz.

## Por que ainda existe um agente aqui

Três fontes de métrica não vêm do app e não teriam como sair por OTLP sozinhas:

| Fonte | O que dá |
|---|---|
| `node_exporter` | CPU, RAM e disco da máquina (alertas de disco >85% e RAM >90%) |
| `cAdvisor` | memória e CPU por container |
| `prontuai-db-exporter` | Postgres — roda junto do banco em `back-end/docker-compose.db.yml` |

O agente faz scrape local desses três e encaminha por OTLP. Usa o receiver
`prometheus`, e não os receivers nativos do OTel (`hostmetrics`, `docker_stats`,
`postgresql`), de propósito: os nativos emitiriam nomes de semconv
(`system.filesystem.*`, `postgresql.*`) e obrigariam a reescrever as 16 queries
dos painéis de infra e de Postgres, cortando o histórico. Com o receiver
`prometheus` os nomes chegam idênticos do outro lado (`node_*`, `container_*`,
`pg_*`) — inclusive o `up`, de que depende o alerta "Postgres sem scrape".

O agente tem **fila em disco** (`file_storage`): se o link com a Oracle cair, ele
segura os pontos em vez de descartar.

## Configuração

### 1. `.env` desta pasta, na EC2

```
OTEL_GATEWAY_ENDPOINT=obs.exemplo.com:4317
OTEL_AUTH_TOKEN=<mesmo token do coletor da Oracle>
OBS_BIND_ADDRESS=127.0.0.1
DB_DOCKER_NETWORK=prontuai-db-net
```

### 2. `.env` do backend

Bloco `OTEL_*` completo em `backend-env.example`. O mínimo:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://obs.exemplo.com:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20<token>
OTEL_METRICS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
```

O `%20` é obrigatório — é o espaço depois de `Bearer`. Sem o URL-encoding o
coletor responde 401.

Sai do `.env`: `METRICS_ENABLED` e `OTEL_ENABLED` (o backend loga um aviso e
ignora esta última; o kill switch agora é `OTEL_SDK_DISABLED`).

## Logs: os dois caminhos, de propósito

O backend **escreve o arquivo local e empurra por OTLP**, e as duas coisas
servem a propósitos diferentes:

- `logs/app.log` é a fonte operacional da máquina e onde caem os logs de crash,
  que não sobrevivem ao flush do exportador. **Nada o lê** — não há mais
  promtail. Era justamente um promtail seguindo um arquivo de dezenas de MB que
  pesava na máquina.
- O caminho OTLP é o correlacionado: chega ao Loki com `trace_id`, e o Grafana
  transforma isso em link para o trace no Tempo.

O arquivo agora **rotaciona** (`LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`) —
antes era um `FileHandler` puro, que crescia sem limite.

Para cortar volume de rede sem perder detalhe no disco, suba `OTEL_LOG_LEVEL`
(ex.: `WARNING`). Cuidado: o dashboard de exploração filtra linhas INFO
(`request.completed`, `workflow_completed`), que desapareceriam.

### Consultar no Loki

A linha chega como envelope OTLP, então o texto está em `body` e os campos
estruturados em `attributes`, que o `| json` achata com `_`:

```logql
{job="prontuai-backend"} | json | attributes_user_email="medico@brmed.com.br"
{job="prontuai-backend", level="ERROR"}
```

`job` e `level` são labels indexados (vêm de `service.name` e da severidade).
`user_email`, `cpf`, `request_id` e `trace_id` ficam em *structured metadata* —
filtráveis, mas **nunca** labels: viraria um stream por requisição.

## Deploy

Automático: o workflow `observability-deploy.yml` roda a cada push na `v1` que
toque `ops/observability/**`, sincroniza para `/home/ec2-user/prontuai-observability`
e recarrega. Só criar o `.env` no servidor é manual (uma vez).

O `--remove-orphans` do workflow derruba os containers da stack antiga
(`grafana`, `loki`, `prometheus`, `promtail`) na primeira execução após esta
migração.

Depois de subir, confirme na Oracle:

- `prontuai_backend_up` existe no Prometheus com `job="prontuai-backend"`
- `up{job="postgres"}` e `up{job="node"}` existem (vieram pelo agente)
- há streams em `{job="prontuai-backend"}` no Loki
- o backend aparece no Tempo

Se não, os logs do backend dizem o motivo: `setup_telemetry` loga por que
desistiu. E `docker compose logs otel-agent` mostra falha de auth ou de rede.

## Workers do gunicorn

O SDK é inicializado no import de `main.py`, o que só é seguro porque o gunicorn
carrega a aplicação **dentro de cada worker, depois do `fork()`** — o padrão
quando `--preload` não é usado (ver `entrypoint.sh`). A thread de exportação do
OTel não sobrevive a um fork: se `--preload` for ligado, os workers ficam sem
telemetria, e o setup precisa migrar para um hook `post_fork`.

Com `WORKERS>1` cada processo exporta suas próprias séries, distinguidas por
`instance=<host>-<pid>`; por isso painéis e alertas agregam com `sum()`. Nos
logs esse atributo é **removido** pelo coletor da Oracle, senão cada deploy
criaria um stream novo no Loki.
