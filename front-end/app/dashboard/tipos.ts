/**
 * Contrato dos dados do dashboard de indicadores.
 *
 * É o que `GET /v1/dashboard/indicadores` devolve — a consulta roda no banco do
 * ambiente em que o back-end está (dev, staging ou produção). A exceção são os
 * campos `expedicoes_*` e `clinicas_sem_prontuai`, que vêm da API do BRNET.
 */

/** Granularidade da série. A chave de cada ponto é a data de início (ISO). */
export type SerieKey = "semanal" | "mensal" | "trimestral";

/** Um ponto da série geral de documentos. `chave` = primeiro dia do período. */
export interface PontoSerie {
  chave: string;
  docs: number;
  pendentes: number;
  revisados: number;
  validados: number;
  rejeitados: number;
  /**
   * Prazo pela previsão gravada no processamento, misturando clínica e técnico.
   * O painel não usa mais: ver `prazo_clinica_dia` e `prazo_tecnico_dia`.
   */
  antecipada: number;
  em_dia: number;
  atrasada: number;
}

/**
 * Um ponto da série de acurácia. `ok_*` são concordâncias, `div_*` divergências
 * e `div_*_jeitinho` as divergências resolvidas por motivo externo (contam como
 * acerto). `falha_*` são erros de leitura — ficam fora da conta de acurácia.
 * Os campos `mot_*` só existem se a extração trouxe a classificação de motivos.
 */
export interface PontoAcuracia {
  chave: string;
  julgados: number;
  ok_aprovou: number;
  ok_rejeitou: number;
  div_aprovou: number;
  div_rejeitou: number;
  div_aprovou_jeitinho: number;
  div_rejeitou_jeitinho: number;
  falha_aprovou: number;
  falha_rejeitou: number;
  falha_aprovou_ok?: number;
  sem_just_total?: number;
  sem_just_aprovacao?: number;
  sem_just_rejeicao?: number;
  sem_just_divergencia: number;
  mot_exame_nao_detectado?: number;
  mot_matching_ia?: number;
  mot_regra_formal?: number;
  mot_sem_justificativa?: number;
  mot_outro?: number;
}

export interface PontoClinica {
  docs: number;
  revisados: number;
  validados: number;
}

export interface ClinicaDados {
  nome: string;
  usuarios: number;
  docs: number;
  /** Mesmas chaves da série geral, para o recorte por período casar exato. */
  series: Partial<Record<SerieKey, Record<string, PontoClinica>>>;
}

/** Pedidos previstos para um mesmo dia. */
export interface PrevisaoDia {
  /** ISO. */
  data: string;
  pedidos: number;
}

/**
 * Credenciado com pedidos de previsão de liberação a partir de hoje. O mesmo
 * formato serve aos dois lados do corte — `clinicas_com_prontuai` e
 * `clinicas_sem_prontuai` —, que são complementares: todo pedido previsto está
 * em exatamente um deles.
 *
 * São sempre pedidos **ainda não liberados**. Previsto e realizado nunca se
 * somam: realizado vive em `expedicoes_prontuai_dia`, que é outra grandeza.
 */
export interface CredenciadoPrevisto {
  /** Rótulo do BRNET, "CIDADE - UF - NOME". */
  credenciado: string;
  nome: string;
  cidade: string | null;
  uf: string | null;
  /**
   * Nome do cadastro no ProntuAI que mais documentos ligou a este credenciado —
   * a chave que casa com a tabela "Adoção por clínica". null quando o
   * credenciado nunca enviou documento, que é a regra do lado sem ProntuAI.
   */
  clinica: string | null;
  /** Pedidos ainda não liberados com previsão a partir de hoje. */
  pedidos_previstos: number;
  /** Os mesmos pedidos, quebrados por data e em ordem crescente. */
  previsoes: PrevisaoDia[];
  /** Pendentes cuja previsão já passou — não têm data futura, só contagem. */
  vencidos: number;
  /** Documentos processados pelo ProntuAI em todo o histórico. */
  documentos: number;
  /**
   * Realizados da clínica por dia de LIBERAÇÃO — o denominador da adesão.
   * Realizado é pedido efetivamente expedido; atendido e ainda não liberado
   * conta como previsto, não como realizado.
   * Mesma datação de `expedicoes_dia`, para a adesão por clínica ser o recorte
   * por clínica do KPI "Expedições via ProntuAI" e os dois números fecharem.
   * Só existe no lado habilitado; quem não tem cadastro não tem adesão a medir.
   */
  realizados_dia?: Record<string, number>;
  /** Dos mesmos realizados, os que tiveram documento liberado no ProntuAI. */
  realizados_prontuai_dia?: Record<string, number>;
}

