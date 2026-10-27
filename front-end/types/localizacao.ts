/**
 * Onde um trecho do documento está no PDF. Espelho de back-end/app/models/localizacao.py.
 * Coordenadas em fração da página (0 a 1, origem no canto superior esquerdo).
 */

export type Caixa = { x: number; y: number; w: number; h: number }

export type Localizacao = {
  pagina: number
  caixas: Caixa[]
}

export type LocalizacaoExame = {
  /** Mesmo texto do `exame` da tabela de comparação. */
  exame: string
  /** Na ordem em que a tela oferece: primeiro a que tem mais cara de laudo. */
  ocorrencias: Localizacao[]
}

/** Um campo da Checklist de Campos e as linhas que o comprovam (as da evidência). */
export type LocalizacaoCampo = {
  /** Mesmo `field` da checklist: cpf, nome_paciente, data, crm_medico, assinatura. */
  campo: string
  ocorrencias: Localizacao[]
}

export type LocalizacoesDocumento = {
  /** false: documento sem posição gravada (lido antes de existir, ou pelo OCR local). */
  disponivel: boolean
  exames: LocalizacaoExame[]
  campos?: LocalizacaoCampo[]
}

/** Uma linha do texto lido (OCR, ou o texto do próprio PDF) e a caixa dela na página. */
export type LinhaTexto = Caixa & {
  pagina: number
  texto: string
  /** Faixa horizontal de cada palavra, na ordem do texto: [x, w]. */
  palavras?: number[][]
}

export type TextoDocumento = {
  /** false: documento sem posição gravada; a busca cai no texto do próprio PDF. */
  disponivel: boolean
  linhas: LinhaTexto[]
}
