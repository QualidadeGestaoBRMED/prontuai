import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { documentToProcessResult } from "@/lib/document-mapper"
import type { EnvioDoColaborador, ProcessResult, ReenvioDesfeito, ReenvioLiberado } from "@/types/process"

/** Tag de status do reenvio, na tabela e no modal. */
export const CLASSE_TAG_REENVIO = "border-transparent bg-sky-100 text-sky-800"
/** Tag do reenvio devolvido à Checagem como complemento. */
export const CLASSE_TAG_COMPLEMENTO = "border-transparent bg-violet-100 text-violet-800"

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

/** O nome do status do reenvio, na tag. */
export function rotuloReenvio(reenvio?: ReenvioLiberado | null): string {
  return reenvio && emRevisao(reenvio) ? "Já em revisão" : "Já liberado"
}

/**
 * O aviso que a clínica vê quando reenvia um prontuário que já foi liberado ou
 * que ainda está em revisão. O reenvio não vai para a Checagem: sem o aviso, ela
 * entendia que o documento não tinha sido aprovado e mandava de novo.
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

/** Devolvido sozinho porque o revisor rejeitou o original (ver `devolver_reenvios_em_revisao`). */
function voltouPelaRejeicao(desfeito: ReenvioDesfeito): boolean {
  return desfeito.por.startsWith("rejeição do original")
}

/** Por que este documento voltou para a Checagem, para o revisor. */
export function mensagemComplemento(desfeito: ReenvioDesfeito): string {
  const original = dataDoOriginal(desfeito)
  const deOriginal = original ? ` O envio anterior é de ${original}.` : ""
  if (voltouPelaRejeicao(desfeito)) {
    return `Era um envio repetido e voltou para a revisão porque o envio anterior foi rejeitado — pode ser a versão corrigida.${deOriginal}`
  }
  const quando = data(desfeito.em)
  return `Era um reenvio e foi devolvido para a revisão como complemento por ${desfeito.por}${quando ? ` em ${quando}` : ""}.${deOriginal}`
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

/** Os envios do mesmo colaborador ligados a um documento, do mais novo ao mais antigo. */
export async function buscarEnvios(documentId: string): Promise<EnvioDoColaborador[]> {
  const resposta = await authFetch(API_ENDPOINTS.DOCUMENT_ENVIOS(documentId))
  if (!resposta.ok) throw new Error("Não foi possível carregar os envios.")
  const corpo = await resposta.json()
  return Array.isArray(corpo?.envios) ? corpo.envios : []
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
