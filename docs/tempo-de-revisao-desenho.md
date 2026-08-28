# Desenho — medição do tempo de revisão

**Status:** implementado em 28/08/2026 e validado (ver seção 12). Falta só
fechar os parâmetros da seção 9, que estão nos valores recomendados.
**Data:** 28/08/2026.
**Escopo:** opção 1 do levantamento (cronômetro no cliente + colunas em `documents`).
Alimenta o item "tempo médio de revisão" do dashboard (`plan.md:1077`) e a meta de
redução de 50% (`plan.md:1150`).

---

## 1. Definição da métrica

> **Tempo de revisão** = intervalo entre a abertura da tela de revisão de um documento e o
> clique de confirmação da decisão, descontados os períodos em que a tela comprovadamente
> não estava em uso.

Quatro números saem disso. Os dois primeiros são o produto da instrumentação; os dois
últimos são derivados no BI.

| Métrica | Definição | Origem |
|---|---|---|
| `tempo_revisao_ativo` | soma dos trechos ativos de todas as aberturas do modal daquele documento | `documents.review_active_ms` (novo) |
| `tempo_revisao_bruto` | soma dos trechos de parede das mesmas aberturas, sem desconto de ocioso | `documents.review_wall_ms` (novo) |
| `tempo_de_fila` | `review_opened_at - uploaded_at` | derivado |
| `lead_time` | `reviewed_at - uploaded_at` | derivado (já existe) |

O número que responde "quanto tempo leva revisar um prontuário" é o **ativo**. O bruto não
é redundante: serve para auditar outliers e para vigiar a própria regra de ocioso — se a
razão `ativo / bruto` despencar, a regra está cortando trabalho real, não ocioso.

**Marco inicial:** abertura do modal de detalhes (`checagem/page.tsx:227`), que é a tela
onde a revisão acontece de fato — dados comparados à esquerda, PDF à direita.
**Marco final:** clique em "Confirmar" no `AlertDialog` de aprovação/rejeição, não o clique
em "Aprovar". A digitação da justificativa é parte da revisão e deve contar.

---

## 2. O que muda e o que não muda

Muda:

- 4 colunas novas em `documents` + migração `004`.
- `DocumentUpdate` ganha um bloco opcional `review_timing`.
- `PATCH /v1/documents/{id}` passa a sanitizar e acumular esses valores.
- 1 histograma OTel novo.
- 1 módulo novo no front (`lib/review-timer.ts`) + 1 hook, engatados em 4 pontos de
  `checagem/page.tsx` e 1 prop nova (sem efeito visual) no modal de checagem.

Não muda:

- **Nada visual.** O revisor não vê cronômetro, contador, aviso nem mudança de layout.
- **Nenhuma requisição nova.** A cronometragem viaja no PATCH que já é feito na decisão.
- Nenhum endpoint novo, nenhum escopo de rate limit novo.
- Nenhum campo novo no caminho de leitura (`GET /paged`, `document-mapper.ts`): o front
  escreve, não lê.
- Comportamento com cliente antigo: `review_timing` ausente → PATCH idêntico ao de hoje.

---

## 3. Modelo de dados

```sql
-- back-end/migrations/004_add_review_timing.sql
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS review_opened_at  TIMESTAMP,
  ADD COLUMN IF NOT EXISTS review_active_ms  INTEGER,
  ADD COLUMN IF NOT EXISTS review_wall_ms    INTEGER,
  ADD COLUMN IF NOT EXISTS review_open_count SMALLINT;
```

Semântica:

| Coluna | Semântica | Regra de escrita |
|---|---|---|
| `review_opened_at` | primeira abertura observada da tela, em UTC | `COALESCE(atual, recebido)` — nunca sobrescreve |
| `review_active_ms` | soma dos trechos ativos | acumula: `COALESCE(atual, 0) + recebido` |
| `review_wall_ms` | soma dos trechos de parede | acumula |
| `review_open_count` | quantas vezes a tela foi aberta | acumula |

`NULL` significa "revisão sem instrumentação" (decidida antes do deploy, ou por cliente
antigo, ou cronômetro que falhou) — **não** significa zero. O BI tem que filtrar por
`review_active_ms IS NOT NULL`, e a consulta de cobertura da seção 7 existe para isso.

Notas de operação:

- Quatro colunas nullable sem default são alteração só de catálogo no PG 11+: sem rewrite
  da tabela, lock `ACCESS EXCLUSIVE` de milissegundos. Seguro de rodar no startup.
