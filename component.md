# Reutilizando a visualizacao de PDF

Este projeto renderiza o PDF usando o visualizador nativo do navegador. O fluxo e simples:

1. O frontend chama um endpoint que retorna o arquivo original.
2. A resposta vira um `Blob`.
3. O browser cria uma URL temporaria com `URL.createObjectURL(blob)`.
4. Um `iframe` renderiza essa URL.
5. Ao fechar/desmontar o componente, a URL temporaria e liberada com `URL.revokeObjectURL`.

No projeto atual, a implementacao esta concentrada em:

- `front-end/app/checagem/page.tsx`: carrega o PDF e guarda a URL temporaria.
- `front-end/components/document-details-modal-checagem.tsx`: renderiza o `iframe`.
- `back-end/app/api/v1/documents.py`: retorna o arquivo com `Content-Disposition: inline`.

## Hook reutilizavel

Crie um arquivo como `use-pdf-preview.ts`:

```tsx
"use client"

import { useCallback, useEffect, useState } from "react"

type UsePdfPreviewOptions = {
  /**
   * Permite substituir o fetch padrao.
   * No ProntuAI, por exemplo, da para passar um authFetch que renova sessao/token.
   */
  fetcher?: typeof fetch

  /**
   * Callback opcional para exibir toast, alert ou registrar erro.
   */
  onError?: (error: unknown) => void
}

export function usePdfPreview(options: UsePdfPreviewOptions = {}) {
  const [url, setUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const close = useCallback(() => {
    setUrl((previousUrl) => {
      // Sempre libere a URL temporaria para evitar vazamento de memoria.
      if (previousUrl) URL.revokeObjectURL(previousUrl)
      return null
    })
  }, [])

  const open = useCallback(
    async (pdfEndpoint: string) => {
      setLoading(true)

      try {
        const response = await (options.fetcher ?? fetch)(pdfEndpoint)

        if (!response.ok) {
          throw new Error("Nao foi possivel carregar o documento.")
        }

        // O endpoint deve retornar o binario do PDF.
        const blob = await response.blob()

        // Cria uma URL temporaria local, consumivel por iframe, object ou window.open.
        const objectUrl = URL.createObjectURL(blob)

        setUrl((previousUrl) => {
          // Se ja havia um PDF aberto, libera antes de trocar pelo novo.
          if (previousUrl) URL.revokeObjectURL(previousUrl)
          return objectUrl
        })
      } catch (error) {
        options.onError?.(error)
      } finally {
        setLoading(false)
      }
    },
    [options]
  )

  useEffect(() => {
    // Cleanup automatico quando o componente que usa o hook desmontar.
    return close
  }, [close])

  return {
    url,
    loading,
    open,
    close,
  }
}
```

## Componente do preview

Crie um arquivo como `pdf-preview.tsx`:

```tsx
type PdfPreviewProps = {
  url: string | null
  loading?: boolean
  title?: string
}

export function PdfPreview({
  url,
  loading,
  title = "Documento",
}: PdfPreviewProps) {
  /**
   * Esses parametros no hash escondem partes da toolbar do viewer nativo
   * em navegadores que respeitam essa configuracao.
   */
  const src = url
    ? url.includes("#")
      ? `${url}&toolbar=0&navpanes=0&scrollbar=0`
      : `${url}#toolbar=0&navpanes=0&scrollbar=0`
    : ""

  return (
    <div className="h-[70vh] overflow-hidden rounded-lg border bg-muted/20">
      {url ? (
        <iframe
          title={title}
          src={src}
          className="h-full w-full"
        />
      ) : (
        <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
          {loading ? "Carregando documento..." : "Nenhum documento carregado"}
        </div>
      )}
    </div>
  )
}
```

## Exemplo de uso em uma tela

```tsx
"use client"

import { PdfPreview } from "./pdf-preview"
import { usePdfPreview } from "./use-pdf-preview"

export function MinhaTela() {
  const documentId = "123"

  const preview = usePdfPreview({
    /**
     * Troque por toast.error, sonner, logger etc. se o projeto tiver.
     */
    onError: () => alert("Falha ao carregar o PDF."),
  })

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => preview.open(`/api/documents/${documentId}/view`)}
        disabled={preview.loading}
      >
        {preview.loading ? "Carregando..." : "Visualizar documento"}
      </button>

      {preview.url && (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => window.open(preview.url!, "_blank", "noopener,noreferrer")}
          >
            Abrir em nova aba
          </button>

          <button type="button" onClick={preview.close}>
            Fechar
          </button>
        </div>
      )}

      <PdfPreview
        url={preview.url}
        loading={preview.loading}
        title="Documento PDF"
      />
    </div>
  )
}
```

## Versao com fetch autenticado

Se o outro projeto tiver autenticacao, passe um `fetcher` proprio:

```tsx
const preview = usePdfPreview({
  fetcher: authFetch,
  onError: () => toast.error("Falha ao carregar o documento."),
})
```

Um exemplo simples de `authFetch`:

```tsx
export async function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)

  if (response.status !== 401) {
    return response
  }

  // Exemplo: tenta renovar a sessao/token.
  const refreshResponse = await fetch("/api/auth/refresh-token", {
    method: "POST",
  })

  if (refreshResponse.ok) {
    return fetch(input, init)
  }

  return response
}
```

## Backend FastAPI

O endpoint precisa retornar o arquivo como resposta inline. O ponto importante e o header `Content-Disposition`.

```py
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()


@app.get("/api/documents/{document_id}/view")
async def view_document(document_id: str):
    # Busque no banco o caminho real do PDF.
    path = buscar_caminho_do_pdf(document_id)

    if not path:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")

    response = FileResponse(
        path,
        media_type="application/pdf",
        filename="documento.pdf",
    )

    # "inline" pede para o navegador tentar abrir/renderizar em vez de baixar.
    response.headers["Content-Disposition"] = 'inline; filename="documento.pdf"'
    return response
```

## Backend Next.js Route Handler

Se o backend/proxy for uma rota do Next.js, o retorno pode ser assim:

```tsx
import { NextResponse } from "next/server"

export async function GET(
  request: Request,
  { params }: { params: { id: string } }
) {
  const file = await buscarPdfComoArrayBuffer(params.id)

  if (!file) {
    return NextResponse.json(
      { error: "Documento nao encontrado" },
      { status: 404 }
    )
  }

  return new NextResponse(file, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'inline; filename="documento.pdf"',
    },
  })
}
```

## Checklist rapido

- O endpoint deve retornar o binario do PDF, nao JSON.
- Use `Content-Type: application/pdf`.
- Use `Content-Disposition: inline`.
- No frontend, renderize a URL criada com `URL.createObjectURL(blob)` em um `iframe`.
- Sempre chame `URL.revokeObjectURL(url)` quando trocar ou fechar o preview.
- Se houver autenticacao, use um `fetcher` autenticado no hook.

