/**
 * Normalidade e alteração de exames. Espelho de back-end/app/models/normalidade.py.
 */

export type SituacaoParametro = "normal" | "acima" | "abaixo" | "alterado" | "sem_resultado"

/** Valor de um parâmetro (glicose, hemoglobina...) lido no laudo do documento. */
export type ParametroLido = {
  chave: string
  nome: string
  unidade: string
  valor: number | null
  /** Como saiu no laudo ("8,9", "148.000", "Reagente 1/4"). */
  valor_texto: string | null
  /** Faixa em vigor, já formatada ("70 a 99 mg/dL"). */
  referencia: string
  situacao: SituacaoParametro
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

/** Linha da tela de Normalidade: a faixa padrão e a que está valendo. */
export type FaixaNormalidade = {
  parametro: string
  nome: string
  unidade: string
  qualitativo: boolean
  normal_texto: string | null
  padrao_minimo: number | null
  padrao_maximo: number | null
  minimo: number | null
  maximo: number | null
  referencia: string
  ajustada: boolean
  atualizado_por_email: string | null
  atualizado_por_nome: string | null
  atualizado_em: string | null
}
