import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { documentToProcessResult } from "@/lib/document-mapper"
import type { EnvioDoColaborador, ProcessResult, ReenvioLiberado } from "@/types/process"

/** Tag de status do reenvio, na tabela e no modal. */
export const CLASSE_TAG_REENVIO = "border-transparent bg-sky-100 text-sky-800"

/** O original ainda espera o revisor (pendente, ou decidido só pela IA). */
export function emRevisao(reenvio: ReenvioLiberado): boolean {
  return reenvio.situacao === "em_revisao"
}

/** "15/10/2026", no fuso do navegador (o back-end manda a data com fuso). */
function data(iso: string | null | undefined): string {
  if (!iso) return ""
  const quando = new Date(iso)
  return Number.isNaN(quando.getTime()) ? "" : quando.toLocaleDateString("pt-BR")
}

/** A data que importa do original: a da liberação, ou a do envio se ainda está em revisão. */
export function dataDoOriginal(reenvio: ReenvioLiberado): string {
  return data(emRevisao(reenvio) ? reenvio.enviado_em : reenvio.liberado_em)
}

/**
 * O nome do status do reenvio, na tag. A clínica vê "Já revisado" no lugar de
 * "Já liberado" (pedido de 06/11/2026); o revisor, na Checagem, "Já liberado".
 */
export function rotuloReenvio(reenvio?: ReenvioLiberado | null, para: "revisor" | "clinica" = "revisor"): string {
  if (reenvio && emRevisao(reenvio)) return "Já em revisão"
  return para === "clinica" ? "Já revisado" : "Já liberado"
}

/** O link do documento no Histórico, que abre o detalhe dele (`?viewId=`). */
export function linkNoHistorico(documentId: string): string {
  return `/historico?viewId=${encodeURIComponent(documentId)}`
}

/**
 * O que a tag diz ao revisor, ao passar o mouse: desde nov/2026 o reenvio vai
 * para a Checagem, e é o revisor quem decide se ele traz algo novo.
 */
export function explicacaoReenvioParaRevisor(reenvio: ReenvioLiberado): string {
  const quando = dataDoOriginal(reenvio)
  const comparar = "Compare com o envio anterior em \"outros envios deste colaborador\"."
  if (emRevisao(reenvio)) {
    return quando
      ? `Prontuário já enviado em ${quando}, ainda em revisão. ${comparar}`
      : `Prontuário já enviado antes, ainda em revisão. ${comparar}`
  }
  return quando
    ? `Prontuário já liberado em ${quando}. ${comparar}`
    : `Prontuário já liberado antes. ${comparar}`
}

/**
 * O aviso que a clínica via quando reenviava um prontuário já liberado ou em
 * revisão, no tempo em que o reenvio não ia para a Checagem (até nov/2026).
 * Fica para os documentos gravados com o status "reenvio".
 */
export function mensagemReenvio(reenvio: ReenvioLiberado): string {
  const quando = dataDoOriginal(reenvio)
  if (emRevisao(reenvio)) {
    return quando
      ? `Este prontuário já está em revisão desde ${quando}. Não é preciso reenviar.`
      : "Este prontuário já está em revisão. Não é preciso reenviar."
  }
  return quando
    ? `Este prontuário já foi liberado em ${quando}. Não é preciso reenviar.`
    : "Este prontuário já foi liberado. Não é preciso reenviar."
}

/**
 * Devolve à Checagem um documento marcado como reenvio que era complemento —
 * o laudo que faltou, por exemplo. Responde com o documento já atualizado.
 */
export async function enviarComoComplemento(documentId: string): Promise<ProcessResult> {
  const resposta = await authFetch(API_ENDPOINTS.DOCUMENT_COMPLEMENTO(documentId), { method: "POST" })
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null)
    throw new Error(corpo?.detail || "Não foi possível enviar para revisão.")
  }
  return documentToProcessResult(await resposta.json())
}

// Busca em andamento por documento: o aviso de reenvio e a lista de envios do
// modal da Checagem pedem a mesma coisa ao mesmo tempo, e saem numa requisição só.
const enviosEmAndamento = new Map<string, Promise<EnvioDoColaborador[]>>()

/** Os envios do mesmo colaborador ligados a um documento, do mais novo ao mais antigo. */
export function buscarEnvios(documentId: string): Promise<EnvioDoColaborador[]> {
  const emAndamento = enviosEmAndamento.get(documentId)
  if (emAndamento) return emAndamento
  const busca = (async () => {
    const resposta = await authFetch(API_ENDPOINTS.DOCUMENT_ENVIOS(documentId))
    if (!resposta.ok) throw new Error("Não foi possível carregar os envios.")
    const corpo = await resposta.json()
    return Array.isArray(corpo?.envios) ? (corpo.envios as EnvioDoColaborador[]) : []
  })().finally(() => enviosEmAndamento.delete(documentId))
  enviosEmAndamento.set(documentId, busca)
  return busca
}

