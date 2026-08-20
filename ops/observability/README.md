# Observabilidade ProntuAI (Loki + Grafana + Prometheus)

Stack completa de observabilidade para rodar junto ao backend (EC2 ou local):

- **Loki + Promtail** — logs estruturados do backend, com filtros por `user_email` e `request_id`
- **OTel Collector** — recebe métricas e traces do backend por OTLP e republica as métricas em `:8889/metrics`
- **Prometheus** — métricas da API, de negócio (OCR, workflow, API externa) e da máquina
- **Correlação** — os logs carregam `trace_id`/`span_id` das requisições (ver "Correlação log ↔ trace")
- **node_exporter** — CPU/RAM/disco da EC2
- **cAdvisor** — CPU/memória por container
- **postgres_exporter** — métricas do Postgres (conexões, transações, cache hit ratio, tamanho do banco, deadlocks, locks); roda junto do banco em `back-end/docker-compose.db.yml`, não nesta pasta
- **Grafana** — dashboards provisionados + alertas

## 1. Configuração do backend (obrigatório)

No `.env` do backend (`back-end/.env` local, ou o `.env` do deploy na EC2):

```
# Logs estruturados (Loki/Grafana filtram por campos)
LOG_FORMAT=json
LOG_FILE=logs/app.log
LOG_LEVEL=INFO

# Métricas por OTLP para o otel-collector desta stack (bloco completo em
# backend-env.example — todas são variáveis padrão do OTel)
OTEL_SERVICE_NAME=prontuai-backend
OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=production,service.version=2.0.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_COMPRESSION=gzip
OTEL_METRICS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=none
OTEL_LOGS_EXPORTER=none
OTEL_METRIC_EXPORT_INTERVAL=15000
OTEL_PYTHON_EXCLUDED_URLS=health,healthz,readyz,livez,metrics
OTEL_SDK_DISABLED=false

# Erros/exceções no Sentry (crie o projeto em sentry.io — free tier atende)
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

Reinicie o backend após aplicar. As dependências do OpenTelemetry entram no
próximo build da imagem (já estão no `requirements.txt`).

> **O backend não expõe mais `/metrics`.** Ele empurra as métricas por OTLP para
> o `otel-collector`, que as publica em `:8889/metrics` para o Prometheus. Sai
> junto o `METRICS_ENABLED` e a necessidade de bloquear `/metrics` no nginx
> público — não há mais rota a bloquear.
>
> O nome `otel-collector` só resolve se o container do backend estiver na mesma
> rede docker da stack (é o que `BACKEND_DOCKER_NETWORK` configura, abaixo). Com
> o backend rodando direto no host, use `http://127.0.0.1:4318`.

Três detalhes que economizam depuração:

- **`OTEL_SDK_DISABLED=true` é o kill switch.** Desliga toda a telemetria sem
  redeploy de código; tenha isso mapeado como variável de deploy. (A variável
  `OTEL_ENABLED`, usada antes desta migração, não existe mais — se ela estiver
  no `.env`, o backend loga um aviso e a ignora.)
- **`service.namespace` não deve ser definido** em `OTEL_RESOURCE_ATTRIBUTES`:
  o exporter Prometheus do collector monta o rótulo `job` como
  `<namespace>/<name>`, então definir namespace viraria
  `job="brmed/prontuai-backend"` e nenhum painel encontraria as séries. Os
  outros atributos de resource são seguros — vão para a métrica sintética
  `target_info`, não para os rótulos das séries.
- **`OTEL_EXPORTER_OTLP_ENDPOINT` é a base, sem `/v1/metrics`.** As variantes
  por sinal (`OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`) exigem o caminho completo.
  Misturar as duas formas dá 404 silencioso.

### Instrumentações automáticas

Além do FastAPI e do SQLAlchemy, o backend instrumenta (lista obtida com
`opentelemetry-bootstrap -a requirements` sobre o `requirements.txt` real):

| Instrumentação | O que dá **hoje** | O que dá **com traces ligadas** |
|---|---|---|
| `httpx` | métrica `http_client_request_duration_seconds` (painel "Latência das chamadas HTTP de saída") | spans das chamadas à API ProntuAI |
| `requests` | nada (nenhuma chamada no código usa `requests`) | spans, se alguma dependência passar a usar |
| `botocore` | nada | spans do AWS Textract — o caminho crítico do OCR |
| `redis` | nada | spans do rate limiter |
| `threading` / `asyncio` | `trace_id` nas linhas de log emitidas dentro de `asyncio.to_thread` e de `threading.Thread` | spans filhos em vez de spans órfãos |

Desligue qualquer uma sem mexer em código com
`OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=redis,botocore` (aceita também `fastapi`,
`sqlalchemy` e `logging`). Cada uma falha isolada: uma instrumentação
incompatível não derruba as outras nem a exportação das métricas de negócio.

