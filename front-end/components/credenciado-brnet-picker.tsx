"use client"

import { useMemo, useState } from "react"
import { AlertTriangle, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

/** Um credenciado da rede do BRNET, como volta de `GET /v1/clinics/credenciados-brnet`. */
export type CredenciadoBrnet = {
  identificador: string
  nome: string
  cidade?: string | null
  uf?: string | null
  /** Clínicas do ProntuAI já vinculadas a este credenciado (inclusive inativas). */
  clinicas: { id: string; name: string; is_active: boolean }[]
}

type Props = {
  opcoes: CredenciadoBrnet[]
  carregando: boolean
  erro: string | null
  /** Identificador escolhido ("C25414"), ou null. */
  valor: string | null
  onEscolher: (credenciado: CredenciadoBrnet) => void
  /** Na edição, a própria clínica não conta como "já cadastrada". */
  clinicaAtualId?: string
}

const MAX_RESULTADOS = 50

/**
 * "TRÊS RIOS - RJ - ASO (5 cadastros, 1 inativo)" em vez do mesmo nome cinco
 * vezes: as cópias de um credenciado costumam ter nome igual.
 */
function descreverClinicas(clinicas: CredenciadoBrnet["clinicas"]) {
  const porNome = new Map<string, { total: number; inativas: number }>()
  for (const c of clinicas) {
    const atual = porNome.get(c.name) ?? { total: 0, inativas: 0 }
    porNome.set(c.name, { total: atual.total + 1, inativas: atual.inativas + (c.is_active ? 0 : 1) })
  }
  return [...porNome.entries()]
    .map(([nome, { total, inativas }]) => {
      if (total === 1) return inativas ? `${nome} (inativa)` : nome
      const extra = inativas ? `, ${inativas} ${inativas === 1 ? "inativo" : "inativos"}` : ""
      return `${nome} (${total} cadastros${extra})`
    })
    .join("; ")
}

function semAcento(texto: string) {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
}

/**
 * Escolha do credenciado na rede do BRNET (~580), com busca.
 *
 * Lista dentro do modal, e não num popover: popover aberto sobre um Dialog do
 * Radix perde a rolagem da roda do mouse para o bloqueio de scroll do modal.
 *
 * Enquanto o vínculo não é único (migration 014), credenciado que já tem
 * clínica não é bloqueado — aparece marcado, e o aviso diz qual é, para quem
 * cadastra usar a existente em vez de criar mais uma.
 */
export function CredenciadoBrnetPicker({ opcoes, carregando, erro, valor, onEscolher, clinicaAtualId }: Props) {
  const [busca, setBusca] = useState("")
  const [trocando, setTrocando] = useState(false)
  const escolhido = valor ? opcoes.find((o) => o.identificador === valor) : undefined
  const outras = (c: CredenciadoBrnet) => c.clinicas.filter((cl) => cl.id !== clinicaAtualId)

  const resultados = useMemo(() => {
    const termo = semAcento(busca.trim())
    const lista = termo
      ? opcoes.filter((o) => semAcento(o.nome).includes(termo) || o.identificador.toLowerCase().includes(termo))
      : opcoes
    return lista.slice(0, MAX_RESULTADOS)
  }, [opcoes, busca])

  if (carregando) {
    return <p className="text-sm text-gray-500">Carregando a rede credenciada do BRNET…</p>
  }
  if (erro) {
    return <p className="text-sm text-red-600">{erro}</p>
  }

  if (valor && !trocando) {
    const jaCadastradas = escolhido ? outras(escolhido) : []
    return (
      <div className="space-y-2">
        <div className="flex items-start justify-between gap-3 rounded-md border bg-gray-50 px-3 py-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{escolhido?.nome ?? valor}</div>
            <div className="text-xs text-gray-500">
              {escolhido
                ? `${[escolhido.cidade, escolhido.uf].filter(Boolean).join(" / ") || "—"} · ${escolhido.identificador}`
                : `${valor} · não está mais na rede credenciada do BRNET`}
            </div>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => setTrocando(true)}>
            Trocar
          </Button>
        </div>
        {jaCadastradas.length > 0 && (
          <p className="flex gap-1.5 text-xs text-amber-700">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>
              Já existe clínica para este credenciado: {descreverClinicas(jaCadastradas)}. Prefira usar a existente.
            </span>
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar por cidade, UF, nome ou código (C…)"
          className="pl-9"
          autoFocus={trocando}
        />
      </div>
      <div className="max-h-56 overflow-y-auto rounded-md border">
        {resultados.length === 0 ? (
          <div className="px-3 py-6 text-center text-sm text-gray-500">Nenhum credenciado encontrado.</div>
        ) : (
          resultados.map((o) => {
            const jaCadastradas = outras(o)
            return (
              <button
                key={o.identificador}
                type="button"
                onClick={() => {
                  onEscolher(o)
                  setTrocando(false)
                  setBusca("")
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-3 border-b px-3 py-2 text-left text-sm last:border-b-0 hover:bg-gray-50",
                  o.identificador === valor && "bg-gray-50",
                )}
              >
                <span className="min-w-0 truncate">{o.nome}</span>
                <span className="flex shrink-0 items-center gap-2 text-xs text-gray-500">
                  {jaCadastradas.length > 0 && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">já cadastrada</span>
                  )}
                  <span className="font-mono">{o.identificador}</span>
                </span>
              </button>
            )
          })
        )}
      </div>
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>
          {!busca.trim()
            ? `Digite para buscar entre os ${opcoes.length} credenciados do BRNET.`
            : resultados.length === MAX_RESULTADOS
              ? `Mostrando os primeiros ${MAX_RESULTADOS} — refine a busca.`
              : `${resultados.length} ${resultados.length === 1 ? "encontrado" : "encontrados"}.`}
        </span>
        {valor && trocando && (
          <Button type="button" variant="ghost" size="sm" onClick={() => setTrocando(false)}>
            Cancelar troca
          </Button>
        )}
      </div>
    </div>
  )
}
