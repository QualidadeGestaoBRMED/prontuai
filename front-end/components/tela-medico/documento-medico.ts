import { foraDaFaixa } from "@/components/exames-comparativo-table"
import type { DocumentApi } from "@/types/document"
import type { Localizacao } from "@/types/localizacao"
import type { ParametroLido } from "@/types/normalidade"
import type { TabelaComparacaoItem } from "@/types/process"
import type { Analise, DocumentoAprovado, ExamePrevisto, NormalidadeExame } from "./tipos"

/**
 * Ponte entre o que já existe (documento aprovado na Checagem + leitura de
 * normalidade pela faixa do laudo) e o contrato da tela, enquanto a API de
 * conduta não existe. A sugestão de conduta fica de fora: a tela mostra o
 * aviso genérico de "ainda não disponível".
 */

/** Leitura de normalidade por nome de exame, como `useNormalidade` entrega. */
export type NormalidadePorExame = Record<string, ParametroLido[]>

const texto = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null)

export function paraDocumentoAprovado(doc: DocumentApi): DocumentoAprovado {
  const payload = (doc.result_payload && typeof doc.result_payload === "object" ? doc.result_payload : {}) as Record<
    string,
    unknown
  >
  const brmed = (payload.brmed_result && typeof payload.brmed_result === "object" ? payload.brmed_result : {}) as Record<
    string,
    unknown
  >
  const tabela = (Array.isArray(payload.tabela_comparacao) ? payload.tabela_comparacao : []) as TabelaComparacaoItem[]
  const cpf = (doc.cpf || "").replace(/\D/g, "")
  return {
    documento_id: doc.id,
    filename: doc.filename,
    paciente_cpf: cpf || null,
    paciente_nome: texto(payload.patient_name),
    clinica: doc.clinic_name ?? null,
    enviado_em: doc.uploaded_at ?? null,
    aprovado_em: doc.reviewed_at ?? null,
    tipo_exame: texto(brmed.tipo_pedido_exame),
    pedido_exame_id: brmed.pedido_exame_id != null ? String(brmed.pedido_exame_id) : null,
    exames: tabela
      .filter((t) => t.status !== "extra_no_ocr")
      .map((t) => ({ exame: t.exame, encontrado: t.status !== "faltante" })),
    extras: tabela.filter((t) => t.status === "extra_no_ocr").map((t) => t.exame),
  }
}

/** "PERIÓDICO SEMESTRAL" → "Periódico semestral". */
export function rotuloTipoExame(tipo: string | null | undefined): string {
  if (!tipo) return "—"
  const minusculo = tipo.replace(/_/g, " ").toLocaleLowerCase("pt-BR")
  return minusculo.charAt(0).toLocaleUpperCase("pt-BR") + minusculo.slice(1)
}

const temCaixa = (l: Localizacao | null | undefined): l is Localizacao => !!l?.caixas?.length

/**
 * Onde o exame aparece no PDF, do que mais interessa ao médico para o resto:
 * os valores fora da faixa (o "Pág. N" leva ao primeiro deles, e não a um
 * valor normal do mesmo laudo), depois as ocorrências do próprio exame. Sem
 * nenhuma das duas, o primeiro valor lido.
 */
function ocorrenciasDo(parametros: ParametroLido[], doExame: Localizacao[] | undefined): Localizacao[] {
  const alterados = parametros.filter(foraDaFaixa).map((p) => p.localizacao).filter(temCaixa)
  const exame = (doExame ?? []).filter(temCaixa)
  if (alterados.length || exame.length) return [...alterados, ...exame]
  const lido = parametros.map((p) => p.localizacao).find(temCaixa)
  return lido ? [lido] : []
}

function paraNormalidade(exame: string, parametros: ParametroLido[], pagina: number | null): NormalidadeExame {
  const alterados = parametros.filter(foraDaFaixa)
  // Direção só quando todos os alterados apontam para o mesmo lado.
  const direcoes = new Set(alterados.map((p) => p.situacao))
  const direcao = direcoes.size === 1 && (direcoes.has("acima") || direcoes.has("abaixo"))
    ? (alterados[0].situacao as "acima" | "abaixo")
    : null
  return {
    exame_id: exame,
    exame,
    classificacao: alterados.length ? "alterado" : "normal",
    direcao,
    desvio: null,
    valor: null,
    unidade: null,
    faixa_referencia: null,
    pagina,
    parametros,
  }
}

/**
 * A `Analise` da tela a partir do documento e da leitura de normalidade. Sem
 * leitura (rota fora do ar ou desligada), os exames entram só com presença.
 */
export function montarAnalise(
  doc: DocumentoAprovado,
  normalidade: NormalidadePorExame | null,
  localizacoes: Record<string, Localizacao[]>,
): Analise {
  const exames: ExamePrevisto[] = []
  const normalidades: NormalidadeExame[] = []
  const incluir = (exame: string, encontrado: boolean) => {
    const parametros = (encontrado && normalidade?.[exame]) || []
    const ocorrencias = encontrado ? ocorrenciasDo(parametros, localizacoes[exame]) : []
    const pagina = ocorrencias[0]?.pagina ?? null
    exames.push({ exame_id: exame, exame, encontrado, pagina, ocorrencias })
    if (parametros.length) normalidades.push(paraNormalidade(exame, parametros, pagina))
  }
  doc.exames.forEach((e) => incluir(e.exame, e.encontrado))
  // Além do previsto, só o que tem valor fora da faixa: o resto não muda a conduta.
  doc.extras.filter((e) => normalidade?.[e]?.some(foraDaFaixa)).forEach((e) => incluir(e, true))

  return {
    analise_id: doc.documento_id,
    status: "concluido",
    pedido_exame_id: doc.pedido_exame_id,
    origem_pedido: "encontrado",
    versao_modelo: "",
    confianca_calibrada: false,
    disponivel_ate: "",
    decisao_ate: "",
    contexto: {
      empresa: null,
      tipo_exame: doc.tipo_exame,
      funcao: null,
      riscos: [],
      atividades_criticas: [],
      particularidades: [],
      ficha_medica: [],
    },
    presenca_exames: { todos_encontrados: exames.every((e) => e.encontrado), exames },
    normalidade: normalidades,
    conduta_sugerida: null,
    motivo_sem_sugestao: null,
    contexto_disponivel: false,
  }
}

/** A mesma conta do "Pontos de atenção" do modal: exame faltante ou com valor fora da faixa. */
export function contarPontos(doc: DocumentoAprovado, normalidade: NormalidadePorExame | null): number {
  const faltantes = doc.exames.filter((e) => !e.encontrado).length
  if (!normalidade) return faltantes
  const alterados = [...doc.exames.filter((e) => e.encontrado).map((e) => e.exame), ...doc.extras].filter((e) =>
    normalidade[e]?.some(foraDaFaixa),
  ).length
  return faltantes + alterados
}
