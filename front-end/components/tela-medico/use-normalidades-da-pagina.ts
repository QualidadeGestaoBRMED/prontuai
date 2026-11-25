"use client"

import { useEffect, useState } from "react"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import type { NormalidadeDocumento } from "@/types/normalidade"
import type { NormalidadePorExame } from "./documento-medico"

/** `undefined` enquanto carrega; `null` se a rota falhou ou está desligada. */
export type NormalidadesDaPagina = Record<string, NormalidadePorExame | null | undefined>

/**
 * A leitura de normalidade de cada documento da página, para a coluna "Pontos
 * de atenção" bater com o modal. Uma chamada por documento (a página tem 10) e
 * só para quem ainda não foi lido: o refresh da lista não repete as chamadas.
 */
export function useNormalidadesDaPagina(ids: string[]): NormalidadesDaPagina {
  const [lidas, setLidas] = useState<NormalidadesDaPagina>({})
  const chave = ids.join(",")

  useEffect(() => {
    const faltam = chave ? chave.split(",").filter((id) => !(id in lidas)) : []
    if (!faltam.length) return
    setLidas((l) => ({ ...l, ...Object.fromEntries(faltam.map((id) => [id, undefined])) }))
    faltam.forEach((id) => {
      authFetch(API_ENDPOINTS.DOCUMENT_NORMALIDADE(id))
        .then(async (resposta) => {
          if (!resposta.ok) throw new Error(String(resposta.status))
          const dados: NormalidadeDocumento = await resposta.json()
          const porExame = dados.habilitada
            ? Object.fromEntries(dados.itens.map((item) => [item.exame, item.parametros]))
            : null
          setLidas((l) => ({ ...l, [id]: porExame }))
        })
        .catch(() => {
          setLidas((l) => ({ ...l, [id]: null }))
        })
    })
    // Sem cancelar na troca de página: a resposta que chegar depois ainda vale
    // para quando o documento voltar à tela, e cancelar deixaria o id marcado
    // como "carregando" para sempre.
    // `lidas` fica de fora de propósito: só a troca de página dispara a busca.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave])

  return lidas
}
