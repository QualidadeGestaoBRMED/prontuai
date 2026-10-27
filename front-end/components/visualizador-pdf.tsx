"use client"

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist"
import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon, ChevronUpIcon, Loader2Icon, SearchIcon, XIcon } from "lucide-react"

import { Caixa, LinhaTexto, Localizacao } from "@/types/localizacao"

type Pdfjs = typeof import("pdfjs-dist")
let pdfjs: Promise<Pdfjs> | null = null

/**
 * O pdf.js só existe no browser e é carregado uma vez: o módulo é pesado e
 * depende de APIs do DOM que o render no servidor não tem. O worker sai do
 * próprio bundle (mesma origem), sem CDN.
 */
function carregarPdfjs(): Promise<Pdfjs> {
  pdfjs ??= import("pdfjs-dist").then((lib) => {
    lib.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString()
    return lib
  })
  return pdfjs
}

/**
 * Trecho a destacar: cada caixa ganha o amarelo de marca-texto por cima do
 * texto. `chave` muda a cada clique, para repetir o mesmo destaque.
 */
export type Destaque = Localizacao & { chave: number }

/**
 * Um controle do botão flutuante, "‹ rótulo ›": passar entre as ocorrências do
 * trecho, ou de um exame (campo) para o seguinte.
 */
export type ControleNavegacao = {
  rotulo: string
  /** Tooltip do rótulo (o nome do exame ou campo). */
  dica?: string
  /** Para leitor de tela: "Ocorrência anterior" / "Próxima ocorrência". */
  rotuloAnterior: string
  rotuloProximo: string
  onAnterior: () => void
  onProximo: () => void
}

type Tamanho = { largura: number; altura: number }

// Folga do marca-texto em volta da caixa, em px: a caixa do Textract encosta no
// texto. Mais larga que alta, como o traço de uma caneta.
const FOLGA_X = 2
const FOLGA_Y = 1
// Acima disso a busca para de listar: termo curto demais casa o documento todo.
const MAX_RESULTADOS = 500

// ---------------------------------------------------------------------------
// Busca no texto
// ---------------------------------------------------------------------------

/** Minúsculas e sem acento, com o índice de cada caractere no texto original. */
function normalizarComMapa(texto: string): { texto: string; mapa: number[] } {
  let saida = ""
  const mapa: number[] = []
  for (let i = 0; i < texto.length; i++) {
    for (const c of texto[i].normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()) {
      saida += c
      mapa.push(i)
    }
  }
  return { texto: saida, mapa }
}

/**
 * Caixa do trecho [inicio, fim) da linha: a união das palavras que ele toca.
 * Sem as caixas das palavras (texto do próprio PDF), estima pela proporção de
 * caracteres. Mesma regra de `layout_ocr.caixa_do_trecho` no back-end.
 */
function caixaDoTrecho(linha: LinhaTexto, inicio: number, fim: number): Caixa {
  const tokens = [...linha.texto.matchAll(/\S+/g)].map((m) => [m.index ?? 0, (m.index ?? 0) + m[0].length])
  const palavras = linha.palavras ?? []
  if (tokens.length && tokens.length === palavras.length) {
    const tocadas = palavras.filter((_, i) => tokens[i][0] < fim && tokens[i][1] > inicio)
    if (tocadas.length) {
      const x0 = Math.min(...tocadas.map((p) => p[0]))
      const x1 = Math.max(...tocadas.map((p) => p[0] + p[1]))
      return { x: x0, y: linha.y, w: x1 - x0, h: linha.h }
    }
  }
  const n = Math.max(linha.texto.length, 1)
  return { x: linha.x + (linha.w * inicio) / n, y: linha.y, w: (linha.w * (fim - inicio)) / n, h: linha.h }
}

