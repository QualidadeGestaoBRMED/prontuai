-- Indicadores do dashboard (/v1/dashboard/indicadores).
--
-- Cópia de relatorio9.sql do repo prontuai-dados, a consulta que a análise usa
-- para gerar o painel. Mantida VERBATIM de propósito: qualquer divergência
-- entre o que a análise mede e o que a tela mostra vira discussão sobre número,
-- não sobre produto. Ao atualizar, copie o arquivo inteiro de novo.
--
-- O bloco 'revisao' (tempo de revisão, datado por reviewed_at) e 'extracao_dia'
-- vêm junto e são descartados no serviço — o dashboard ainda não os consome.
-- Vale podar aqui quando der para rodar a consulta e medir o ganho.
--
-- Painel completo: utilizacao + acuracia + exames + extracao (datados por
-- created_at) e tempo de revisao (datado por reviewed_at, sob a chave
-- 'revisao'). Merge de relatorio6.sql + relatorio7.sql.

-- result_payload e TEXT, e uma unica linha invalida fazia o cast derrubar a
-- consulta INTEIRA ("invalid input syntax for type json") -- ou seja, o painel
-- todo, para sempre, por causa de um documento. O guarda abaixo faz a linha
-- torta virar NULL e so ela se perder.
--
-- Por que CASE e nao funcao: a consulta roda em transacao READ ONLY, onde
-- CREATE FUNCTION (mesmo em pg_temp) e recusado. E o CASE garante a ordem --
-- o cast so acontece no ramo verdadeiro, enquanto condicoes soltas no WHERE o
-- planejador pode reordenar.
--
-- `LIKE '{%'` e a convencao do resto do codigo e pega NULL, vazio e texto
-- legado; `pg_input_is_valid` pega tambem JSON truncado, e exige Postgres 16+
-- (producao roda 17, staging 16).

