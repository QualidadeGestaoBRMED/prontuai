"use client"

import { useEffect, useState } from "react"

import ExamesComparativoTable, { ExamesComparativoTableProps, foraDaFaixa } from "@/components/exames-comparativo-table"
import { TagNovo } from "@/components/tag-novo"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { NormalidadeDocumento, ParametroLido } from "@/types/normalidade"
import { TabelaComparacaoItem } from "@/types/process"

export type EstadoNormalidade =
  | { fase: "carregando" }
  | { fase: "pronta"; porExame: Record<string, ParametroLido[]> }
  // Rota desligada, sem permissão ou fora do ar: a tabela fica como era.
  | { fase: "indisponivel" }

/**
 * Os valores lidos no laudo para cada exame, por nome do exame (a coluna
 * "Normalidade"). Vêm de uma rota própria, e não do documento, porque são
 * calculados na hora com as faixas em vigor: ajustar uma faixa vale também para
 * o que já foi processado. É um hook à parte porque o modal precisa da leitura
 * antes do `return null` (os hooks não podem depender de haver documento) e
 * para seguir a ordem da tabela no botão que passa de exame em exame.
 */
export function useNormalidade(documentId?: string | null): EstadoNormalidade {
  const [estado, setEstado] = useState<EstadoNormalidade>({ fase: "carregando" })

  useEffect(() => {
    setEstado({ fase: "carregando" })
    if (!documentId) return
    let ativo = true
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

  return estado
}

/**
 * Os exames da comparação em duas partes, na linguagem de quem confere a grade
 * do BRNET: os **previstos no BRNET** (o que está na timeline do atendimento) e,
 * numa seção à parte e fechada, os que vieram no prontuário **além do previsto**.
 * Antes ficava tudo numa tabela só ("Comparação Detalhada"), e o "Extra no OCR"
 * no meio dos previstos confundia a conferência. As duas tabelas levam a coluna
 * "Normalidade": o valor lido no laudo e se está dentro da faixa de referência.
 *
 * A seção dos além do previsto abre sozinha quando o destaque no PDF chega num
 * deles (pelo botão que passa de exame em exame), para a linha selecionada não
 * ficar escondida.
 *
 * `localizar` liga o atalho até o PDF: a linha do exame e o valor lido levam
 * ao trecho no documento (ver `ExamesComparativoTable`).
 */
export function ComparacaoDetalhada({
  tabela,
  estado,
  localizar,
}: {
  tabela: TabelaComparacaoItem[]
  estado: EstadoNormalidade
  localizar?: ExamesComparativoTableProps["localizar"]
}) {
  const previstos = tabela.filter((item) => item.status !== "extra_no_ocr")
  const alem = tabela.filter((item) => item.status === "extra_no_ocr")
  const [alemAberto, setAlemAberto] = useState(false)
  const ativo = localizar?.ativo?.exame
  useEffect(() => {
    if (ativo && alem.some((item) => item.exame === ativo)) setAlemAberto(true)
    // `alem` muda de identidade a cada render; o que importa é o exame ativo.
  }, [ativo]) // eslint-disable-line react-hooks/exhaustive-deps

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
        Exames previstos no BRNET
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
      {previstos.length > 0 && (
        <div className="mb-4">
          <ExamesComparativoTable tabela={previstos} mostrarEvidencia normalidade={normalidade} localizar={localizar} />
        </div>
      )}
      {alem.length > 0 && (
        <details
          className="mb-6 rounded-lg border"
          open={alemAberto}
          onToggle={(e) => setAlemAberto(e.currentTarget.open)}
        >
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
            Exames além do previsto no BRNET ({alem.length})
            <span className="block text-xs font-normal text-muted-foreground">
              Vieram no prontuário, mas não estão previstos no BRNET para este atendimento.
            </span>
          </summary>
          <div className="border-t px-1 pb-1">
            <ExamesComparativoTable
              tabela={alem}
              normalidade={normalidade}
              localizar={localizar}
              rotuloColunaExame="Exame no prontuário"
              rotuloExtra="Além do previsto"
            />
          </div>
        </details>
      )}
    </div>
  )
}