- Migração automática exige as duas pontas (`app/core/migrations.py:11`), porque não há
  Alembic:

  ```python
  cursor.execute("""
      SELECT column_name FROM information_schema.columns
      WHERE table_name='documents' AND column_name='review_active_ms'
  """)
  if not cursor.fetchone():
      migrations_needed.append("004_add_review_timing.sql")
  ```

- Sem índice novo por ora. As consultas de BI filtram por faixa de `reviewed_at`, que não
  é indexado; no volume atual um seq scan resolve. Reavaliar se a tabela passar de algumas
  centenas de milhares de linhas.
- `purge_old_records.sh` não toca em `documents` (linha 10), então o histórico fica.

---

## 4. Contrato de API

```python
# app/models/document.py
class ReviewTiming(BaseModel):
    """Cronometragem da tela de revisão, medida no cliente.

    As durações vêm de performance.now() (monotônico) — imunes a skew e a ajuste
    de hora do relógio do cliente. started_at é relógio de parede e serve só para
    o tempo de fila.
    """
    started_at: Optional[datetime] = None
    active_ms: Optional[int] = None
    wall_ms: Optional[int] = None
    open_count: Optional[int] = None


class DocumentUpdate(BaseModel):
    ...
    review_timing: Optional[ReviewTiming] = None
```

**Sem constraint nenhuma no schema, de propósito.** `Field(ge=...)` viraria 422 e
derrubaria o PATCH inteiro por causa de um número torto — ou seja, impediria o
revisor de aprovar o documento. Todo limite mora na sanitização abaixo, que
descarta em vez de levantar erro.

Sanitização em `app/services/review_timing.py` — função pura, sem banco, para poder ser
testada com `--noconftest`:

| Verificação | Ação |
|---|---|
| `wall_ms > 4h` | descarta o bloco inteiro, `logger.warning` com `document_id` (sem PII) |
| `active_ms > wall_ms + 2000` | descarta o bloco (inconsistente) |
| `active_ms > wall_ms` (até 2 s) | trunca `active_ms = wall_ms` (arredondamento) |
| `started_at` no futuro além de 24 h, ou mais de 90 dias no passado | descarta **só o `started_at`**: as durações são monotônicas, não dependem do relógio de parede, e continuam válidas |
| `open_count` fora de 1..255 | trunca para a faixa (é SMALLINT no banco) |
| bloco ausente | segue o fluxo atual, sem escrever as colunas |

Descartar em vez de levantar erro é deliberado: uma cronometragem suspeita não pode
impedir o revisor de aprovar o documento.

**Guarda de decisão.** A cronometragem só é gravada quando o PATCH é uma decisão
humana de verdade:

```python
payload.validation_status in ("validated", "rejected")
and is_human_reviewer
and (
    payload.validation_status != document.validation_status
    or not document.reviewed_by
)
```

Comparar só o status **não basta**, e isso apareceu no primeiro teste em staging: a fila
da checagem inclui documentos que a IA já marcou `validated` aguardando confirmação
humana (filtro de `DocumentQueue.CHECAGEM`, `documents.py:199`). Nesses, aprovar manda o
mesmo status que já está no banco — a comparação sozinha descartaria em silêncio o
caminho mais comum de todos. O `not document.reviewed_by` cobre esse caso e continua
bloqueando retry: depois da primeira decisão o revisor está gravado, então um segundo
PATCH idêntico não conta de novo.

Efeito colateral deliberado: o contador `REVISAO_HUMANA`, que usava a condição antiga,
passa a contar também as confirmações em que o humano concorda com a IA. Ele vinha
subcontando desde sempre — o número vai subir no Grafana, e comparação através dessa
data não vale.

Persistência: 1 kwarg novo (`review_timing`, já com os incrementos sanitizados) em
`user_db.update_document` (`database_postgres.py:1431`), só na chamada primária — o `except TypeError` de `documents.py:663` é o caminho de
compatibilidade e já hoje descarta campos.

---

## 5. Cronômetro no front

Módulo puro `front-end/lib/review-timer.ts` + hook `front-end/hooks/use-review-timer.ts`.
O acumulador vive num `useRef<Map<documentId, Acumulador>>` na página, não no modal —
fechar o modal sem decidir não pode zerar o que já foi medido.

Engate em `front-end/app/checagem/page.tsx`:

