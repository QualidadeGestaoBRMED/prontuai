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
  /**
   * Falha técnica aprovada com motivo externo de dado de fora (CNPJ de outra
   * empresa, atendimento ainda fora do BRNET): não é falha da IA.
   */
  falha_externa?: number;
  /** Divergências resolvidas por motivo externo, por código do parecer. */
  ext_exame_por_fora?: number;
  ext_guia_nao_anexada?: number;
  ext_cnpj_divergente?: number;
  ext_atendimento_nao_registrado?: number;
  ext_outro_ticket?: number;
  ext_cliente_autorizou?: number;
  ext_outro?: number;
  /** Histórico anterior ao modal, achado por palavra-chave na justificativa. */
  ext_sem_codigo?: number;
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
   * a chave que casa as duas pontas do cruzamento. null quando o credenciado
   * nunca enviou documento, que é a regra do lado sem ProntuAI.
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
   * Reconciliação previsto × expedido, por semana de PREVISÃO (chave = segunda
   * da semana ISO): `[via_prontuai, liberado_fora, nao_liberado]`.
   *
   * Os três são exclusivos e somam os previstos daquela semana — é o que faz a
   * barra empilhada fechar em 100% sem fatia de resto. Datado pelo dia da
   * promessa, não pelo da liberação: pedido previsto para sexta e liberado na
   * segunda conta na semana em que foi prometido.
   *
   * Decompõe o buraco entre previsto e expedido em dois donos: "liberou por
   * fora" é adesão, "não liberou" é atraso do credenciado. Só do lado
   * habilitado — fora do ProntuAI o primeiro desfecho seria sempre zero.
   */
  desfecho_previsao_semana?: Record<string, [number, number, number]>;
  /**
   * Liberações do credenciado por semana ISO, em todo o histórico buscado no
   * BRNET (~7 meses). Só do lado **sem** cadastro: dentro, quem responde pela
   * adesão é `desfecho_previsao_semana`.
   *
   * É o que permite ranquear a inclusão por volume recorrente — mediana das
   * semanas — em vez de pelo previsto da janela, que premia o pico isolado e o
   * credenciado lento.
   */
  liberacoes_semana?: Record<string, number>;
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
  /**
   * Acurácia por exame, do parecer do revisor no modal de feedback. Ausente num
   * back-end anterior ao indicador e null quando a consulta falhou — nos dois
   * casos o card mostra "Em breve". Ver `dashboard_service._agregar_pareceres`.
   */
  acuracia_exames?: AcuraciaExamesDados | null;
}

/** Um período (semana ou mês, mesma chave das outras séries) da acurácia por exame. */
export interface BlocoAcuraciaExames {
  /** Pareceres que entram na acurácia: a IA chegou a julgar os exames. */
  pareceres: number;
  /** Todos os pareceres, inclusive de falha técnica — numerador da adesão. */
  com_parecer: number;
  /** Decisões humanas desde que o modal existe, mais as que têm parecer. */
  decisoes: number;
  /**
   * Por exame: [avaliações, erros por categoria do parecer]. Back-end anterior a
   * 23/10/2026 manda [avaliações, falta indevida, presença indevida].
   */
  exames: Record<string, [number, Record<string, number>] | [number, number, number]>;
  /** Um item por erro, para abrir o exame na lista. Ausente no back-end anterior. */
  casos?: CasoErroExame[];
}

/** Um erro apontado pelo revisor: o exame, o motivo e o documento onde foi. */
export interface CasoErroExame {
  exame: string;
  /** Categoria do parecer (`types/feedback.ts`, CATEGORIAS_EXAME). */
  motivo: string;
  documento: string;
  clinica: string;
  /** Data de envio do documento, ISO. */
  enviado: string;
}

export interface AcuraciaExamesDados {
  /**
   * Data de envio (ISO) do documento mais antigo com parecer — o começo da
   * série. Não é a data do primeiro parecer: dá para avaliar documento antigo.
   */
  desde: string | null;
  series: Partial<Record<SerieKey, Record<string, BlocoAcuraciaExames>>>;
}

/** [antecipado, no dia, atrasado]. */
export type Prazos = [number, number, number];
