"use client"

import { useEffect, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import type { DocumentApi } from "@/types/document"

/** O parâmetro do link que abre um documento: `?viewId=<id>`. */
export const PARAMETRO_DO_LINK = "viewId"

type Opcoes = {
  /** A página da lista ainda está carregando: espera para procurar o documento nela. */
  carregando: boolean
  /** O documento, se ele está na página carregada (evita uma chamada a mais). */
  naPagina: (id: string) => DocumentApi | undefined
  /** Abre o modal do documento. */
  abrir: (documento: DocumentApi) => void
}

/**
 * Abre o modal do documento quando a URL traz `?viewId=<id>`: o link que o
 * botão "Copiar link" gera, nas telas de Pendentes, Checagem, Histórico e
 * Conduta Médica.
 *
 * A lista é paginada, então o documento quase nunca está na página carregada.
 * Fora dela, ele vem de `GET /v1/documents/{id}`, que já aplica a regra de
 * clínica do SENDER no back-end. É o comportamento que o Histórico tinha,
 * agora igual nas quatro telas.
 *
 * Abre uma vez por id: sem essa trava o modal reabriria sozinho a cada
 * atualização da lista depois de fechado. Precisa de `<Suspense>` em volta da
 * página, por causa do `useSearchParams`.
 */
export function useDocumentoDoLink({ carregando, naPagina, abrir }: Opcoes) {
  const searchParams = useSearchParams()
  const viewId = searchParams.get(PARAMETRO_DO_LINK)
  const aberto = useRef<string | null>(null)
  // As funções mudam a cada render; o efeito lê a versão atual por aqui.
  const naPaginaRef = useRef(naPagina)
  naPaginaRef.current = naPagina
  const abrirRef = useRef(abrir)
  abrirRef.current = abrir

  useEffect(() => {
    if (!viewId || aberto.current === viewId) return
    const daPagina = naPaginaRef.current(viewId)
    if (daPagina) {
      aberto.current = viewId
      abrirRef.current(daPagina)
      return
    }
    if (carregando) return
    aberto.current = viewId
    void (async () => {
      try {
        const resposta = await authFetch(`${API_ENDPOINTS.DOCUMENTS}/${encodeURIComponent(viewId)}`)
        if (!resposta.ok) {
          toast.error(
            resposta.status === 404
              ? "Documento não encontrado."
              : resposta.status === 403
                ? "Você não tem permissão para abrir este documento."
                : "Não foi possível abrir o documento.",
          )
          return
        }
        abrirRef.current((await resposta.json()) as DocumentApi)
      } catch (erro) {
        console.error("Falha ao abrir documento do link:", erro)
        toast.error("Não foi possível abrir o documento.")
      }
    })()
  }, [viewId, carregando])
}

/** O link que abre o documento na tela atual (a mesma rota, com `?viewId=`). */
export function linkDoDocumento(id: string): string {
  const url = new URL(window.location.pathname, window.location.origin)
  url.searchParams.set(PARAMETRO_DO_LINK, id)
  return url.toString()
}