| Ponto | Linha atual | Chamada |
|---|---|---|
| abrir a tela | `handleViewDetails` :243 | `reviewTimer.abrir(id)` |
| aprovar | `handleAprovar` :135 | `reviewTimer.encerrar(id)` → vai no corpo do PATCH |
| rejeitar | `handleRejeitar` :189 | `reviewTimer.encerrar(id)` → vai no corpo do PATCH |
| fechar sem decidir | `onOpenChange` :365 | `reviewTimer.fechar(id)` (mantém o acumulado) |
| abrir o PDF em nova aba | prop `onAbrirPdfExterno` :378 | `reviewTimer.registrarPdfExterno(id)` |

`onAprovar` é chamado **antes** de `onOpenChange(false)` no modal
(`document-details-modal-checagem.tsx:130-133`), então ler o cronômetro dentro de
`handleAprovar` é seguro — não há corrida com o `pause`.

### 5.1 Regra de ocioso

Esta é a parte que decide se o número presta. A restrição de origem: **o PDF é renderizado
num `iframe`** (`modal:357`) pelo viewer nativo do Chrome, e rolagem/clique dentro dele
**não** gera evento no documento pai. Um detector de ocioso ingênuo por `mousemove`
classificaria "lendo o prontuário" como ocioso — exatamente o trabalho que queremos medir.

Daí três regimes, cada um limitado pelo que é observável naquele estado:

| Estado | Regra | Por quê |
|---|---|---|
| Aba oculta (`visibilityState === "hidden"`) **ou** janela sem foco (`!document.hasFocus()`) | **pausa** | trocou de aba ou de aplicativo; `hasFocus()` pega o caso que `visibilitychange` não pega (alt-tab para outro app com a aba ainda "visível") |
| Aba visível e com foco, foco **dentro** do `iframe` do PDF | **conta, sem timeout de ocioso**, limitado por `TETO_SESSAO` | ali não há evento nenhum para observar; presumir ocioso truncaria leitura legítima |
| Aba visível e com foco, foco **fora** do `iframe` | conta, com `TIMEOUT_OCIOSO` sobre `pointerdown`/`keydown`/`scroll`/`wheel`/mudança de `activeElement` | no painel de comparação a atividade é observável, então o ocioso pode ser detectado |

Exceção do "Abrir em nova aba" (`modal:349`): o clique liga um flag `pdfExterno`; enquanto
ele estiver ligado, `hidden` **não** pausa, com teto de `TETO_PDF_EXTERNO`. O flag cai
quando a aba volta a ter foco. Sem essa exceção, o tempo de quem lê o PDF em aba separada
seria contado como zero.

Ao expirar o `TIMEOUT_OCIOSO`, o trecho ativo é fechado **no instante da última
atividade** — a janela ociosa é descontada, não creditada.

Constantes (valores propostos, ver seção 9):

```ts
TIMEOUT_OCIOSO     = 10 * 60_000  // sem sinal de atividade com foco fora do PDF
TETO_PDF_EXTERNO   =  5 * 60_000  // graça para leitura em aba separada
TETO_SESSAO        = 60 * 60_000  // teto duro por abertura
```

O `wall` nunca pausa: corre da abertura ao fechamento de cada sessão.

### 5.2 Tolerância a falha

Todo o cronômetro roda dentro de `try/catch`. Se `performance` não existir, se um listener
explodir ou se `encerrar()` devolver algo inconsistente, `review_timing` sai `undefined` e o
PATCH é exatamente o de hoje. Medição não pode bloquear revisão.

---

## 6. Métrica OTel

Irmã do contador que já existe, para o Grafana ter p50/p95 em tempo real sem depender do BI:

```python
# app/core/metrics.py — sem unit="s"; o "_segundos" já está no nome (ver cabeçalho do arquivo)
REVISAO_DURACAO = _meter.create_histogram(
    "prontuai_revisao_duracao_segundos",
    description="Tempo ativo de revisão humana, da abertura da tela à decisão",
)

# VIEWS
{"instrument_name": "prontuai_revisao_duracao_segundos",
 "buckets": (5, 15, 30, 60, 120, 300, 600, 1800)},
```

Gravado ao lado de `REVISAO_HUMANA` (`documents.py:686`), com os mesmos atributos
(`decisao`, `clinica_id`, `clinica_nome`) e só quando a cronometragem sobreviveu à
sanitização. `user_email` **não** entra como atributo — cardinalidade por requisição.

Isto é complemento, não fonte de BI: agregado, sem drill-down por documento.

---

## 7. Consultas de BI

Mediana e p95 por mês e clínica:

