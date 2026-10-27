"use client"

import { useEffect, useState } from "react"

import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { LinhaTexto, Localizacao, LocalizacoesDocumento, TextoDocumento } from "@/types/localizacao"

/**
 * Onde cada exame da Comparação Detalhada aparece no PDF, por nome do exame.
 *
 * Vazio enquanto carrega, para documento sem posição gravada (processado antes
 * de existir, ou pelo OCR local) e se a rota falhar: é só navegação, e a
 * checagem segue sem o atalho. Sem `documentId` (modal fechado) não busca.
 */
export function useLocalizacoes(documentId?: string | null): Record<string, Localizacao[]> {
  const [porExame, setPorExame] = useState<Record<string, Localizacao[]>>({})

  useEffect(() => {
    setPorExame({})
    if (!documentId) return
    let ativo = true
    authFetch(API_ENDPOINTS.DOCUMENT_LOCALIZACOES(documentId))
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error(String(resposta.status))
        const dados: LocalizacoesDocumento = await resposta.json()
        if (!ativo || !dados.disponivel) return
        setPorExame(Object.fromEntries(dados.exames.map((e) => [e.exame, e.ocorrencias])))
      })
      .catch(() => {
        // Informativo: a checagem segue sem o atalho.
      })
    return () => {
      ativo = false
    }
  }, [documentId])

  return porExame
}

/**
 * Texto que o OCR leu, com a posição de cada linha, para a busca no documento.
 * null quando o documento não tem essa leitura gravada (ou a rota falhou): o
 * visualizador procura então no texto do próprio PDF.
 */
export async function carregarTextoDocumento(documentId: string): Promise<LinhaTexto[] | null> {
  const resposta = await authFetch(API_ENDPOINTS.DOCUMENT_TEXTO(documentId))
  if (!resposta.ok) return null
  const dados: TextoDocumento = await resposta.json()
  return dados.disponivel ? dados.linhas : null
}