export interface DadosDashboard {
  periodo: { doc_mais_antigo: string; doc_mais_recente: string };
  totais: {
    enviados: number;
    pendentes: number;
    revisados: number;
    validados: number;
    rejeitados: number;
  };
  series: Record<SerieKey, PontoSerie[]>;
  acuracia: Record<SerieKey, PontoAcuracia[]>;
  clinicas: ClinicaDados[];
  /**
   * Pedidos liberados em clínicas credenciadas, por dia de liberação —
   * denominador de "Expedições via ProntuAI". Vem da API de monitoramento de
   * credenciados do BRNET (ver `dashboard_service._cruzar_expedicoes`). Vazio
   * quando algum mês não pôde ser buscado — aí o KPI mostra o total absoluto em
   * vez de uma cobertura inventada.
   */
  expedicoes_dia: Record<string, number>;
  /**
   * Numerador: dos mesmos pedidos, os que tiveram documento **processado** pelo
   * ProntuAI, ligados pelo `pedido_exame_id`. Processado, não liberado: um
   * prontuário rejeitado ou pendente passou pela plataforma do mesmo jeito, e
   * medir só o liberado confundiria adoção com desfecho da revisão. Conta
   * pedido, não documento — reenvio não infla a cobertura.
   */
  expedicoes_prontuai_dia: Record<string, number>;
  /**
   * Primeiro dia (ISO) em que a ligação por pedido existe. Antes dele não há
   * como medir cobertura, e o painel não mostra.
   */
  expedicoes_desde: string | null;
  /**
   * Credenciados **sem cadastro habilitado** — a tabela de prioridade de
   * inclusão. null quando o BRNET não pôde ser consultado.
   */
  clinicas_sem_prontuai: CredenciadoPrevisto[] | null;
  /**
   * Clínicas com **cadastro habilitado** (`clinics.is_active`), agregadas pelo
   * cadastro — dois credenciados do BRNET que apontam para a mesma clínica são
   * uma linha só. Complementar da lista acima; null junto com ela. Entra aqui
   * também o cadastro que nunca mandou documento: a adesão dele é baixa, não
   * inexistente, e é justamente o que a tabela revela.
   */
  clinicas_com_prontuai: CredenciadoPrevisto[] | null;
  /**
   * Previstos por UF e por dia, de cada lado do corte — a abertura por UF da
   * comparação dentro × fora. Vem à parte das listas por clínica porque a UF é
   * do CREDENCIADO: um cadastro pode receber de praças em UFs diferentes, e
   * usar a UF do cadastro jogaria os pedidos de uma na conta da outra.
   * `"—"` é o balde de credenciado sem UF no rótulo. null junto com as listas.
   */
  previstos_uf_dia: { dentro: Record<string, Record<string, number>>;
                      fora: Record<string, Record<string, number>> } | null;
  /** Quando a consulta rodou (ISO com fuso) — origem do "hoje" dos rótulos. */
  gerado_em?: string;
  /**
   * Envio do prontuário pela clínica comparado ao prazo do credenciado no BRNET,
   * por dia de envio. Um documento por entrega (reenvio conta de novo).
   */
  prazo_clinica_dia: Record<string, Prazos>;
  /**
   * Aprovação pelo técnico de credenciados comparada ao prazo da BR MED (um dia
   * útil depois do da clínica), por dia de aprovação. Só aprovações humanas — a
   * automática da IA fica de fora.
   */
  prazo_tecnico_dia: Record<string, Prazos>;
}

/** [antecipado, no dia, atrasado]. */
export type Prazos = [number, number, number];