```sql
SELECT date_trunc('month', d.reviewed_at) AS mes,
       c.name                             AS clinica,
       count(*)                                                                    AS revisoes,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY d.review_active_ms) / 1000.0     AS p50_seg,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY d.review_active_ms) / 1000.0    AS p95_seg,
       avg(d.review_active_ms::numeric / nullif(d.review_wall_ms, 0))               AS razao_ativo_bruto
FROM documents d
JOIN clinics c ON c.id = d.clinic_id
WHERE d.reviewed_at IS NOT NULL
  AND d.review_active_ms IS NOT NULL
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

Cobertura da instrumentação — obrigatória em qualquer painel comparativo, senão os
primeiros meses parecem ter tempo baixíssimo por falta de dado, não por eficiência:

```sql
SELECT date_trunc('week', reviewed_at) AS semana,
       count(*)                                                     AS decisoes,
       count(review_active_ms)                                      AS com_cronometro,
       round(100.0 * count(review_active_ms) / count(*), 1)          AS cobertura_pct
FROM documents
WHERE reviewed_at IS NOT NULL
GROUP BY 1 ORDER BY 1 DESC;
```

Os três relógios juntos (fila, revisão, lead time):

```sql
SELECT d.id,
       extract(epoch FROM d.review_opened_at - d.uploaded_at) AS fila_seg,
       d.review_active_ms / 1000.0                            AS revisao_seg,
       extract(epoch FROM d.reviewed_at - d.uploaded_at)       AS lead_time_seg,
       d.review_open_count