/** Texto do próprio PDF (documento digital), quando não há leitura do OCR gravada. */
async function textoDoPdf(documento: PDFDocumentProxy): Promise<LinhaTexto[]> {
  const lib = await carregarPdfjs()
  const linhas: LinhaTexto[] = []
  for (let n = 1; n <= documento.numPages; n++) {
    const pagina = await documento.getPage(n)
    const vp = pagina.getViewport({ scale: 1 })
    const conteudo = await pagina.getTextContent()
    for (const item of conteudo.items) {
      if (!("str" in item) || !item.str.trim()) continue
      const t = lib.Util.transform(vp.transform, item.transform)
      const altura = Math.hypot(t[2], t[3])
      linhas.push({
        pagina: n,
        texto: item.str,
        x: t[4] / vp.width,
        y: (t[5] - altura) / vp.height,
        w: item.width / vp.width,
        h: altura / vp.height,
      })
    }
  }
  return linhas
}

type Resultado = { pagina: number; caixa: Caixa }
type EstadoTexto = "ocioso" | "carregando" | "pronto" | "indisponivel"

// ---------------------------------------------------------------------------

/**
 * Visualizador de PDF da checagem, no lugar do `<iframe>`: o leitor nativo do
 * navegador não deixa rolar até um ponto da página nem desenhar por cima, e é
 * isso que o atalho "clicar no exame e ver onde ele está" precisa.
 *
 * Mesmo visual do leitor de antes: o documento inteiro numa rolagem só, cada
 * página na largura toda, sobre o cinza-escuro do leitor. O trecho destacado
 * ganha amarelo de marca-texto.
 *
 * A busca ("Buscar no documento", também pelo Ctrl+F) procura no texto que o
 * OCR leu, que `carregarTexto` traz com a posição de cada linha: PDF escaneado
 * não tem texto próprio, e a busca do navegador não acha nada nele. Sem essa
 * leitura gravada (documento antigo), procura no texto do próprio PDF, quando
 * ele tem.
 *
 * Recebe os bytes (o `Blob` que a checagem já baixou) e não a URL `blob:`: o
 * pdf.js buscaria a URL com `fetch`, e o CSP de `connect-src` não libera `blob:`.
 * A URL fica para o fallback: se o pdf.js falhar (arquivo que não é PDF, PDF
 * corrompido), cai no `<iframe>` de antes — sem destaque, mas com o documento.
 *
 * Só desenha as páginas perto da área visível e solta o canvas das que saem
 * dela: um prontuário escaneado de 20 páginas desenhado inteiro passaria de
 * 100 MB de memória.
 */
