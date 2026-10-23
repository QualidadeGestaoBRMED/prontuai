"use client"

import { useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { createPortal } from "react-dom"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

/** Um credenciado da rede do BRNET, como volta de `GET /v1/clinics/credenciados-brnet`. */
export type CredenciadoBrnet = {
  identificador: string
  nome: string
  cidade?: string | null
  uf?: string | null
  /** E-mail do credenciado no BRNET; vai para a clínica quando o campo fica vazio. */
  email?: string | null
  /** Clínicas do ProntuAI já vinculadas a este credenciado (inclusive inativas). */
  clinicas: { id: string; name: string; is_active: boolean }[]
}

type Props = {
  id: string
  /** O nome digitado no campo. */
  value: string
  /** Digitar desfaz a escolha: o nome deixa de ser o do credenciado. */
  onChange: (nome: string) => void
  onEscolher: (credenciado: CredenciadoBrnet) => void
  opcoes: CredenciadoBrnet[]
  placeholder?: string
}

const MIN_CARACTERES = 2
const MAX_SUGESTOES = 8
/** Altura das 8 sugestões (36px cada + respiro): a lista inteira cabe sem rolar. */
const ALTURA_LISTA = 300
/** Distância mínima entre a lista e a borda da tela. */
const MARGEM_TELA = 8

/**
 * Onde a lista fica na tela, colada no campo. Abre para baixo; só sobe quando
 * embaixo não cabe e em cima há mais espaço.
 */
function posicaoDaLista(campo: HTMLElement): CSSProperties {
  const r = campo.getBoundingClientRect()
  const abaixo = window.innerHeight - r.bottom - MARGEM_TELA
  const acima = r.top - MARGEM_TELA
  const subir = abaixo < ALTURA_LISTA && acima > abaixo
  return {
    position: "fixed",
    left: r.left,
    width: r.width,
    maxHeight: Math.min(ALTURA_LISTA, subir ? acima : abaixo),
    ...(subir ? { bottom: window.innerHeight - r.top + 4 } : { top: r.bottom + 4 }),
  }
}

function semAcento(texto: string) {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
}

/**
 * "TRÊS RIOS - RJ - ASO (5 cadastros, 1 inativo)" em vez do mesmo nome cinco
 * vezes: as cópias de um credenciado costumam ter nome igual.
 */
export function descreverClinicas(clinicas: CredenciadoBrnet["clinicas"]) {
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

/**
 * Nome da clínica com sugestões da rede credenciada do BRNET (~580) conforme
 * a digitação. Escolher uma sugestão é o que vincula a clínica ao credenciado;
 * o código do BRNET não aparece, mas a busca também o aceita ("C4071").
 *
 * A lista sai do modal: vai num portal para o `body`, com posição fixa colada
 * no campo. Dentro do modal ela ficava presa no `overflow-y-auto` do
 * DialogContent, que ganhava barra de rolagem e escondia as sugestões.
 *
 * Fora do modal valem três cuidados com o Dialog do Radix:
 * - o portal continua filho do Dialog na árvore do React, então clicar na lista
 *   não conta como clique fora e o modal não fecha;
 * - o Dialog põe `pointer-events: none` no `body`, e a lista devolve o `auto`;
 * - o bloqueio de scroll do Dialog cancela a rolagem de tudo que está fora
 *   dele. As 8 sugestões cabem sem rolar; quando a tela é baixa e a lista
 *   encolhe, a roda do mouse rola a lista à mão.
 */
export function CredenciadoBrnetAutocomplete({ id, value, onChange, onEscolher, opcoes, placeholder }: Props) {
  const [aberto, setAberto] = useState(false)
  const [ativo, setAtivo] = useState(0)
  const campoRef = useRef<HTMLDivElement>(null)
  const [posicao, setPosicao] = useState<CSSProperties | null>(null)

  const termo = semAcento(value.trim())
  const sugestoes = useMemo(() => {
    if (termo.length < MIN_CARACTERES) return []
    return opcoes
      .filter((o) => semAcento(o.nome).includes(termo) || o.identificador.toLowerCase() === termo)
      .slice(0, MAX_SUGESTOES)
  }, [opcoes, termo])
  const mostrar = aberto && sugestoes.length > 0

  // Segue o campo a cada quadro enquanto a lista está aberta. Evento de scroll
  // e resize não basta: o modal abre com animação de escala, e quem digita
  // logo ao abrir mediria o campo ainda encolhido. Só re-renderiza quando a
  // posição muda de fato.
  useLayoutEffect(() => {
    if (!mostrar) return
    let quadro = 0
    let anterior = ""
    const atualizar = () => {
      if (campoRef.current) {
        const nova = posicaoDaLista(campoRef.current)
        const chave = JSON.stringify(nova)
        if (chave !== anterior) {
          anterior = chave
          setPosicao(nova)
        }
      }
      quadro = requestAnimationFrame(atualizar)
    }
    atualizar()
    return () => cancelAnimationFrame(quadro)
  }, [mostrar])

  const escolher = (credenciado: CredenciadoBrnet) => {
    onEscolher(credenciado)
    setAberto(false)
  }

  return (
    <div ref={campoRef}>
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={mostrar}
        aria-controls={`${id}-sugestoes`}
        onChange={(e) => {
          onChange(e.target.value)
          setAtivo(0)
          setAberto(true)
        }}
        onFocus={() => setAberto(true)}
        // O clique numa sugestão chega depois do blur: sem o atraso, a lista
        // fecharia antes de registrar a escolha.
        onBlur={() => window.setTimeout(() => setAberto(false), 120)}
        onKeyDown={(e) => {
          if (!mostrar) return
          if (e.key === "ArrowDown") {
            e.preventDefault()
            setAtivo((i) => Math.min(i + 1, sugestoes.length - 1))
          } else if (e.key === "ArrowUp") {
            e.preventDefault()
            setAtivo((i) => Math.max(i - 1, 0))
          } else if (e.key === "Enter") {
            e.preventDefault()
            escolher(sugestoes[ativo])
          } else if (e.key === "Escape") {
            setAberto(false)
          }
        }}
      />
      {mostrar && posicao && createPortal(
        <ul
          id={`${id}-sugestoes`}
          role="listbox"
          style={{ ...posicao, pointerEvents: "auto" }}
          onWheel={(e) => {
            e.currentTarget.scrollTop += e.deltaY
          }}
          className="z-[60] overflow-y-auto rounded-md border bg-white py-1 shadow-lg"
        >
          {sugestoes.map((o, i) => (
            <li
              key={o.identificador}
              role="option"
              aria-selected={i === ativo}
              onMouseDown={(e) => {
                e.preventDefault()
                escolher(o)
              }}
              onMouseEnter={() => setAtivo(i)}
              className={cn(
                "flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm",
                i === ativo && "bg-gray-100",
              )}
            >
              <span className="min-w-0 truncate">{o.nome}</span>
              {o.clinicas.length > 0 && (
                <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                  já cadastrada
                </span>
              )}
            </li>
          ))}
        </ul>,
        document.body,
      )}
    </div>
  )
}
