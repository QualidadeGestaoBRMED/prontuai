import { API_ENDPOINTS } from "@/lib/config"

type DownloadOptions = {
  id: string
  filename?: string
  accessToken?: string | null
}

export async function downloadDocumentPdf(options: DownloadOptions) {
  const { id, filename, accessToken } = options
  const headers: Record<string, string> = {}
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`
  }

  const response = await fetch(API_ENDPOINTS.DOCUMENT_VIEW(id), { headers })
  if (!response.ok) {
    const detail = await response.text().catch(() => "Erro ao baixar documento")
    throw new Error(detail)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename || `documento-${id}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