export function VisualizadorPdf({
  arquivo,
  url,
  titulo,
  destaque,
  navegacao,
  carregarTexto,
}: {
  arquivo: Blob | null
  url: string
  titulo: string
  destaque?: Destaque | null
  /** Controles do botão flutuante; vazio, o botão não aparece. */
  navegacao?: ControleNavegacao[]
  /** Texto do OCR com a posição de cada linha; null quando não há. */
  carregarTexto?: () => Promise<LinhaTexto[] | null>
}) {
  // Estado, e não ref: o observador de largura precisa saber quando a área
  // aparece (ela não existe enquanto o fallback do `<iframe>` está na tela).
  const [raiz, setRaiz] = useState<HTMLDivElement | null>(null)
  const [documento, setDocumento] = useState<PDFDocumentProxy | null>(null)
  const [paginas, setPaginas] = useState<Tamanho[]>([])
  const [largura, setLargura] = useState(0)
  const [falhou, setFalhou] = useState(false)

  const campoBusca = useRef<HTMLInputElement>(null)
  const carregarTextoRef = useRef(carregarTexto)
  carregarTextoRef.current = carregarTexto
  const [busca, setBusca] = useState("")
  const [estadoTexto, setEstadoTexto] = useState<EstadoTexto>("ocioso")
  const [linhasTexto, setLinhasTexto] = useState<LinhaTexto[]>([])
  const [atual, setAtual] = useState(0)

  useEffect(() => {
    if (!arquivo) return
    let cancelado = false
    let tarefa: PDFDocumentLoadingTask | null = null
    setDocumento(null)
    setPaginas([])
    setFalhou(false)
    setBusca("")
    setEstadoTexto("ocioso")
    setLinhasTexto([])
    ;(async () => {
      try {
        const lib = await carregarPdfjs()
        const dados = new Uint8Array(await arquivo.arrayBuffer())
        if (cancelado) return
        // Sem `eval`: o CSP de produção não tem 'unsafe-eval'. `verbosity: 0`
        // cala os avisos de JPEG malformado, comuns em scan e inofensivos.
        tarefa = lib.getDocument({ data: dados, isEvalSupported: false, verbosity: 0 })
        const pdf = await tarefa.promise
        const tamanhos: Tamanho[] = []
        for (let n = 1; n <= pdf.numPages; n++) {
          const vp = (await pdf.getPage(n)).getViewport({ scale: 1 })
          tamanhos.push({ largura: vp.width, altura: vp.height })
        }
        if (cancelado) return
        setPaginas(tamanhos)
        setDocumento(pdf)
      } catch (erro) {
        const mensagem = erro instanceof Error ? erro.message : String(erro)
        // Em dev o StrictMode monta o efeito duas vezes, e o destroy da primeira
        // rejeita com "Loading aborted": cancelamento esperado, não falha.
        if (cancelado || /loading aborted/i.test(mensagem)) return
        console.error("[PDF] Falha ao abrir o documento no visualizador", erro)
        setFalhou(true)
      }
    })()
    return () => {
      cancelado = true
      void tarefa?.destroy()
    }
  }, [arquivo])

  useEffect(() => {
    if (!raiz) return
    const medir = () => setLargura(Math.max(320, raiz.clientWidth - 8))
    medir()
    const observador = new ResizeObserver(medir)
    observador.observe(raiz)
    return () => observador.disconnect()
  }, [raiz])

  // Uma escala para todas as páginas: a mais larga ocupa a largura toda.
  const escala = useMemo(() => {
    const maisLarga = Math.max(0, ...paginas.map((p) => p.largura))
    return maisLarga && largura ? largura / maisLarga : 0
  }, [paginas, largura])

  // Leva o ponto `y` (fração da página) ao terço de cima da área visível. Salto
  // longo vai direto — rolar suave por várias páginas desenharia cada uma delas
  // no caminho e atrasaria a que importa.
  const rolarAte = useCallback(
    (numero: number, y: number) => {
      if (!raiz) return
      const pagina = raiz.querySelector<HTMLElement>(`[data-pagina="${numero}"]`)
      if (!pagina) return
      const top = Math.max(0, pagina.offsetTop + y * pagina.offsetHeight - raiz.clientHeight * 0.28)
      raiz.scrollTo({
        top,
        behavior: Math.abs(top - raiz.scrollTop) > raiz.clientHeight * 1.5 ? "instant" : "smooth",
      })
    },
    [raiz],
  )

  useEffect(() => {
    if (!destaque || !documento || !escala) return
    rolarAte(destaque.pagina, Math.min(...destaque.caixas.map((c) => c.y)))
  }, [destaque, documento, escala, rolarAte])

  // A leitura do OCR só é buscada quando o revisor começa a procurar.
  const prepararTexto = useCallback(async () => {
    if (estadoTexto !== "ocioso" || !documento) return
    setEstadoTexto("carregando")
    try {
      let linhas = (await carregarTextoRef.current?.().catch(() => null)) ?? null
      if (!linhas?.length) linhas = await textoDoPdf(documento)
      setLinhasTexto(linhas)
      setEstadoTexto(linhas.length ? "pronto" : "indisponivel")
    } catch (erro) {
      console.error("[PDF] Falha ao preparar a busca", erro)
      setEstadoTexto("indisponivel")
    }
  }, [estadoTexto, documento])

  const termo = useMemo(() => normalizarComMapa(busca.trim().replace(/\s+/g, " ")).texto, [busca])
  const resultados = useMemo<Resultado[]>(() => {
    if (termo.length < 2) return []
    const achados: Resultado[] = []
    for (const linha of linhasTexto) {
      const { texto, mapa } = normalizarComMapa(linha.texto)
      for (let i = texto.indexOf(termo); i >= 0 && achados.length < MAX_RESULTADOS; i = texto.indexOf(termo, i + 1)) {
        achados.push({ pagina: linha.pagina, caixa: caixaDoTrecho(linha, mapa[i], mapa[i + termo.length - 1] + 1) })
      }
    }
    // Ordem de leitura: página, depois de cima para baixo.
    return achados.sort((a, b) => a.pagina - b.pagina || a.caixa.y - b.caixa.y || a.caixa.x - b.caixa.x)
  }, [termo, linhasTexto])

  useEffect(() => setAtual(0), [resultados])

  const resultadoAtual = resultados[atual]
  useEffect(() => {
    if (resultadoAtual && escala) rolarAte(resultadoAtual.pagina, resultadoAtual.caixa.y)
  }, [resultadoAtual, escala, rolarAte])

  const irPara = (delta: number) => {
    if (resultados.length) setAtual((i) => (i + delta + resultados.length) % resultados.length)
  }

  // Ctrl+F abre esta busca: a do navegador não acha nada no PDF desenhado.
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        e.preventDefault()
        campoBusca.current?.focus()
        campoBusca.current?.select()
      }
    }
    window.addEventListener("keydown", aoTeclar)
    return () => window.removeEventListener("keydown", aoTeclar)
  }, [])

  if (falhou || !arquivo) {
    return <iframe title={titulo} src={`${url}#toolbar=0&navpanes=0&scrollbar=0`} className="h-full w-full" />
  }

  const situacaoBusca =
    estadoTexto === "carregando"
      ? "Lendo…"
      : estadoTexto === "indisponivel"
        ? "Sem texto para buscar"
        : termo.length < 2
          ? ""
          : resultados.length
            ? `${atual + 1} de ${resultados.length}${resultados.length === MAX_RESULTADOS ? "+" : ""}`
            : "Nenhum resultado"

  return (
    <div ref={setRaiz} className="relative h-full overflow-auto bg-[#525659]" aria-label={titulo}>
      {documento && (
        // Altura zero: a caixa flutua sobre as páginas sem empurrá-las para baixo.
        <div className="sticky top-0 z-30 h-0">
          <div className="absolute right-3 top-2 flex items-center gap-1 rounded-md border bg-white/95 py-1 pl-2 pr-1 text-xs shadow-md">
            <SearchIcon className="size-3.5 shrink-0 text-muted-foreground" />
            <input
              ref={campoBusca}
              value={busca}
              onChange={(e) => {
                setBusca(e.target.value)
                void prepararTexto()
              }}
              onFocus={() => void prepararTexto()}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  irPara(e.shiftKey ? -1 : 1)
                }
              }}
              placeholder="Buscar no documento"
              aria-label="Buscar no documento"
              className="w-40 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            {situacaoBusca && <span className="whitespace-nowrap px-1 tabular-nums text-muted-foreground">{situacaoBusca}</span>}
            <button
              type="button"
              onClick={() => irPara(-1)}
              disabled={!resultados.length}
              className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
              aria-label="Resultado anterior"
            >
              <ChevronUpIcon className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => irPara(1)}
              disabled={!resultados.length}
              className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
              aria-label="Próximo resultado"
            >
              <ChevronDownIcon className="size-4" />
            </button>
            {busca && (
              <button
                type="button"
                onClick={() => setBusca("")}
                className="rounded p-0.5 hover:bg-muted"
                aria-label="Limpar busca"
              >
                <XIcon className="size-4" />
              </button>
            )}
          </div>
        </div>
      )}
      {!documento || !escala ? (
        <div className="grid h-full place-items-center text-sm text-white/80">
          <div className="flex items-center gap-2">
            <Loader2Icon className="size-4 animate-spin" />
            Carregando documento...
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-1 py-1">
          {paginas.map((tamanho, i) => (
            <PaginaPdf key={i} documento={documento} numero={i + 1} escala={escala} tamanho={tamanho} raiz={raiz}>
              {destaque?.pagina === i + 1 &&
                destaque.caixas.map((c, j) => (
                  <MarcaTexto key={`d-${destaque.chave}-${j}`} caixa={c} forte />
                ))}
              {resultados.map((r, j) =>
                r.pagina === i + 1 ? (
                  <MarcaTexto key={`b-${j}`} caixa={r.caixa} forte={j === atual} />
                ) : null,
              )}
            </PaginaPdf>
          ))}
        </div>
      )}
      {documento && !!navegacao?.length && (
        <div className="sticky bottom-3 z-30 mx-auto flex w-fit items-center gap-1 rounded-md bg-slate-900/85 p-1 text-xs tabular-nums text-white shadow-lg">
          {navegacao.map((controle, i) => (
            <div key={controle.rotuloProximo} className={`flex items-center gap-1 ${i ? "border-l border-white/20 pl-1" : ""}`}>
              <button
                type="button"
                onClick={controle.onAnterior}
                className="rounded p-1 hover:bg-white/15"
                aria-label={controle.rotuloAnterior}
              >
                <ChevronLeftIcon className="size-4" />
              </button>
              <span className="max-w-56 truncate px-2 text-center" title={controle.dica ?? controle.rotulo}>
                {controle.rotulo}
              </span>
              <button
                type="button"
                onClick={controle.onProximo}
                className="rounded p-1 hover:bg-white/15"
                aria-label={controle.rotuloProximo}
              >
                <ChevronRightIcon className="size-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Amarelo de marca-texto sobre o trecho. O `mix-blend-multiply` tinge o papel
 * e deixa a tinta escura por baixo, como uma caneta — e não uma caixa por cima
 * do texto. `forte` para o trecho atual; o fraco marca os demais resultados da
 * busca.
 */
function MarcaTexto({ caixa, forte = false }: { caixa: Caixa; forte?: boolean }) {
  return (
    <div
      className={`pointer-events-none absolute rounded-[2px] mix-blend-multiply ${forte ? "bg-yellow-300/80" : "bg-yellow-200/50"}`}
      style={{
        top: `calc(${caixa.y * 100}% - ${FOLGA_Y}px)`,
        left: `calc(${caixa.x * 100}% - ${FOLGA_X}px)`,
        width: `calc(${caixa.w * 100}% + ${2 * FOLGA_X}px)`,
        height: `calc(${caixa.h * 100}% + ${2 * FOLGA_Y}px)`,
      }}
    />
  )
}

function PaginaPdf({
  documento,
  numero,
  escala,
  tamanho,
  raiz,
  children,
}: {
  documento: PDFDocumentProxy
  numero: number
  escala: number
  tamanho: Tamanho
  raiz: HTMLElement | null
  children?: ReactNode
}) {
  const moldura = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [perto, setPerto] = useState(false)

  useEffect(() => {
    const el = moldura.current
    if (!el || !raiz) return
    // "Perto" = até uma tela e meia acima ou abaixo da área visível.
    const observador = new IntersectionObserver(([e]) => setPerto(e.isIntersecting), {
      root: raiz,
      rootMargin: "150% 0px",
    })
    observador.observe(el)
    return () => observador.disconnect()
  }, [raiz])

  useEffect(() => {
    const c = canvas.current
    if (!c) return
    if (!perto) {
      // Solta a memória do bitmap.
      c.width = 0
      c.height = 0
      return
    }
    let ativo = true
    let tarefa: RenderTask | null = null
    documento
      .getPage(numero)
      .then((pagina) => {
        if (!ativo) return
        const densidade = Math.min(window.devicePixelRatio || 1, 2)
        const vp = pagina.getViewport({ scale: escala * densidade })
        c.width = Math.floor(vp.width)
        c.height = Math.floor(vp.height)
        const contexto = c.getContext("2d")
        if (!contexto) return
        tarefa = pagina.render({ canvasContext: contexto, viewport: vp })
        return tarefa.promise
      })
      .catch(() => {
        // Render cancelado (a página saiu da tela ou a largura mudou): nada a fazer.
      })
    return () => {
      ativo = false
      tarefa?.cancel()
    }
  }, [documento, numero, escala, perto])

  return (
    <div
      ref={moldura}
      data-pagina={numero}
      className="relative shrink-0 bg-white"
      style={{ width: tamanho.largura * escala, height: tamanho.altura * escala }}
    >
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      {children}
    </div>
  )
}
