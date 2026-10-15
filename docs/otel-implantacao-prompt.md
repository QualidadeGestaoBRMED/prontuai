# Prompt — Implantar OpenTelemetry num serviço Python/FastAPI

Use este documento como prompt para introduzir OpenTelemetry num serviço que
exporta telemetria para um coletor compartilhado. Ele descreve um método, não um
resultado: a ordem das fases importa, porque cada uma depende de fatos que a
anterior levanta.

A premissa central: **meça antes de escrever.** Quase toda decisão abaixo parece
óbvia até você observar o que o SDK e o coletor realmente emitem. As doze
armadilhas no fim deste documento foram todas encontradas medindo, não lendo
documentação — e cada uma delas teria passado silenciosa em revisão de código.

---

## Fase 0 — Levante os fatos do destino

Não escreva uma linha de configuração antes de saber para onde a telemetria vai.
Cada versão habilita ou proíbe um caminho inteiro.

Descubra e anote:

- **Versão do coletor.** Opções de configuração e componentes mudam entre
  minors, e componentes são depreciados e removidos. Valide sua config contra a
  versão exata que vai rodar em produção.
- **Versão do Prometheus.** 3.x aceita OTLP nativo (`--web.enable-otlp-receiver`);
  2.x só faz scrape. Isso decide se o coletor empurra métricas ou se as expõe
  para serem coletadas — e muda o desenho dos rótulos.
- **Versão do Loki.** 3.x ingere OTLP nativamente; 2.x não. Isso decide se os
  logs podem viajar no mesmo canal ou precisam de um caminho próprio.
- **Existe backend de traces?** Sem Tempo/Jaeger, exportar spans é gastar CPU
  para o coletor descartar.
- **Topologia e autenticação.** O coletor é local ou está em outra máquina? Se
  for remoto, o canal precisa de token e de TLS — telemetria carrega nome de
  rota, identificadores de usuário e atributos de negócio no payload.
- **O que já é coletado por scrape local e não vem do app.** Métricas de host, de
  container e de banco costumam vir de exporters. Elas não têm como sair por
  OTLP sozinhas, e alguém precisa decidir o destino delas.

## Fase 1 — Defina a identidade do serviço

Três atributos de resource, e um que você deve deixar de fora.

- **`service.name`** é a identidade. No caminho de scrape ele se torna o rótulo
  `job` das métricas *e* o label `job` dos streams de log. Trocar depois quebra
  todo painel e todo alerta.
- **`service.instance.id`** precisa ser único **por processo**, não por máquina.
  Com múltiplos workers, o mesmo instance faz as séries de cada processo
  colidirem numa só e os valores oscilarem. Use algo como `<host>-<pid>`.
- **`service.version`** e **`deployment.environment.name`** (nome atual no
  semconv; `deployment.environment` está depreciado) podem entrar livremente:
  não afetam rótulo, vão para a métrica sintética `target_info`.
- **`service.namespace`** — não defina. Ver armadilha 3.

## Fase 2 — Configure por variável de ambiente, não por parâmetro

Quase toda a configuração do SDK é feita por env var, e isso é intencional:
permite mudar comportamento sem tocar em código. Prefira sempre a variável
padrão a um parâmetro no código.

O SDK honra nativamente, sem você escrever nada:

| Variável | Efeito |
|---|---|
| `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | identidade, lidas por `Resource.create({})` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` e afins | destino, protocolo, headers, compressão, timeout |
| `OTEL_TRACES_SAMPLER`, `..._ARG` | amostragem, lida por `TracerProvider()` |
| `OTEL_METRIC_EXPORT_INTERVAL` | intervalo, lido pelo reader |
| `OTEL_BSP_*`, `OTEL_ATTRIBUTE_*_LIMIT` | batching e limites |
| `OTEL_PYTHON_EXCLUDED_URLS` | rotas fora da instrumentação |
| `OTEL_SDK_DISABLED` | kill switch — desliga tudo sem redeploy |

O SDK **não** honra em setup manual (só pela auto-instrumentação), então você
precisa checar no código:

- `OTEL_{TRACES,METRICS,LOGS}_EXPORTER` — ler e decidir se monta cada pipeline.
- `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` — ler e filtrar a lista.
- `OTEL_PYTHON_LOG_CORRELATION` — ver armadilha 9 antes de usar.