FROM documents d
WHERE d.review_active_ms IS NOT NULL;
```

---

## 8. Casos de borda

| Caso | Comportamento |
|---|---|
| Abre, fecha sem decidir, reabre e decide (mesmo carregamento de página) | soma os dois trechos, `review_open_count = 2` |
| Abre, fecha, recarrega a página, reabre e decide | acumulador do primeiro trecho é perdido; o segundo é somado ao que já estiver na coluna |
| Abre e nunca decide (abandono) | **não medido** — sem decisão não há PATCH. Limitação conhecida, ver seção 10 |
| Documento revisado duas vezes (status muda de novo) | soma; `review_opened_at` continua sendo a primeira abertura |
| Decide sem abrir o PDF | tempo baixo e legítimo — não é erro de medição |
| Dois documentos abertos em abas diferentes | a aba sem foco pausa; cada aba manda a sua fatia, e o servidor soma |
| Retry / duplo clique no PATCH | guarda de transição bloqueia a segunda gravação |
| Decisão em lote pela lista | não existe hoje: `checagem-actions.tsx` é código morto, a decisão só sai do modal. Se voltar a existir, precisa de decisão explícita sobre o que gravar |
| Máquina bloqueada com o PDF em foco | pode inflar até `TETO_SESSAO`. Aparece como outlier; por isso o painel usa p50/p95 e a razão ativo/bruto, nunca média simples |

---

## 9. Parâmetros a decidir na avaliação

| Questão | Recomendação | Custo de errar |
|---|---|---|
| Marco inicial: abertura do modal ou primeiro clique em "Visualizar documento"? | abertura do modal | o segundo mede menos tempo e ignora quem revisa só pela comparação |
| `TIMEOUT_OCIOSO` | 10 min | mais curto trunca leitura longa; mais longo credita café como trabalho |
| Descontar retroativamente a janela ociosa? | sim | não descontar infla sistematicamente o ativo em até 10 min por sessão |
| Aba oculta com PDF em aba separada | exceção com teto de 5 min | pausar sempre é mais simples e subestima quem lê fora do modal |
| Reabertura entre carregamentos de página | somar | sobrescrever perde a primeira passada |
| BI expõe tempo por revisor nominal? | agregado por clínica/período por padrão; nominal só para ADMIN | tempo por revisor é medição de produtividade individual — decisão de gestão, não técnica |

---

## 10. Limitações conhecidas

1. **Abandono não é medido.** Abrir e sair sem decidir não gera evento. Taxa de abandono,
   reabertura e tempo até a primeira interação exigem a tabela de eventos (opção 3). Este
   desenho não a impede: as colunas seguem válidas como agregado, e a opção 3 as
   alimentaria a partir dos eventos.
2. **Valor calculado no cliente.** Auditável pelos clamps e pela razão ativo/bruto, mas não
   à prova de adulteração. Aceitável para BI interno; se algum dia o número for usado para
   avaliação individual formal, isso precisa ser reavaliado.
3. **`review_opened_at` é relógio de parede do cliente**, como o `reviewed_at` já é hoje
   (`checagem/page.tsx:146`). Skew de minutos é possível e afeta só o tempo de fila; as
   durações são monotônicas e não são afetadas.
4. **Sem histórico.** Só há dado a partir do deploy. O baseline para a meta de 50% tem que
   vir da opção 0 (gap entre decisões consecutivas do mesmo revisor no `audit_logs`).
5. **Nada disso deve ser gravado no `metadata_json` do `audit_log`.** O
   `set_audit_context()` de `documents.py:717` roda numa task filha do
   `BaseHTTPMiddleware` (`main.py:227`) e o middleware sempre lê `{}` — é a causa do
   `metadata_json` vazio que apareceu na apuração de acurácia. Coluna em `documents` passa
   longe desse problema.

---

## 11. Execução

| Frente | Itens | Estimativa |
|---|---|---|
| Back-end | `ReviewTiming`, `review_timing.py` (sanitização), PATCH, `update_document`, migração 004 + check, histograma + VIEWS | 4 h |
| Front-end | `lib/review-timer.ts`, `use-review-timer.ts`, 5 engates em `checagem/page.tsx` | 3 h |
| BI | as 3 consultas + painel de p50/p95 e cobertura | 2 h |

Total ~1,5 dia. Deploy sem coordenação: back e front são independentes (front antigo com
back novo → colunas ficam `NULL`; front novo com back antigo → campo ignorado pelo
Pydantic).

Testes:

- `back-end/tests/test_review_timing.py` — função pura, roda com
  `PYTHONPATH=back-end pytest ... --noconftest`: cada clamp, cada descarte, acumulação
  sobre valor existente.
- Guarda de transição: PATCH repetido não soma duas vezes.
- Front: a lógica fica no módulo puro, mas **não há runner de teste no front-end** (só
  eslint). Validação manual, roteiro de 6 casos: decidir direto; abrir/fechar/reabrir;
  trocar de aba no meio; abrir o PDF em aba separada; ficar 12 min com o PDF em foco;
  falhar o `encerrar()` de propósito e confirmar que o PATCH ainda passa.

---

## 12. Validação executada (28/08/2026)

| Verificação | Resultado |
|---|---|
| `tests/test_review_timing.py` — 19 casos da sanitização + 7 da guarda de decisão no handler | 26 passaram |
| Suíte back-end completa contra Postgres real | 3 falhas, 88 passaram |
| Mesma suíte no HEAD limpo, sem esta mudança (baseline) | as **mesmas** 3 falhas, 62 passaram |
| Migração 004 contra Postgres: detecção, aplicação, tipos, idempotência, reaplicação | 16 checagens passaram |
| Acumulação em `update_document`: soma, `review_opened_at` imutável, PATCH sem timing não escreve | passou |
| Cronômetro do front: 10 cenários simulados com DOM falso e relógio controlado | passaram |
| `tsc --noEmit`, `npm run lint`, `npm run build` | limpos; `/checagem` segue prerenderizado |

As 3 falhas são pré-existentes e não têm relação com esta mudança:
`test_validacao.py` chama `validacao_service.fuzzy_match` e
`comparar_listas_exames`, que não existem mais no módulo.

Cenários cobertos na simulação do cronômetro: revisão simples; troca de aba;
PDF em aba separada dentro e fora do teto de graça; ocioso de 12 min com foco
fora do PDF; leitura de 12 min dentro do iframe (o caso que a regra ingênua
truncaria); abre/fecha/reabre; aba esquecida por 65 min; `encerrar` sem
abertura; e `destruir` seguido de nova abertura (duplo mount do StrictMode).

Não coberto por automação: o comportamento real do viewer de PDF do Chrome —
a simulação assume que o foco no iframe é observável pelo documento pai, que é
o pressuposto da regra de ocioso. Vale um teste manual na tela antes do deploy.

### Correção pós-primeiro teste em staging

O primeiro deploy em staging não gravou nada, por dois motivos independentes:

1. Só o back-end subiu — `deploy_staging_vps.sh` envia `git archive "$SHA:back-end"`, e
   o cronômetro inteiro vive no front. O PATCH chegou (200, registrado em `audit_logs`)
   sem o bloco `review_timing`.
2. Investigando o item 1, apareceu a falha real da guarda de decisão descrita na seção 4:
   documento que a IA marcou `validated` e o humano confirma não muda de status, e a
   condição antiga o descartava em silêncio. Corrigido antes do segundo teste.