> **Por que a métrica de saída só conta o httpx:** as instrumentações de `httpx`
> e de `requests` emitem `http.client.request.duration` com o mesmo nome e os
> mesmos atributos, em escopos diferentes. O SDK mantém os dois separados, mas o
> exporter Prometheus do collector achata o escopo — as séries ficam idênticas e
> uma sobrescreve a outra, perdendo ~50% das amostras sem erro nenhum. Por isso
> uma View descarta a métrica do escopo `requests` (ver `app/core/metrics.py`);
> os spans dele continuam sendo gerados.

### Correlação log ↔ trace

Com `OTEL_PYTHON_LOG_CORRELATION=true`, toda linha de log emitida **dentro de
uma requisição** ganha `trace_id` e `span_id`, ao lado do `request_id` que já
existia:

```json
{"timestamp":"...","level":"INFO","logger":"app.api","message":"processando documento",
 "request_id":"req-abc-123","trace_id":"28389a8d…","span_id":"a5b390a2…","document_id":"doc-42"}
```

Linhas fora de requisição (startup, job em background) não recebem os campos —
o instrumentador do OTel injeta `"0"` nesses casos e o `JsonFormatter` descarta.

No Loki, filtre com `| json | trace_id="28389a8d…"`. O campo **não** é label de
propósito: seria um stream novo por requisição (ver `promtail-config.yml`). O
datasource Loki já tem um *derived field* que o destaca no detalhe do log.

Duas ressalvas honestas:

- **O trace_id ainda não é clicável.** Falta um datasource de traces. Quando um
  Tempo entrar na stack, complete o `derivedFields` em
  `grafana/provisioning/datasources/loki.yml` (as duas linhas estão lá,
  comentadas) e ligue `OTEL_TRACES_EXPORTER=otlp` no `.env` do backend.
- **O sampler é `parentbased_always_on`** por isso: com amostragem de 10%, 90%
  dos `trace_id` logados apontariam para traces que nunca foram gravadas. Como
  as traces não são exportadas hoje, 100% custa apenas o span em memória.

### Workers do gunicorn

O SDK é inicializado no import de `main.py`, o que só é seguro porque o gunicorn
carrega a aplicação **dentro de cada worker, depois do `fork()`** — o
comportamento padrão quando `--preload` não é usado (ver `entrypoint.sh`). A
thread de exportação do OTel não sobrevive a um fork: se `--preload` for ligado
algum dia, os workers ficam sem telemetria (ou travam), e o setup precisa migrar
para um hook `post_fork` num `gunicorn.conf.py`.

Com `WORKERS>1` cada processo exporta suas próprias séries, distinguidas por
`instance=<host>-<pid>`. Por isso os painéis e alertas agregam com `sum()`: sem
isso o limiar passaria a ser por processo, não por serviço.

## 2. Configuração da stack

Crie `ops/observability/.env`:

```
# Caminho dos logs do backend NO HOST (na EC2, o diretório montado pelo compose do backend)
BACKEND_LOGS_PATH=/caminho/para/back-end/logs

# Troque a senha do Grafana!
GRAFANA_ADMIN_PASSWORD=uma-senha-forte

# Mantenha 127.0.0.1 — nunca exponha Grafana/Loki/Prometheus publicamente
OBS_BIND_ADDRESS=127.0.0.1

# Rede docker do compose do backend (é por ela que o backend alcança o
# otel-collector pelo nome do serviço). Descubra com:
#   docker inspect prontuai-backend --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}'
BACKEND_DOCKER_NETWORK=back-end_default

# Rede docker do Postgres (back-end/docker-compose.db.yml). Nome fixo, quase
# nunca precisa mudar:
DB_DOCKER_NETWORK=prontuai-db-net
```

> O compose do backend E o `docker-compose.db.yml` (Postgres) precisam estar
> rodando antes de subir esta stack (as redes externas `BACKEND_DOCKER_NETWORK`
> e `DB_DOCKER_NETWORK` precisam existir).

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

- **ProntuAI - Logs & Auditoria** — busca de logs com filtros `user_email`/`request_id`;
  row **Atividade** com usuários ativos (24h, distintos por `user_email` no Loki);
  row **Por Usuário** com ranking de documentos processados e falhas nas últimas 24h
  (via Loki, `topk` sobre `count_over_time`)
- **ProntuAI - Aplicação (API / Negócio / Qualidade)** — RPS, latência p95, 5xx,
  documentos enviados e processados por hora, duração do OCR por motor,
  timeouts/fallbacks do Textract, consultas à API externa e qualidade de entrega
  (score de confiança, exames faltantes, aprovação/rejeição na revisão humana);
  row **Por Clínica** com volume, taxa de erro, score de confiança médio, taxa
  de rejeição na revisão e usuários criados, cada um quebrado por `clinica_nome`
  (Prometheus); row **Cadastros** com totais de clínicas/usuários criados (30d,
  por papel). Use o filtro **Clínica** no topo do dashboard para restringir
  todos os painéis de "Por Clínica" a uma ou mais clínicas específicas
  (ex.: selecionar só "BRMED" mostra apenas os números dela)
- **ProntuAI - Infra (EC2)** — CPU/RAM/disco da máquina, memória por container e
  row **Picos & Armazenamento** (pico de RAM/disco no período selecionado,
  armazenamento usado em GB)
