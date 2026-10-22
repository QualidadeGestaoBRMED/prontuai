import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { documentToProcessResult } from "@/lib/document-mapper"
import type { ProcessResult, ReenvioLiberado } from "@/types/process"

/** Tag de status do reenvio, na tabela e no modal. */
export const CLASSE_TAG_REENVIO = "border-transparent bg-sky-100 text-sky-800"

/** "15/10/2026", no fuso do navegador (o back-end manda a data com fuso). */
export function dataDaLiberacao(reenvio: ReenvioLiberado): string {
  const data = new Date(reenvio.liberado_em)
  return Number.isNaN(data.getTime()) ? "" : data.toLocaleDateString("pt-BR")
}

/**
 * O aviso que a clínica vê quando reenvia um prontuário já liberado. O reenvio
 * não vai para a Checagem: sem o aviso, ela entendia que o documento não tinha
 * sido aprovado e mandava de novo.
 */
export function mensagemReenvio(reenvio: ReenvioLiberado): string {
  const data = dataDaLiberacao(reenvio)
  return data
    ? `Este prontuário já foi liberado em ${data}. Não é preciso reenviar.`
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