Cuidado com o endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT` é a **base**, sem
`/v1/metrics`. As variantes por sinal (`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`)
exigem o caminho **completo**. Misturar as duas formas dá 404 silencioso.

Mapeie `OTEL_SDK_DISABLED` como variável de deploy desde o primeiro dia.

## Fase 3 — Meça o que o SDK emite

Antes de escrever config de coletor, query de painel ou regra de alerta, observe
o que sai de verdade. Um script de dez linhas com um reader em memória responde:

- **nome exato** do instrumento e sua **unidade**;
- **quais atributos** ele carrega (é aqui que a cardinalidade se decide);
- **quais buckets** um histograma usa.

Depois meça o **round-trip completo**: empurre por OTLP para o coletor real, na
versão real, e compare o que sai do outro lado com o que entrou. Nomes ganham e
perdem sufixos nessa travessia, e escopos podem colidir.

Rode o mesmo teste na **versão mínima** que você declarar na dependência. O
comportamento não é estável entre versões — a armadilha 4 é exatamente isso.

## Fase 4 — Trate cardinalidade como orçamento

O jeito mais rápido de derrubar um Prometheus é colocar um identificador em
atributo de métrica. Vale para os três sinais, com efeitos diferentes: séries no
Prometheus, streams no Loki, agregações inúteis nas traces.

- Ligue o **opt-in de semconv** da sua instrumentação HTTP. Sem ele o rótulo
  costuma ser o caminho cru da URL — uma série nova por recurso (armadilha 5).
- Rotule por **template de rota**, nunca por caminho concreto.
- Atributos de negócio só entram se forem **limitados por natureza** (dezenas de
  valores, não milhares). Papel de usuário: sim. E-mail de usuário: nunca.
- No Loki, **nunca** promova a label: identificador de requisição, `trace_id`,
  `service.instance.id`. Eles continuam filtráveis em structured metadata.

## Fase 5 — Use Views para o que o default erra

Duas situações pedem View explícita:

- **Buckets de histograma.** O default do SDK é largo e genérico, inútil para
  duração em segundos. Declare os limites que o seu domínio exige — e declare
  também para os histogramas da instrumentação, não só para os seus.
- **Colisão entre escopos.** Duas instrumentações podem emitir o mesmo nome de
  métrica com os mesmos atributos. Restrinja a View por escopo (`meter_name`) e
  descarte o escopo que não interessa. Atenção: quando duas Views casam com o
  mesmo instrumento, **as duas se aplicam** — restringir uma exige restringir a
  outra.

## Fase 6 — Correlacione logs com traces

O ganho concreto da adoção é pular de um trace para as linhas de log daquela
requisição. Para isso:

- Registre o **TracerProvider mesmo sem exportar traces**. Sem provider, o span
  corrente é inválido e nenhum `trace_id` aparece nos logs.
- Use amostragem **`always_on`** enquanto o volume permitir. Com 10%, nove de
  cada dez `trace_id` nos logs apontariam para traces que nunca foram gravadas.
- Injete o contexto da requisição **no LogRecord**, não só no formatter. Ver
  armadilha 10.
- Decida os **dois caminhos de log** conscientemente: o arquivo local é a fonte
  operacional e pega log de crash; o OTLP é o caminho correlacionado. Manter os
  dois é a recomendação — mas então nada deve ficar *lendo* o arquivo, e o
  arquivo precisa de rotação (armadilha 12).

## Fase 7 — Verifique segurança de fork

O processador em lote sobe uma thread com lock. Num `fork()`, o filho herda a
memória — inclusive o lock, possivelmente travado — mas não a thread. Resultado:
deadlock ou exportação silenciosamente morta no worker.

Se o servidor de aplicação carrega o app **dentro de cada worker, depois do
fork** (o padrão quando não há pré-carregamento), inicializar no import é
seguro. Documente essa dependência no código: ligar o pré-carregamento depois,
por economia de memória, quebra a telemetria sem erro visível.

A alternativa que elimina a classe do problema: um worker por container, e
escale por réplicas.

## Fase 8 — Valide contra a stack real

Config que valida não é config que funciona. Suba coletor e backends nas
versões reais, gere carga e verifique:

- **todas** as queries de painel e alerta rodam e retornam dados — não uma
  amostra, todas;
- os valores fazem sentido (uma taxa de erro conhecida bate com a esperada);
- a cardinalidade é a prevista (N requisições com identificadores distintos
  produzem quantas séries?);
- os rótulos sobreviveram à travessia;
- **quanto tempo leva** para o sistema perceber que o app caiu. Meça, não
  presuma: essa é a armadilha 1.

---

## As doze armadilhas

Todas encontradas medindo. Nenhuma emite erro.

**1 · Timestamp explícito desliga o tratamento de staleness.**
Com timestamps na exposição, o Prometheus não marca séries ausentes: quando o
app cai, ele segue devolvendo o último valor por até 5 minutos (lookback delta),
e o alerta de queda nunca dispara. Com timestamps desligados: série ausente em
~105s. O custo é o instante virar o do scrape em vez do da medição — desvio de
um intervalo de exportação.

**2 · Sem `honor_labels`, o `job` do coletor é sobrescrito.**
O coletor rotula cada série com o `job` vindo do `service.name` do app. O
Prometheus, por padrão, renomeia rótulos conflitantes para `exported_job` e
impõe o `job` do scrape config. Num coletor compartilhado isso colapsa projetos
diferentes num `job` só.

**3 · `service.namespace` reescreve o `job`.**
O exporter Prometheus do coletor monta o rótulo como `<namespace>/<name>`.
Definir namespace transforma `job="meu-servico"` em `job="ns/meu-servico"` e
nenhum seletor encontra as séries. No caminho OTLP nativo do Prometheus 3.x o
namespace viraria um label próprio — o comportamento depende do caminho.

**4 · Buckets recomendados pelo semconv são ignorados por SDKs mais antigos.**
Numa versão mais nova, o histograma de latência HTTP nasce com limites de
0,005 a 10 s. Numa mais antiga, cai nos limites default do SDK, de 0 a 10000 —
para um histograma em **segundos**, isso joga todo o tráfego no primeiro bucket
e zera o p95. Declare a View e o resultado fica igual em qualquer versão.

**5 · Sem o opt-in de semconv, o rótulo é o caminho cru.**
A instrumentação passa a usar o caminho concreto em vez do template da rota: uma
série nova por recurso acessado. Medido com o opt-in: nove mil requisições com
identificadores aleatórios colapsaram em **duas** séries.

**6 · Dois escopos com a mesma métrica perdem metade das amostras.**
Duas instrumentações de cliente HTTP emitem o mesmo nome com os mesmos
atributos, em escopos diferentes. O SDK mantém os dois separados; o exporter
Prometheus achata o escopo, as séries ficam idênticas e uma sobrescreve a outra.
Medido: 40 chamadas, 20 registradas. Nem `enable_open_metrics` preserva o
escopo.

**7 · `service.instance.id` como label do Loki cria um stream por deploy.**
O exporter promove esse atributo a label. Com o valor sendo `<host>-<pid>`, cada
restart e cada worker gera um stream novo. Remova o atributo **apenas no
pipeline de logs** — nas métricas ele é necessário.

**8 · O instrumentor de logging não injeta nada por padrão.**
Chamar `instrument()` roda sem erro e não faz nada. A injeção depende de um
parâmetro explícito de contexto de trace, cujo nome não é óbvio. Confira lendo o
código da versão instalada, não a documentação.

**9 · A variável de correlação de log destrói o seu formatter.**
O atalho que "liga a correlação" também chama a configuração básica de logging e
substitui os handlers já montados. Se você tem formato JSON estruturado, passe
explicitamente o parâmetro que desliga esse comportamento — assim a variável de
ambiente deixa de ser capaz de quebrar o formato.

**10 · Contexto em contextvars não chega ao caminho OTLP.**
Se o seu formatter lê o contexto da requisição direto dos contextvars, o handler
OTLP não o vê: ele só enxerga o que está no LogRecord. Os logs chegam ao backend
sem identificador de requisição e sem usuário — justamente os campos pelos quais
se investiga. Instale uma fábrica de LogRecord que copie o contexto para dentro
do record, encadeando com a fábrica anterior.

**11 · `OTEL_LOGS_EXPORTER` sem LoggerProvider é decorativo.**
A variável existe no padrão, mas se o código não monta o provider de logs ela
não tem efeito nenhum. Alguém vai trocá-la para `otlp` e esperar log fluir.
Documente, ou implemente.

**12 · Handler de arquivo sem rotação cresce para sempre.**
Não é uma armadilha de OTel, mas aparece na mesma investigação: um handler de
arquivo simples não rotaciona nada. O arquivo chega a dezenas ou centenas de MB,
e um coletor de logs seguindo esse arquivo é o que pesa na máquina. Se você tirar
o leitor, o arquivo continua crescendo; se mantiver, ele continua pesando.
Rotação resolve os dois.

---

## Ordem de subida

1. Backends e coletor no destino, com o segredo de autenticação criado.
2. Configuração do app, com o kill switch **desligado** — telemetria só liga
   quando o endpoint estiver definido.
3. Rebuild da imagem (as dependências mudaram).
4. Um sinal de heartbeat sempre presente confirma que o caminho funciona antes
   de você depender de qualquer painel. Se não aparecer, o log de inicialização
   da telemetria deve dizer por que ela desistiu — projete essas mensagens.
