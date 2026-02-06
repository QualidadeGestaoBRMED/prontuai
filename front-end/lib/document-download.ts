import { API_ENDPOINTS } from "@/lib/config"
import { authFetch } from "@/lib/auth-fetch"

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

  const response = await authFetch(API_ENDPOINTS.DOCUMENT_VIEW(id), { headers })
  if (!response.ok) {
    const detail = await response.text().catch(() => "Erro ao baixar documento")
    throw new Error(detail)
  }

  const contentDisposition = response.headers.get("content-disposition") || ""
  const filenameMatch =
    /filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?/i.exec(contentDisposition)
  const serverFilename = filenameMatch?.[1] || filenameMatch?.[2]
  const resolvedFilename = serverFilename
    ? decodeURIComponent(serverFilename)
    : filename || `documento-${id}`

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = resolvedFilename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
