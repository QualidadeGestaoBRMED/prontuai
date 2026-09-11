/**
 * Documento arquivado: leitura da resposta 410 do back-end.
 *
 * Depois da janela de retenção, o PDF aprovado sai do disco da VPS para o
 * arquivo morto no Drive (ops/deploy/archive_documents_to_drive.sh) e o
 * endpoint de visualização passa a responder 410 Gone. Isso é diferente de
 * 404: 404 significa que o arquivo deveria estar lá e não está — defeito, que
 * continua merecendo mensagem de erro genérica. 410 é estado esperado, com
 * caminho de recuperação, e é o que o usuário precisa saber.
 */

export type DocumentoArquivadoInfo = {
  archivedAt?: string
  filename?: string
  contact?: string
}

/**
 * Retorna os dados do documento arquivado, ou null se a resposta for
 * outra coisa. Usa `clone()` para não consumir o corpo — quem chamou pode
 * ainda querer ler a resposta como texto/blob no caminho de erro comum.
 */
export async function lerDocumentoArquivado(
  response: Response,
): Promise<DocumentoArquivadoInfo | null> {
  if (response.status !== 410) return null
  try {
    const data = await response.clone().json()
    const detail = data?.detail
    if (!detail || detail.code !== "documento_arquivado") return null
    return {
      archivedAt: detail.archived_at,
      filename: detail.filename,
      contact: detail.contact,
    }
  } catch {
    // 410 sem corpo reconhecível ainda é "arquivado"; cai na frase sem data e
    // sem contato, em vez de virar erro de rede.
    return {}
  }
}

/**
 * Monta a mensagem exibida ao usuário.
 *
 * A data é formatada AQUI, no navegador, e não no back-end: archived_at chega
 * em UTC, e só o navegador sabe o fuso de quem está lendo. Formatada no
 * servidor, um arquivamento feito à noite apareceria com a data do dia
 * seguinte.
 *
 * O contato vem de DOCUMENT_ARCHIVE_CONTACT no back-end e já traz o artigo
 * ("o setor de Qualidade e Gestão"), para a frase concordar com qualquer
 * valor configurado.
 */
export function mensagemDocumentoArquivado(info: DocumentoArquivadoInfo): string {
  let quando = ""
  if (info.archivedAt) {
    const data = new Date(info.archivedAt)
    if (!Number.isNaN(data.getTime())) quando = ` em ${data.toLocaleDateString("pt-BR")}`
  }
  const recuperacao = info.contact
    ? `entre em contato com ${info.contact}`
    : "solicite ao responsável"
  return (
    `Este documento foi arquivado${quando} e não está mais disponível para visualização. ` +
    `Para recuperá-lo, ${recuperacao}.`
  )
}

/** Erro lançado por downloadDocumentPdf quando o documento está arquivado. */
export class DocumentoArquivadoError extends Error {
  readonly info: DocumentoArquivadoInfo
  constructor(info: DocumentoArquivadoInfo) {
    super(mensagemDocumentoArquivado(info))
    this.name = "DocumentoArquivadoError"
    this.info = info
  }
}
