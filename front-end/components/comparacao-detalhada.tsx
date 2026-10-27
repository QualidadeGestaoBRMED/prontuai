"use client"

import { useEffect, useState } from "react"

import ExamesComparativoTable, { ExamesComparativoTableProps, foraDaFaixa } from "@/components/exames-comparativo-table"
import { TagNovo } from "@/components/tag-novo"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { NormalidadeDocumento, ParametroLido } from "@/types/normalidade"
import { TabelaComparacaoItem } from "@/types/process"

type Estado =
  | { fase: "carregando" }
  | { fase: "pronta"; porExame: Record<string, ParametroLido[]> }
  // Rota desligada, sem permissão ou fora do ar: a tabela fica como era.
  | { fase: "indisponivel" }

/**
 * Comparação Detalhada da checagem, com a coluna "Normalidade": o valor lido
 * no laudo para cada exame e se está dentro da faixa de referência.
 *
 * A leitura vem de uma rota própria, e não do documento, porque é calculada na
 * hora com as faixas em vigor: ajustar uma faixa vale também para o que já foi
 * processado. Fica num componente à parte porque o modal sai cedo quando não há
 * documento, antes de qualquer hook.
 *
 * `localizar` liga o atalho até o PDF: a linha do exame e o valor lido levam
 * ao trecho no documento (ver `ExamesComparativoTable`).
 */
export function ComparacaoDetalhada({
  documentId,
  tabela,
  localizar,
}: {
  documentId: string
  tabela: TabelaComparacaoItem[]
  localizar?: ExamesComparativoTableProps["localizar"]
}) {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" })

  useEffect(() => {
    let ativo = true
    setEstado({ fase: "carregando" })
    authFetch(API_ENDPOINTS.DOCUMENT_NORMALIDADE(documentId))
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error(String(resposta.status))
        const dados: NormalidadeDocumento = await resposta.json()
        if (!ativo) return
        if (!dados.habilitada) return setEstado({ fase: "indisponivel" })
        setEstado({
          fase: "pronta",
          porExame: Object.fromEntries(dados.itens.map((item) => [item.exame, item.parametros])),
        })
      })
      .catch(() => {
        // Informativo: a checagem segue sem a coluna.
        if (ativo) setEstado({ fase: "indisponivel" })
      })
    return () => {
      ativo = false
    }
  }, [documentId])

  const normalidade =
    estado.fase === "indisponivel"
      ? undefined
      : { carregando: estado.fase === "carregando", porExame: estado.fase === "pronta" ? estado.porExame : {} }
  const alterados =
    estado.fase === "pronta" ? Object.values(estado.porExame).flat().filter(foraDaFaixa).length : 0
  const comPosicao =
    Object.keys(localizar?.porExame ?? {}).length > 0 ||
    (estado.fase === "pronta" && Object.values(estado.porExame).flat().some((p) => p.localizacao))

  return (
    <div>
      <h4 className={`font-semibold flex flex-wrap items-center gap-2 ${localizar && comPosicao ? "mb-1" : "mb-3"}`}>
        Comparação Detalhada
        {alterados > 0 && (
          <span className="rounded-md border border-red-300 bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
            {alterados} {alterados === 1 ? "valor fora da faixa" : "valores fora da faixa"}
          </span>
        )}
      </h4>
      {localizar && comPosicao && (
        <p className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
          Clique no exame ou no valor lido para vê-lo no documento.
          <TagNovo />
        </p>
      )}
      {tabela.length > 0 && (
        <div className="mb-6">
          <ExamesComparativoTable tabela={tabela} mostrarEvidencia normalidade={normalidade} localizar={localizar} />
        </div>
      )}
    </div>
  )
}