WITH lim AS (
    SELECT min(created_at) AS ini, max(created_at) AS fim FROM documents
),
gran AS (
    SELECT * FROM (VALUES ('semanal', 'week'),
                          ('mensal', 'month'),
                          ('trimestral', 'quarter')) AS g(gran, unidade)
),
grid AS (
    SELECT 'semanal' AS gran, 'week' AS unidade, g AS p
    FROM lim, generate_series(date_trunc('week', lim.ini),
                              date_trunc('week', lim.fim), interval '1 week') g
    UNION ALL
    SELECT 'mensal', 'month', g
    FROM lim, generate_series(date_trunc('month', lim.ini),
                              date_trunc('month', lim.fim), interval '1 month') g
    UNION ALL
    SELECT 'trimestral', 'quarter', g
    FROM lim, generate_series(date_trunc('quarter', lim.ini),
                              date_trunc('quarter', lim.fim), interval '3 months') g
),
-- revisao humana: quem de fato bateu o martelo
humano AS (
    SELECT DISTINCT ON (al.resource_id)
        al.resource_id AS document_id,
        COALESCE(al.metadata_json::jsonb ->> 'after_status', d.validation_status) AS humano_status,
        al.created_at AS humano_em
    FROM audit_logs al
    JOIN documents d ON d.id = al.resource_id
    WHERE al.resource = 'documents'
      AND (al.action = 'documents.update' OR al.action LIKE 'patch:/v1/documents/%')
      AND al.user_role IN ('ADMIN', 'CHECKER', 'MANAGER')
      AND al.status_code BETWEEN 200 AND 299
      AND COALESCE(al.metadata_json::jsonb ->> 'after_status', d.validation_status)
          IN ('validated', 'rejected')
    ORDER BY al.resource_id, al.created_at DESC, al.id DESC
),
-- decisao original da IA
ia AS (
    SELECT DISTINCT ON (resource_id)
        resource_id AS document_id,
        metadata_json::jsonb ->> 'validation_status' AS ia_status,
        created_at AS ia_em
    FROM audit_logs
    WHERE action = 'documents.processed'
      AND resource = 'documents'
      AND metadata_json::jsonb ->> 'validation_status' IN ('validated', 'pending', 'rejected')
    ORDER BY resource_id, created_at DESC, id DESC
),
-- base de utilizacao
doc AS (
    SELECT
        d.id, d.clinic_id, d.validation_status, d.created_at,
        (h.document_id IS NOT NULL) AS revisado,
        CASE WHEN (p.payload #>> '{brmed_result,data_previsao_liberacao}')
                  ~ '^\d{2}/\d{2}/\d{4}$'
             THEN to_date(p.payload #>> '{brmed_result,data_previsao_liberacao}',
                          'DD/MM/YYYY')
        END AS previsao,
        COALESCE(d.reviewed_at, d.updated_at)::date AS liberado_em
    FROM documents d
    LEFT JOIN humano h ON h.document_id = d.id
    CROSS JOIN LATERAL (SELECT CASE WHEN d.result_payload LIKE '{%'
                              AND pg_input_is_valid(d.result_payload, 'jsonb')
                         THEN d.result_payload::jsonb END AS payload) p
),
agg AS (
    SELECT
        gr.gran, gr.p,
        count(d.id)                                                        AS docs,
        count(*) FILTER (WHERE d.validation_status = 'validated')          AS validados,
        count(*) FILTER (WHERE d.validation_status = 'rejected')           AS rejeitados,
        count(*) FILTER (WHERE d.id IS NOT NULL
                           AND (d.validation_status = 'pending'
                             OR d.validation_status IS NULL))              AS pendentes,
        count(*) FILTER (WHERE d.revisado)                                 AS revisados,
        count(*) FILTER (WHERE d.validation_status = 'validated'
                           AND d.previsao IS NOT NULL
                           AND d.liberado_em < d.previsao)                 AS antecipada,
        count(*) FILTER (WHERE d.validation_status = 'validated'
                           AND d.previsao IS NOT NULL
                           AND d.liberado_em = d.previsao)                 AS em_dia,
        count(*) FILTER (WHERE d.validation_status = 'validated'
                           AND d.previsao IS NOT NULL
                           AND d.liberado_em > d.previsao)                 AS atrasada
    FROM grid gr
    LEFT JOIN doc d ON date_trunc(gr.unidade, d.created_at) = gr.p
    GROUP BY gr.gran, gr.p
),
clin AS (
    SELECT
        d.clinic_id, g.gran, date_trunc(g.unidade, d.created_at) AS p,
        count(*)                                                   AS docs,
        count(*) FILTER (WHERE d.revisado)                         AS revisados,
        count(*) FILTER (WHERE d.validation_status = 'validated')  AS validados
    FROM doc d CROSS JOIN gran g
    GROUP BY 1, 2, 3
),
-- base de acuracia: IA x humano, com classificacao do "jeitinho"
julgamento AS (
    SELECT
        d.created_at,
        ia.ia_status,
        h.humano_status,
        (motivo = '') AS sem_motivo,
        CASE
            -- humano aprovou apesar do apontamento da IA, por razao externa
            WHEN h.humano_status = 'validated' AND motivo ~ (
                    'outro sistema|outro lugar|outra plataforma|outro site|por fora|caepetox'
                 || '|autorizad|combinad|acordo|cliente pediu|pediu para liberar|liberar sem'
                 || '|sem o exame|sem o pesquisa|nao foi realiz|nao realiz|nao foi feito'
                 || '|duas vezes|duplicad|homologacao'
                 || '|clinica nao inseriu|clinica nao anexou|nao inseriu a guia|nao anexou a guia'
                 || '|outro ticket|nao esta na grade|fora da grade')
                THEN true
            -- humano rejeitou por pedido do cliente ou pendencia externa
            WHEN h.humano_status = 'rejected' AND motivo ~ (
                    'cliente pediu|cliente solicitou|cliente nao enviou|aguardando|combinad'
                 || '|^teste')
                THEN true
            ELSE false
        END AS jeitinho,
        motivo
    FROM ia
    JOIN humano h ON h.document_id = ia.document_id AND h.humano_em >= ia.ia_em
    JOIN documents d ON d.id = ia.document_id
    CROSS JOIN LATERAL (
        SELECT lower(translate(
            btrim(COALESCE(CASE WHEN h.humano_status = 'validated' THEN d.approval_reason
                                ELSE d.rejection_reason END, '')),
            'ÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç', 'AAAAEEIOOOUUCaaaaeeiooouuc')) AS motivo
    ) mm
),
-- Por que a divergencia aconteceu. So classifica o que conta contra a acuracia.
motivado AS (
    SELECT
        j.*,
        CASE
            WHEN j.jeitinho THEN 'jeitinho'
            WHEN j.ia_status = 'rejected' THEN 'falha_tecnica'
            -- IA aprovou e o revisor derrubou
            WHEN j.ia_status = 'validated' AND j.humano_status = 'rejected' THEN
                CASE
                    WHEN j.motivo = '' THEN 'sem_justificativa'
                    WHEN j.motivo ~ ('cortad|ilegiv|carimbo|assinatura|assinal|aptid|marcac'
                                  || '|invertid|ano errado|duas (pagina|via)|reaproveitament'
                                  || '|antigo|outro colaborador|sexo|observacao|incorret|data ')
                        THEN 'regra_formal'
                    WHEN j.motivo ~ ('falta|faltand|faltou|nao consta|ausente|nao anexad'
                                  || '|somente|apenas|nao enviou')
                        THEN 'exame_nao_detectado'
                    ELSE 'outro'
                END
            -- IA apontou falta e o revisor liberou
            WHEN j.ia_status = 'pending' AND j.humano_status = 'validated' THEN
                CASE
                    WHEN j.motivo = '' THEN 'sem_justificativa'
                    WHEN j.motivo ~ ('nao (reconheceu|identificou|leu|le |encontrou|lê)|nomenclatura'
                                  || '|consta|esta no|estao no|no pdf|no anexo|em anexo|anexado'
                                  || '|inclus|incluid|prontuario (completo|esta)|tudo ok|tudo cert'
                                  || '|todos os exames|todos exames|^ok|completo')
                        THEN 'matching_ia'
                    ELSE 'outro'
                END
            ELSE 'ok'
        END AS categoria
    FROM julgamento j
),
acc AS (
    SELECT
        gr.gran, gr.p,
        -- julgamento documental (aprovar x apontar exame faltante)
        count(*) FILTER (WHERE j.ia_status = 'validated' AND j.humano_status = 'validated') AS ok_aprovou,
        count(*) FILTER (WHERE j.ia_status = 'pending'   AND j.humano_status = 'rejected')  AS ok_rejeitou,
        count(*) FILTER (WHERE j.ia_status = 'validated' AND j.humano_status = 'rejected')  AS div_aprovou,
        count(*) FILTER (WHERE j.ia_status = 'validated' AND j.humano_status = 'rejected'
                           AND j.jeitinho)                                                  AS div_aprovou_jeitinho,
        count(*) FILTER (WHERE j.ia_status = 'pending'   AND j.humano_status = 'validated') AS div_rejeitou,
        count(*) FILTER (WHERE j.ia_status = 'pending'   AND j.humano_status = 'validated'
                           AND j.jeitinho)                                                  AS div_rejeitou_jeitinho,
        -- falhas tecnicas (fora do julgamento)
        count(*) FILTER (WHERE j.ia_status = 'rejected' AND j.humano_status = 'rejected')   AS falha_rejeitou,
        count(*) FILTER (WHERE j.ia_status = 'rejected' AND j.humano_status = 'validated')  AS falha_aprovou,
        count(*) FILTER (WHERE j.ia_status = 'rejected' AND j.humano_status = 'validated'
                           AND (j.jeitinho OR j.sem_motivo))                                AS falha_aprovou_ok,

        -- por que a acuracia nao esta maior
        count(*) FILTER (WHERE j.categoria = 'exame_nao_detectado') AS mot_exame_nao_detectado,
        count(*) FILTER (WHERE j.categoria = 'regra_formal')        AS mot_regra_formal,
        count(*) FILTER (WHERE j.categoria = 'matching_ia')         AS mot_matching_ia,
        count(*) FILTER (WHERE j.categoria = 'sem_justificativa')   AS mot_sem_justificativa,
        count(*) FILTER (WHERE j.categoria = 'outro')               AS mot_outro,

        -- decisoes humanas sem justificativa registrada
        count(*) FILTER (WHERE j.sem_motivo)                                   AS sem_just_total,
        count(*) FILTER (WHERE j.sem_motivo AND j.humano_status = 'rejected')  AS sem_just_rejeicao,
        count(*) FILTER (WHERE j.sem_motivo AND j.humano_status = 'validated') AS sem_just_aprovacao,
        count(*) FILTER (WHERE j.sem_motivo
                           AND ((j.ia_status = 'validated' AND j.humano_status = 'rejected')
                             OR (j.ia_status = 'pending'   AND j.humano_status = 'validated')
                             OR (j.ia_status = 'rejected'  AND j.humano_status = 'validated')))
                                                                               AS sem_just_divergencia,
        count(j.ia_status)                                                     AS julgados
    FROM grid gr
    LEFT JOIN motivado j ON date_trunc(gr.unidade, j.created_at) = gr.p
    GROUP BY gr.gran, gr.p
),
-- ONDE ATUAR: detalhe por exame, mes a mes
-- alarme -> IA marcou o exame como faltante e o revisor liberou assim mesmo
-- escape -> IA deu o exame como presente e o revisor apontou a falta
revertidos AS (
    SELECT d.id, d.created_at, ia.ia_status, h.humano_status,
           p.payload -> 'tabela_comparacao' AS tabela,
           lower(translate(btrim(COALESCE(
               CASE WHEN h.humano_status = 'validated' THEN d.approval_reason
                    ELSE d.rejection_reason END, '')),
               'ÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç', 'AAAAEEIOOOUUCaaaaeeiooouuc')) AS motivo
    FROM ia
    JOIN humano h ON h.document_id = ia.document_id AND h.humano_em >= ia.ia_em
    JOIN documents d ON d.id = ia.document_id
    CROSS JOIN LATERAL (SELECT CASE WHEN d.result_payload LIKE '{%'
                              AND pg_input_is_valid(d.result_payload, 'jsonb')
                         THEN d.result_payload::jsonb END AS payload) p
    WHERE jsonb_typeof(p.payload -> 'tabela_comparacao') = 'array'
      AND ((ia.ia_status = 'pending' AND h.humano_status = 'validated')
        OR (ia.ia_status = 'validated' AND h.humano_status = 'rejected'))
),
falhas_exame AS (
    -- alarme falso: a IA apontou falta e o documento foi liberado
    SELECT g.gran, date_trunc(g.unidade, r.created_at) AS p,
           upper(btrim(e ->> 'exame')) AS exame,
           CASE WHEN r.motivo ~ ('outro sistema|outro lugar|outra plataforma|outro site|por fora'
                              || '|caepetox|autorizad|combinad|cliente pediu|liberar sem'
                              || '|nao foi realiz|nao realiz')
                THEN 'externo' ELSE 'alarme' END AS tipo
    FROM revertidos r
    CROSS JOIN gran g
    CROSS JOIN LATERAL jsonb_array_elements(r.tabela) e
    WHERE r.ia_status = 'pending' AND r.humano_status = 'validated'
      AND e ->> 'status' = 'faltante'
    UNION ALL
    -- escape: a IA deu como presente e o revisor citou o exame ao rejeitar
    SELECT g.gran, date_trunc(g.unidade, r.created_at) AS p,
           upper(btrim(e ->> 'exame')) AS exame,
           'escape' AS tipo
    FROM revertidos r
    CROSS JOIN gran g
    CROSS JOIN LATERAL jsonb_array_elements(r.tabela) e
    CROSS JOIN LATERAL (
        SELECT w FROM unnest(string_to_array(
            lower(translate(e ->> 'exame',
                'ÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç', 'AAAAEEIOOOUUCaaaaeeiooouuc')), ' ')) w
        WHERE length(w) >= 5 ORDER BY length(w) DESC LIMIT 1
    ) k
    WHERE r.ia_status = 'validated' AND r.humano_status = 'rejected'
      AND e ->> 'status' = 'encontrado'
      AND r.motivo LIKE '%' || k.w || '%'
),
exame_periodo AS (
    SELECT gran, exame, p,
           count(*) FILTER (WHERE tipo = 'alarme')  AS alarme,
           count(*) FILTER (WHERE tipo = 'externo') AS externo,
           count(*) FILTER (WHERE tipo = 'escape')  AS escape
    FROM falhas_exame GROUP BY gran, exame, p
),
-- EFEITO DE CORRECOES NA EXTRACAO DE IDENTIFICADOR
-- Medido no momento do PROCESSAMENTO (veredito da propria IA), nao da revisao.
-- regra_negocio (expedicao em aberto) e grupo de controle.
extracao AS (
    SELECT
        ia.ia_em::date AS dia,
        CASE
            WHEN ia.ia_status <> 'rejected' THEN 'ok'
            WHEN d.rejection_reason ~* 'cnpj' THEN 'extracao_cnpj'
            WHEN d.rejection_reason ~* 'cpf|passaporte' THEN 'extracao_cpf'
            WHEN d.rejection_reason ~* 'paciente n[ãa]o encontrado'
                THEN 'paciente_nao_encontrado'
            WHEN d.rejection_reason ~* 'expedi[çc][ãa]o em aberto'
                THEN 'regra_negocio'
            ELSE 'outro'
        END AS causa
    FROM ia
    JOIN documents d ON d.id = ia.document_id
)
,
-- TEMPO DE REVISAO (docs/tempo-de-revisao-desenho.md)
-- Datado por reviewed_at (decisao), nao por created_at (upload): o trabalho
-- aconteceu no dia da decisao. As chaves tem o MESMO FORMATO das outras
-- series, mas agrupam coortes diferentes -- por isso tudo vive sob 'revisao',
-- e nao misturado em 'series'. Nao some as duas por chave.
lim_rev AS (
    SELECT min(reviewed_at) AS ini, max(reviewed_at) AS fim
    FROM documents WHERE reviewed_at IS NOT NULL
),
grid_rev AS (
    SELECT 'semanal' AS gran, 'week' AS unidade, g AS p
    FROM lim_rev, generate_series(date_trunc('week', lim_rev.ini),
                                  date_trunc('week', lim_rev.fim), interval '1 week') g
    UNION ALL
    SELECT 'mensal', 'month', g
    FROM lim_rev, generate_series(date_trunc('month', lim_rev.ini),
                                  date_trunc('month', lim_rev.fim), interval '1 month') g
    UNION ALL
    SELECT 'trimestral', 'quarter', g
    FROM lim_rev, generate_series(date_trunc('quarter', lim_rev.ini),
                                  date_trunc('quarter', lim_rev.fim), interval '3 months') g
),
-- toda decisao humana registrada, com ou sem cronometro.
-- review_active_ms NULL = revisao sem instrumentacao, NAO zero (secao 3).
rev AS (
    SELECT
        d.id, d.clinic_id, d.validation_status, d.reviewed_at,
        d.review_active_ms, d.review_wall_ms, d.review_open_count,
        (d.review_active_ms IS NOT NULL) AS cronometrado,
        d.review_active_ms / 1000.0 AS ativo_seg,
        d.review_wall_ms   / 1000.0 AS bruto_seg,
        CASE WHEN d.review_wall_ms > 0
             THEN d.review_active_ms::numeric / d.review_wall_ms END AS razao,
        extract(epoch FROM d.review_opened_at - d.uploaded_at) AS fila_seg,
        extract(epoch FROM d.reviewed_at     - d.uploaded_at)  AS lead_seg
    FROM documents d
    WHERE d.reviewed_at IS NOT NULL
),
tempo AS (
    SELECT
        gr.gran, gr.p,
        count(r.id)                             AS decisoes,
        count(r.review_active_ms)               AS com_cronometro,
        count(r.id) - count(r.review_active_ms) AS sem_cronometro,
        CASE WHEN count(r.id) > 0
             THEN round(100.0 * count(r.review_active_ms) / count(r.id), 1)
        END                                     AS cobertura_pct,
        round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1) AS p50_ativo_seg,
        round(percentile_cont(0.95) WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1) AS p95_ativo_seg,
        round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY r.bruto_seg)::numeric, 1) AS p50_bruto_seg,
        round(percentile_cont(0.95) WITHIN GROUP (ORDER BY r.bruto_seg)::numeric, 1) AS p95_bruto_seg,
        -- vigia a regra de ocioso: se despencar, esta cortando trabalho real
        round(avg(r.razao), 3)                                   AS razao_ativo_bruto,
        round((sum(r.review_active_ms) / 3600000.0)::numeric, 2)  AS ativo_total_horas,
        -- os tres relogios na MESMA coorte cronometrada (secao 7 do desenho)
        round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r.fila_seg)::numeric, 1) AS p50_fila_seg,
        round((percentile_cont(0.5) WITHIN GROUP (ORDER BY r.lead_seg)
               FILTER (WHERE r.cronometrado))::numeric, 1)        AS p50_lead_seg,
        -- populacao inteira, para o historico (NAO comparavel com o ativo)
        round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r.lead_seg)::numeric, 1) AS p50_lead_todos_seg,
        round(avg(r.review_open_count), 2)                        AS aberturas_media,
        count(*) FILTER (WHERE r.review_open_count > 1)           AS reabertos
    FROM grid_rev gr
    LEFT JOIN rev r ON date_trunc(gr.unidade, r.reviewed_at) = gr.p
    GROUP BY gr.gran, gr.p
),
-- rejeitar exige escrever justificativa; aprovar nao
decisao AS (
    SELECT
        gr.gran, gr.p, r.validation_status AS decisao,
        count(*) AS n,
        round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1) AS p50_ativo_seg,
        round(percentile_cont(0.95) WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1) AS p95_ativo_seg
    FROM grid_rev gr
    JOIN rev r ON date_trunc(gr.unidade, r.reviewed_at) = gr.p
    WHERE r.cronometrado
    GROUP BY gr.gran, gr.p, r.validation_status
),
-- faixas iguais aos buckets do histograma OTel (secao 6 do desenho)
faixa AS (
    SELECT
        gr.gran, gr.p,
        count(*) FILTER (WHERE r.ativo_seg <    5)                        AS ate_5s,
        count(*) FILTER (WHERE r.ativo_seg >=   5 AND r.ativo_seg <   15) AS s5_15,
        count(*) FILTER (WHERE r.ativo_seg >=  15 AND r.ativo_seg <   30) AS s15_30,
        count(*) FILTER (WHERE r.ativo_seg >=  30 AND r.ativo_seg <   60) AS s30_60,
        count(*) FILTER (WHERE r.ativo_seg >=  60 AND r.ativo_seg <  120) AS s60_120,
        count(*) FILTER (WHERE r.ativo_seg >= 120 AND r.ativo_seg <  300) AS s120_300,
        count(*) FILTER (WHERE r.ativo_seg >= 300 AND r.ativo_seg <  600) AS s300_600,
        count(*) FILTER (WHERE r.ativo_seg >= 600 AND r.ativo_seg < 1800) AS s600_1800,
        count(*) FILTER (WHERE r.ativo_seg >= 1800)                       AS acima_30min
    FROM grid_rev gr
    JOIN rev r ON date_trunc(gr.unidade, r.reviewed_at) = gr.p
    WHERE r.cronometrado
    GROUP BY gr.gran, gr.p
),
clin_rev AS (
    SELECT
        r.clinic_id, g.gran, date_trunc(g.unidade, r.reviewed_at) AS p,
        count(*)                  AS decisoes,
        count(r.review_active_ms) AS com_cronometro,
        round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1) AS p50_ativo_seg,
        round(percentile_cont(0.95) WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1) AS p95_ativo_seg,
        round(avg(r.razao), 3)    AS razao_ativo_bruto
    FROM rev r CROSS JOIN gran g
    GROUP BY 1, 2, 3
)
SELECT jsonb_pretty(jsonb_build_object(

  'periodo', jsonb_build_object(
      'doc_mais_antigo',  (SELECT ini::date FROM lim),
      'doc_mais_recente', (SELECT fim::date FROM lim)),

  'totais', (SELECT jsonb_build_object(
        'enviados',   count(*),
        'revisados',  count(*) FILTER (WHERE revisado),
        'validados',  count(*) FILTER (WHERE validation_status = 'validated'),
        'rejeitados', count(*) FILTER (WHERE validation_status = 'rejected'),
        'pendentes',  count(*) FILTER (WHERE validation_status = 'pending'
                                          OR validation_status IS NULL)) FROM doc),

  -- serie de utilizacao
  'series', (SELECT jsonb_object_agg(gran, pts) FROM (
        SELECT gran, jsonb_agg(jsonb_build_object(
                   'chave',      to_char(p, 'YYYY-MM-DD'),
                   'docs',       docs,
                   'validados',  validados,
                   'rejeitados', rejeitados,
                   'pendentes',  pendentes,
                   'revisados',  revisados,
                   'antecipada', antecipada,
                   'em_dia',     em_dia,
                   'atrasada',   atrasada) ORDER BY p) AS pts
        FROM agg GROUP BY gran) s),

  -- serie de acuracia, nas mesmas chaves da serie de utilizacao
  'acuracia', (SELECT jsonb_object_agg(gran, pts) FROM (
        SELECT gran, jsonb_agg(jsonb_build_object(
                   'chave',                 to_char(p, 'YYYY-MM-DD'),
                   'ok_aprovou',            ok_aprovou,
                   'ok_rejeitou',           ok_rejeitou,
                   'div_aprovou',           div_aprovou,
                   'div_aprovou_jeitinho',  div_aprovou_jeitinho,
                   'div_rejeitou',          div_rejeitou,
                   'div_rejeitou_jeitinho', div_rejeitou_jeitinho,
                   'falha_rejeitou',        falha_rejeitou,
                   'falha_aprovou',         falha_aprovou,
                   'falha_aprovou_ok',      falha_aprovou_ok,
                   'mot_exame_nao_detectado', mot_exame_nao_detectado,
                   'mot_regra_formal',      mot_regra_formal,
                   'mot_matching_ia',       mot_matching_ia,
                   'mot_sem_justificativa', mot_sem_justificativa,
                   'mot_outro',             mot_outro,
                   'sem_just_total',        sem_just_total,
                   'sem_just_rejeicao',     sem_just_rejeicao,
                   'sem_just_aprovacao',    sem_just_aprovacao,
                   'sem_just_divergencia',  sem_just_divergencia,
                   'julgados',              julgados) ORDER BY p) AS pts
        FROM acc GROUP BY gran) s),

  -- onde atuar, por exame
  'exames', (SELECT jsonb_agg(x ORDER BY (x ->> 'total')::int DESC) FROM (
        SELECT jsonb_build_object(
            'exame',   m.exame,
            'total',   sum(m.alarme + m.externo + m.escape),
            'alarme',  sum(m.alarme),
            'externo', sum(m.externo),
            'escape',  sum(m.escape),
            'acao',    CASE
                         WHEN sum(m.externo) >= sum(m.alarme)
                          AND sum(m.externo) >= sum(m.escape)
                             THEN 'marcar na grade como exame externo'
                         WHEN sum(m.escape) > sum(m.alarme)
                             THEN 'reforçar a detecção'
                         ELSE 'dicionário de sinônimos'
                       END,
            -- historico mensal (usado no grafico de evolucao)
            'por_mes', jsonb_object_agg(to_char(m.p, 'YYYY-MM'),
                           jsonb_build_object('alarme',  m.alarme,
                                              'externo', m.externo,
                                              'escape',  m.escape)),
            -- mesmas chaves das demais series, para o filtro de periodo
            'series',  (SELECT jsonb_object_agg(gran, pts) FROM (
                   SELECT ep.gran, jsonb_object_agg(
                              to_char(ep.p, 'YYYY-MM-DD'),
                              jsonb_build_object('alarme',  ep.alarme,
                                                 'externo', ep.externo,
                                                 'escape',  ep.escape)) AS pts
                   FROM exame_periodo ep
                   WHERE ep.exame = m.exame
                   GROUP BY ep.gran) se)) AS x
        FROM exame_periodo m
        WHERE m.gran = 'mensal'
        GROUP BY m.exame
        HAVING sum(m.alarme + m.externo + m.escape) >= 2) t),

  -- efeito de correcoes de extracao, dia a dia (ultimos 60 dias)
  'extracao_dia', (SELECT jsonb_agg(x ORDER BY x ->> 'dia') FROM (
        SELECT jsonb_build_object(
            'dia',            to_char(dia, 'YYYY-MM-DD'),
            'processados',    count(*),
            'falha_extracao', count(*) FILTER (WHERE causa IN ('extracao_cnpj',
                                                               'extracao_cpf',
                                                               'paciente_nao_encontrado')),
            'cnpj',           count(*) FILTER (WHERE causa = 'extracao_cnpj'),
            'cpf',            count(*) FILTER (WHERE causa = 'extracao_cpf'),
            'nao_encontrado', count(*) FILTER (WHERE causa = 'paciente_nao_encontrado'),
            'regra_negocio',  count(*) FILTER (WHERE causa = 'regra_negocio'),
            'outro',          count(*) FILTER (WHERE causa = 'outro')) AS x
        FROM extracao
        WHERE dia >= (SELECT max(dia) FROM extracao) - 60
        GROUP BY dia) t),

  -- ── TEMPO DE REVISAO ────────────────────────────────────────────────────
  -- Bloco proprio porque e datado por reviewed_at, nao por created_at.
  'revisao', jsonb_build_object(

      'periodo', jsonb_build_object(
          'primeira_decisao', (SELECT ini::date FROM lim_rev),
          'ultima_decisao',   (SELECT fim::date FROM lim_rev),
          'datado_por',       'reviewed_at (decisao), nao created_at (upload)'),

      'totais', (SELECT jsonb_build_object(
            'decisoes',          count(*),
            'com_cronometro',    count(review_active_ms),
            'sem_cronometro',    count(*) - count(review_active_ms),
            'cobertura_pct',     CASE WHEN count(*) > 0
                                      THEN round(100.0 * count(review_active_ms) / count(*), 1) END,
            'p50_ativo_seg',     round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY ativo_seg)::numeric, 1),
            'p95_ativo_seg',     round(percentile_cont(0.95) WITHIN GROUP (ORDER BY ativo_seg)::numeric, 1),
            'p50_bruto_seg',     round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY bruto_seg)::numeric, 1),
            'p95_bruto_seg',     round(percentile_cont(0.95) WITHIN GROUP (ORDER BY bruto_seg)::numeric, 1),
            'razao_ativo_bruto', round(avg(razao), 3),
            'ativo_total_horas', round((sum(review_active_ms) / 3600000.0)::numeric, 2),
            'aberturas_media',   round(avg(review_open_count), 2),
            'reabertos',         count(*) FILTER (WHERE review_open_count > 1)) FROM rev),

      -- obrigatoria em qualquer painel comparativo (secao 7 do desenho)
      'cobertura', (SELECT jsonb_object_agg(gran, pts) FROM (
            SELECT gran, jsonb_agg(jsonb_build_object(
                       'chave',          to_char(p, 'YYYY-MM-DD'),
                       'decisoes',       decisoes,
                       'com_cronometro', com_cronometro,
                       'sem_cronometro', sem_cronometro,
                       'cobertura_pct',  cobertura_pct) ORDER BY p) AS pts
            FROM tempo GROUP BY gran) s),

      'tempos', (SELECT jsonb_object_agg(gran, pts) FROM (
            SELECT gran, jsonb_agg(jsonb_build_object(
                       'chave',              to_char(p, 'YYYY-MM-DD'),
                       'com_cronometro',     com_cronometro,
                       'p50_ativo_seg',      p50_ativo_seg,
                       'p95_ativo_seg',      p95_ativo_seg,
                       'p50_bruto_seg',      p50_bruto_seg,
                       'p95_bruto_seg',      p95_bruto_seg,
                       'razao_ativo_bruto',  razao_ativo_bruto,
                       'ativo_total_horas',  ativo_total_horas,
                       'p50_fila_seg',       p50_fila_seg,
                       'p50_lead_seg',       p50_lead_seg,
                       'p50_lead_todos_seg', p50_lead_todos_seg,
                       'aberturas_media',    aberturas_media,
                       'reabertos',          reabertos) ORDER BY p) AS pts
            FROM tempo GROUP BY gran) s),

      'por_decisao', (SELECT jsonb_object_agg(gran, pts) FROM (
            SELECT gran, jsonb_agg(jsonb_build_object(
                       'chave',         to_char(p, 'YYYY-MM-DD'),
                       'decisao',       decisao,
                       'n',             n,
                       'p50_ativo_seg', p50_ativo_seg,
                       'p95_ativo_seg', p95_ativo_seg) ORDER BY p, decisao) AS pts
            FROM decisao GROUP BY gran) s),

      'distribuicao', (SELECT jsonb_object_agg(gran, pts) FROM (
            SELECT gran, jsonb_agg(jsonb_build_object(
                       'chave',       to_char(p, 'YYYY-MM-DD'),
                       'ate_5s',      ate_5s,
                       's5_15',       s5_15,
                       's15_30',      s15_30,
                       's30_60',      s30_60,
                       's60_120',     s60_120,
                       's120_300',    s120_300,
                       's300_600',    s300_600,
                       's600_1800',   s600_1800,
                       'acima_30min', acima_30min) ORDER BY p) AS pts
            FROM faixa GROUP BY gran) s),

      'clinicas', (SELECT jsonb_agg(x ORDER BY (x ->> 'com_cronometro')::int DESC,
                                              (x ->> 'decisoes')::int DESC) FROM (
            SELECT jsonb_build_object(
                'nome',           c.name,
                'decisoes',       count(r.id),
                'com_cronometro', count(r.review_active_ms),
                'p50_ativo_seg',  round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1),
                'p95_ativo_seg',  round(percentile_cont(0.95) WITHIN GROUP (ORDER BY r.ativo_seg)::numeric, 1),
                'series',         (SELECT jsonb_object_agg(gran, pts) FROM (
                       SELECT cl.gran, jsonb_object_agg(
                                  to_char(cl.p, 'YYYY-MM-DD'),
                                  jsonb_build_object('decisoes',          cl.decisoes,
                                                     'com_cronometro',    cl.com_cronometro,
                                                     'p50_ativo_seg',     cl.p50_ativo_seg,
                                                     'p95_ativo_seg',     cl.p95_ativo_seg,
                                                     'razao_ativo_bruto', cl.razao_ativo_bruto)) AS pts
                       FROM clin_rev cl WHERE cl.clinic_id = c.id
                       GROUP BY cl.gran) sc)) AS x
            FROM clinics c
            JOIN rev r ON r.clinic_id = c.id
            WHERE c.name NOT IN ('teste', 'testando', 'Clinica Default')
            GROUP BY c.id, c.name
            ORDER BY count(r.review_active_ms) DESC, count(r.id) DESC
            LIMIT 10) t)),

  -- Todas as clinicas com documento, sem corte. O corte por volume TOTAL
  -- escondia clinica que so aparece no periodo filtrado no dashboard (uma
  -- semana, um mes) e ainda fazia o "ver todas as N clinicas" da tela mentir.
  'clinicas', (SELECT jsonb_agg(x ORDER BY (x ->> 'docs')::int DESC) FROM (
        SELECT jsonb_build_object(
            'nome',      c.name,
            'usuarios',  (SELECT count(*) FROM users u WHERE u.clinic_id = c.id),
            'docs',      count(doc.id),
            'series',    (SELECT jsonb_object_agg(gran, pts) FROM (
                   SELECT cl.gran, jsonb_object_agg(
                              to_char(cl.p, 'YYYY-MM-DD'),
                              jsonb_build_object('docs', cl.docs,
                                                 'revisados', cl.revisados,
                                                 'validados', cl.validados)) AS pts
                   FROM clin cl WHERE cl.clinic_id = c.id
                   GROUP BY cl.gran) sc)) AS x
        FROM clinics c
        JOIN doc ON doc.clinic_id = c.id
        WHERE c.name NOT IN ('teste', 'testando', 'Clinica Default')
        GROUP BY c.id, c.name) t)
));