/** "06/11/2026 às 16:10", no fuso do navegador. */
export function dataEHora(iso: string | null | undefined): string {
  if (!iso) return ""
  const quando = new Date(iso)
  if (Number.isNaN(quando.getTime())) return ""
  const dia = quando.toLocaleDateString("pt-BR")
  const hora = quando.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
  return `${dia} às ${hora}`
}

/**
 * O aviso sobre o reenvio, a partir do envio original como ele está agora
 * (`original`, da lista de envios) — que pode ter sido revisado depois da
 * detecção — ou, sem a lista, do que a detecção gravou (`reenvio`).
 *
 * O revisor vê a decisão e quem revisou; a clínica, só que já foi revisado e
 * quando — sem identificar o revisor (a rota de envios nem manda o nome a ela).
 */
export function avisoDeReenvio(
  reenvio: ReenvioLiberado,
  original: EnvioDoColaborador | null | undefined,
  para: "revisor" | "clinica",
): { titulo: string; detalhe: string } {
  if (original?.revisado) {
    const quando = dataEHora(original.revisado_em)
    if (para === "clinica") {
      return { titulo: "Este prontuário já foi revisado.", detalhe: quando ? `Revisão em ${quando}.` : "" }
    }
    // Sem nome nem e-mail (quem lê não é da BR MED, como a filial da staging):
    // só a data.
    const quem = original.revisado_por_nome || original.revisado_por
    const decisao = original.validation_status === "rejected" ? "rejeitado" : "liberado"
    const detalhe = quem ? `Revisado por ${quem}${quando ? ` em ${quando}` : ""}.` : quando ? `Revisado em ${quando}.` : ""
    return { titulo: `Este prontuário já foi ${decisao}.`, detalhe }
  }
  if (original) {
    const quando = dataEHora(original.enviado_em)
    return {
      titulo: "Este prontuário já foi enviado e ainda aguarda revisão.",
      detalhe: quando ? `Envio anterior em ${quando}.` : "",
    }
  }
  const quando = dataEHora(emRevisao(reenvio) ? reenvio.enviado_em : reenvio.liberado_em)
  if (emRevisao(reenvio)) {
    return { titulo: "Este prontuário já foi enviado e ainda aguarda revisão.", detalhe: quando ? `Envio anterior em ${quando}.` : "" }
  }
  return para === "clinica"
    ? { titulo: "Este prontuário já foi revisado.", detalhe: quando ? `Revisão em ${quando}.` : "" }
    : { titulo: "Este prontuário já foi liberado.", detalhe: quando ? `Liberado em ${quando}.` : "" }
}

/** A segunda linha do aviso: o que fazer se o envio não for repetido de fato. */
export function orientacaoDoReenvio(para: "revisor" | "clinica"): string {
  return para === "clinica"
    ? "Se este envio for uma correção, ele segue para a revisão normalmente."
    : "Se este documento for uma correção ou se a identificação estiver errada, siga o procedimento normal."
}

/** O envio anterior do mesmo arquivo (`POST /documents/envios-anteriores`). */
export type EnvioAnterior = {
  documento_id: string
  enviado_em: string | null
  situacao: "liberado" | "rejeitado" | "em_revisao" | "reenvio"
  filename: string
}

const SITUACAO_ANTERIOR: Record<EnvioAnterior["situacao"], string> = {
  liberado: "já liberado",
  rejeitado: "rejeitado",
  em_revisao: "em revisão",
  reenvio: "enviado como repetido",
}

/** "em 01/10/2026 (já liberado)" */
export function descreverEnvioAnterior(anterior: EnvioAnterior): string {
  const quando = data(anterior.enviado_em)
  return `${quando ? `em ${quando} ` : ""}(${SITUACAO_ANTERIOR[anterior.situacao] ?? anterior.situacao})`
}

/** SHA-256 do arquivo, em hexadecimal — o mesmo `content_hash` que o back-end grava. */
export async function hashDoArquivo(arquivo: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await arquivo.arrayBuffer())
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("")
}

/**
 * Para cada arquivo, o envio anterior com o mesmo conteúdo, se houver. Só o
 * hash vai ao back-end. Falha devolve vazio: a checagem é aviso, nunca bloqueia
 * o envio.
 */
export async function buscarEnviosAnteriores(arquivos: File[]): Promise<Map<File, EnvioAnterior>> {
  const encontrados = new Map<File, EnvioAnterior>()
  try {
    const hashes = await Promise.all(arquivos.map(hashDoArquivo))
    const resposta = await authFetch(API_ENDPOINTS.DOCUMENTS_ENVIOS_ANTERIORES, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hashes }),
    })
    if (!resposta.ok) return encontrados
    const envios: Record<string, EnvioAnterior> = (await resposta.json())?.envios ?? {}
    arquivos.forEach((arquivo, i) => {
      if (envios[hashes[i]]) encontrados.set(arquivo, envios[hashes[i]])
    })
  } catch {
    // Sem a checagem, o envio segue como sempre.
  }
  return encontrados
}

export { data as dataCurta }