- **ProntuAI - Postgres** — conexões ativas por banco, cache hit ratio,
  transações/s (commit vs rollback), tuplas lidas/escritas por segundo,
  deadlocks, locks por modo; row **Resumo** com status up/down, tamanho do
  banco em GB e `max_connections` configurado

### Por que clínica é label Prometheus e usuário não

Clínica é um conjunto pequeno e estável (dezenas) — vira label direto nas
métricas (`clinica_id`/`clinica_nome`) sem risco de cardinalidade. Usuário
pode crescer bastante e cresce por padrão (novo cadastro = nova série se
virasse label), então a visão por usuário usa consulta sobre o corpo JSON dos
logs no Loki (`| json`), nunca como label — mesmo motivo que fez a ingestão de
logs travar antes com `request_id`/`user_email` como label (ver seção 5 do
histórico de commits / `promtail-config.yml`).

## 5. Alertas provisionados

| Alerta | Condição | Severidade |
|---|---|---|
| Backend sem scrape | `up == 0` por 2 min | critical |
| Postgres sem scrape | `up{job="postgres"} == 0` por 2 min | critical |
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

O deploy desta pasta é automático: o workflow `observability-deploy.yml` roda a
cada push na `v1` que toque `ops/observability/**`, sincroniza os arquivos para
`/home/ec2-user/prontuai-observability` e recarrega o stack (dashboards e
alertas incluídos). Só o passo 4 (criar o `.env` no servidor) é manual e feito
uma única vez — sem ele o workflow falha com mensagem explicando o que criar.

1. [ ] `LOG_FORMAT=json` + bloco `OTEL_*` (passo 1 acima, incluindo
       `OTEL_SDK_DISABLED=false`) no `.env` do backend; reiniciar
2. [ ] Criar projeto no sentry.io e setar `SENTRY_DSN`
3. [ ] Rebuild/pull da imagem do backend (o `prometheus-fastapi-instrumentator`
       saiu do `requirements.txt`; as métricas agora vêm do OpenTelemetry)
4. [ ] Criar `.env` em `/home/ec2-user/prontuai-observability` na EC2 com
       `BACKEND_LOGS_PATH=/home/ec2-user/prontuai/logs`,
       `BACKEND_DOCKER_NETWORK=prontuai_default` (confirme com
       `docker inspect prontuai-backend`), `DB_DOCKER_NETWORK=prontuai-db-net`
       e `GRAFANA_ADMIN_PASSWORD`
5. [ ] Confirmar que `back-end/docker-compose.db.yml` já está no ar (senão a
       rede externa `prontuai-db-net` não existe e esta stack não sobe)
6. [ ] Rodar o workflow **Observability Deploy** (push ou `workflow_dispatch`)
7. [ ] Conferir targets em http://localhost:9090/targets (todos UP, incluindo
       `postgres` e `otel-collector`)
8. [ ] Confirmar que o backend está empurrando: `prontuai_backend_up` deve
       existir no Prometheus (uma série por worker do gunicorn) com
       `job="prontuai-backend"`. Se não existir, veja os logs do backend —
       `setup_telemetry` loga o motivo de ter desistido
9. [ ] Configurar contact point (e-mail/Slack) no Grafana Alerting
10. [ ] (Recomendado) Alarme CloudWatch `StatusCheckFailed` + auto-recover na EC2 —
       cobre o caso em que a instância inteira cai junto com o Grafana
11. [ ] Verificar folga de RAM: a stack consome ~1–1,5 GB (+ ~30-50MB do postgres_exporter)

## Notas

- Painéis de **Negócio** (documentos processados, OCR, API externa) só populam
  após o primeiro documento processado — antes disso mostram "No Data".
- **Histórico das métricas HTTP**: a migração para o OpenTelemetry renomeou
  `http_requests_total`/`http_request_duration_seconds` para
  `http_server_request_duration_seconds_*` e o rótulo `handler` para
  `http_route`. Os painéis de HTTP começam do zero na data do deploy; os dados
  antigos continuam no TSDB pelos 30 dias de retenção, consultáveis pelo nome
  antigo. As métricas de negócio (`prontuai_*`) mantiveram nome e rótulos, então
  o histórico delas é contínuo.
- Painel **Memória por container**: exige que o Docker do host use o storage
  driver clássico (overlay2, padrão na EC2). Se `docker info` mostrar
  `io.containerd.snapshotter.v1` (comum em desktop de dev), o cAdvisor não
  suporta e o painel fica sem dados — limitação conhecida do cAdvisor.

- Retenção do Loki: 7 dias (`retention_period: 168h` em `loki-config.yml`);
  Prometheus: 30 dias (`--storage.tsdb.retention.time`)
- Para resetar o Grafana: `docker volume rm observability_grafana-data`
- Se mover o arquivo de log, atualize `BACKEND_LOGS_PATH` (compose) — o caminho
  interno `/var/log/prontuai/app.log` do promtail-config.yml não muda
