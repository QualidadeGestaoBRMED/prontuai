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
  /** Expedições por prazo. Só é capturado a partir de jun/26. */
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

/** Credenciado com previsão de liberação a partir de hoje que não usa o ProntuAI. */
export interface ClinicaSemProntuai {
  /** Rótulo do BRNET, "CIDADE - UF - NOME". */
  credenciado: string;
  nome: string;
  cidade: string | null;
  uf: string | null;
  /** Pedidos ainda não liberados com previsão a partir de hoje. */
  pedidos_previstos: number;
  /** ISO. */
  proxima_previsao: string;
  /** Documentos ligados no ProntuAI em todo o histórico — abaixo de 3. */
  documentos: number;
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
   * Pedidos atendidos em clínicas credenciadas, por dia de atendimento —
   * denominador de "Expedições via ProntuAI". Vem da API de monitoramento de
   * credenciados do BRNET (ver `dashboard_service._cruzar_expedicoes`). Vazio
   * quando algum mês não pôde ser buscado — aí o KPI mostra o total absoluto em
   * vez de uma cobertura inventada.
   */
  expedicoes_dia: Record<string, number>;
  /**
   * Numerador: dos mesmos pedidos, os que têm documento liberado no ProntuAI,
   * ligados pelo `pedido_exame_id`. Conta pedido, não documento — reenvio não
   * infla a cobertura.
   */
  expedicoes_prontuai_dia: Record<string, number>;
  /**
   * Primeiro dia (ISO) em que a ligação por pedido existe. Antes dele não há
   * como medir cobertura, e o painel não mostra.
   */
  expedicoes_desde: string | null;
  /** null quando o BRNET não pôde ser consultado. */
  clinicas_sem_prontuai: ClinicaSemProntuai[] | null;
}
