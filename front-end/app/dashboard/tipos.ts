/**
 * Contrato dos dados do dashboard de indicadores.
 *
 * É o que `GET /v1/dashboard/indicadores` devolve — a consulta roda no banco do
 * ambiente em que o back-end está (dev, staging ou produção). A exceção é
 * `expedicoes_dia`, que não sai do banco: ver `dados.ts`.
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
   * Expedições de clínicas credenciadas por dia de atendimento — denominador de
   * "Expedições via ProntuAI". Único campo que não sai do banco: o back-end lê
   * de um arquivo no disco, fora do git (ver `dashboard_service.EXPEDICOES_PATH`).
   * Vem vazio quando o servidor não tem a extração — aí o KPI mostra o total
   * absoluto em vez de uma cobertura inventada.
   */
  expedicoes_dia: Record<string, number>;
}
