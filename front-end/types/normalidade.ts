/**
 * Normalidade e alteração de exames. Espelho de back-end/app/models/normalidade.py.
 */

import { Localizacao } from "@/types/localizacao"

export type SituacaoParametro = "normal" | "acima" | "abaixo" | "alterado" | "sem_resultado" | "sem_referencia"

/** Valor de um parâmetro (glicose, hemoglobina...) lido no laudo do documento. */
export type ParametroLido = {
  chave: string
  nome: string
  unidade: string
  valor: number | null
  /** Como saiu no laudo ("8,9", "148.000", "Reagente 1/4"). */
  valor_texto: string | null
  /** Faixa impressa no laudo, já formatada ("70 a 99 mg/dL"), ou "não lida no laudo". */
  referencia: string
  situacao: SituacaoParametro
  /** Onde o valor está no PDF (valor e nome do parâmetro). Sem layout do OCR, null. */
  localizacao?: Localizacao | null
}

export type NormalidadeItem = {
  /** Mesmo texto do `exame` da tabela de comparação. */
  exame: string
  parametros: ParametroLido[]
}

export type NormalidadeDocumento = {
  habilitada: boolean
  itens: NormalidadeItem[]
}

/** Linha da tela de Normalidade: um parâmetro que o ProntuAI lê nos laudos. */
export type ParametroLeitura = {
  parametro: string
  nome: string
  unidade: string
  qualitativo: boolean
  normal_texto: string | null
}
