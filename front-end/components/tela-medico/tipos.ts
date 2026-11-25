/**
 * Contrato da análise de normalidade e conduta sugerida, como descrito no doc
 * "ProntuAI — API de Normalidade e Conduta Sugerida" (rev. 421). A API ainda
 * não existe: por enquanto a tela monta a `Analise` a partir do documento
 * aprovado e da leitura de normalidade que já existem (`documento-medico.ts`).
 * Os campos marcados "fora do doc" são dessa montagem.
 */

import type { Localizacao } from "@/types/localizacao"
import type { ParametroLido } from "@/types/normalidade"

export type SituacaoAso = "LIBERADO" | "LIBERADO_COM_ENCAMINHAMENTO" | "RETIDO" | "INAPTO"

export type TipoExame =
  | "ADMISSIONAL"
  | "PERIODICO"
  | "RETORNO_AO_TRABALHO"
  | "MUDANCA_DE_RISCO"
  | "DEMISSIONAL"

export type MotivoSemSugestao = "CONFIANCA_BAIXA" | "FORA_DO_PROTOCOLO" | "FALHA_NA_LEITURA" | "PEDIDO_DIVERGENTE"

export type Classificacao = "normal" | "alterado" | "inconclusivo"

export interface CampoFicha {
  campo: string
  valor: "sim" | "nao" | "nao_informado"
}

export interface ContextoAnalise {
  /** null enquanto o ProntuAI não recebe a empresa (fora do doc). */
  empresa: string | null
  /** O BRNET manda texto livre ("PERIÓDICO SEMESTRAL"), não só os do doc. */
  tipo_exame: TipoExame | string | null
  /** null enquanto o ProntuAI não recebe a função (fora do doc). */
  funcao: string | null
  riscos: string[]
  atividades_criticas: string[]
  particularidades: string[]
  ficha_medica: CampoFicha[]
}

export interface ExamePrevisto {
  exame_id: string
  exame: string
  encontrado: boolean
  pagina: number | null
  /**
   * Onde o exame aparece no PDF: os valores fora da faixa quando há, senão o
   * próprio exame (fora do doc). Ver `ocorrenciasDo`.
   */
  ocorrencias?: Localizacao[]
  /** true quando `ocorrencias` são valores alterados: só esses entram na navegação. */
  ocorrencias_alteradas?: boolean
}

export interface NormalidadeExame {
  exame_id: string
  exame: string
  classificacao: Classificacao
  direcao: "acima" | "abaixo" | null
  desvio: number | null
  valor: string | null
  unidade: string | null
  faixa_referencia: { min?: number | null; max?: number | null; texto: string } | null
  pagina: number | null
  /**
   * Todos os valores lidos no laudo deste exame, pela rota de normalidade que
   * já existe (fora do doc). Presente, a tela mostra um valor por parâmetro
   * em vez do `valor` único.
   */
  parametros?: ParametroLido[]
}

export interface RegraCliente {
  exame_id: string
  regra: string
  efeito: SituacaoAso
}

export interface CondutaSugerida {
  situacao_aso: SituacaoAso
  confianca: number
  fatores: string[]
  explicacao: string | null
  alertas: string[]
  regras_cliente: RegraCliente[]
}

export interface Analise {
  analise_id: string
  status: "processando" | "concluido" | "erro"
  pedido_exame_id: string | null
  origem_pedido: "informado" | "encontrado"
  versao_modelo: string
  confianca_calibrada: boolean
  /** Probabilidade de COM encaminhamento que o modelo deu (0 a 1); null sem resposta do modelo. */
  prob_encaminhamento?: number | null
  disponivel_ate: string
  decisao_ate: string
  contexto: ContextoAnalise
  presenca_exames: { todos_encontrados: boolean; exames: ExamePrevisto[] }
  normalidade: NormalidadeExame[]
  conduta_sugerida: CondutaSugerida | null
  motivo_sem_sugestao: MotivoSemSugestao | null
  /**
   * false enquanto riscos, atividade crítica e ficha médica não chegam ao
   * ProntuAI: a tela avisa em vez de mostrar "Nenhum" (fora do doc).
   */
  contexto_disponivel?: boolean
}

/**
 * Linha da tela do médico: um documento que um revisor APROVOU na Checagem
 * (rejeitado e o aprovado só pela IA não chegam aqui). Tudo vem do documento,
 * que já guarda CPF e nome extraídos localmente (nada vai para a OpenAI).
 */
export interface DocumentoAprovado {
  documento_id: string
  filename: string
  /** Só dígitos. */
  paciente_cpf: string | null
  paciente_nome: string | null
  clinica: string | null
  /** ISO 8601. */
  enviado_em: string | null
  /** ISO 8601: quando o revisor aprovou. */
  aprovado_em: string | null
  /** Como o BRNET manda ("PERIÓDICO", "ADMISSIONAL"...). */
  tipo_exame: string | null
  pedido_exame_id: string | null
  /** Exames previstos no BRNET e se vieram no documento (a comparação da Checagem). */
  exames: { exame: string; encontrado: boolean }[]
  /** Exames que vieram além do previsto: entram na revisão se tiverem valor alterado. */
  extras: string[]
}

/** Corpo do `POST /v1/analises/{analise_id}/decisao`. Não leva nome, CPF nem CRM. */
export interface DecisaoMedico {
  sugestao_exibida: boolean
  concordou_com_sugestao: boolean | null
  conduta_final: { situacao_aso: SituacaoAso | null; observacao: string | null }
  normalidade_final: { exame_id: string; classificacao: string }[]
  decidido_em: string
}
