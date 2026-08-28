// Cronômetro da tela de revisão — desenho em docs/tempo-de-revisao-desenho.md.
//
// Mede o tempo entre abrir o modal de checagem de um documento e confirmar a
// decisão. O resultado viaja no PATCH que já é feito na decisão: nada é exibido
// ao revisor e nenhuma requisição nova é criada.
//
// Duas restrições do ambiente moldam o desenho da regra de ocioso:
//
// 1. O PDF é renderizado num <iframe> pelo viewer nativo do Chrome, e rolagem
//    ou clique lá dentro NÃO geram evento no documento pai. Detector de ocioso
//    por mousemove classificaria "lendo o prontuário" como ocioso — justamente
//    o trabalho que queremos medir. Por isso o timeout de ocioso só vale
//    enquanto o foco está FORA do iframe.
// 2. Aba visível não é o mesmo que janela em uso: alt-tab para outro programa
//    mantém visibilityState === "visible". Daí o document.hasFocus() junto do
//    visibilitychange.
//
// As durações vêm de performance.now() (monotônico): imunes a skew e a ajuste
// de hora do cliente. Só started_at é relógio de parede, e serve apenas para
// derivar o tempo de fila contra o uploaded_at.

export type ReviewTiming = {
  started_at: string
  active_ms: number
  wall_ms: number
  open_count: number
}

// Sem sinal de atividade e com o foco fora do PDF, o trecho é fechado no
// instante da última atividade: a janela ociosa é descontada, não creditada.
export const TIMEOUT_OCIOSO_MS = 10 * 60_000
// Graça para quem abre o PDF em aba separada: a aba da revisão fica oculta,
// mas a pessoa está lendo o documento.
export const TETO_PDF_EXTERNO_MS = 5 * 60_000
// Teto duro por abertura. Acima disso não é revisão longa, é aba esquecida.
export const TETO_SESSAO_MS = 60 * 60_000
// Ocioso não gera evento, então a expiração precisa de um tique.
const INTERVALO_TIQUE_MS = 5_000
// Rolagem dispara por quadro; sem isto o sincronizar rodaria centenas de vezes.
const THROTTLE_ATIVIDADE_MS = 500
// review_open_count é SMALLINT no banco e o servidor também limita.
const MAX_ABERTURAS = 255

type Acumulador = {
  startedAt: string
  ativoMs: number
  paredeMs: number
  aberturas: number
  paredeInicio: number | null
  ativoInicio: number | null
  ultimaAtividade: number
  pdfExternoAte: number | null
}

export type CronometroRevisao = {
  /** Tela de revisão aberta. Reabrir o mesmo documento soma ao acumulado. */
  abrir: (documentId: string) => void
  /** Tela fechada sem decisão: mantém o acumulado para uma reabertura. */
  fechar: (documentId: string) => void
  /** Clique em "Abrir em nova aba": a aba oculta não pausa por um tempo. */
  registrarPdfExterno: (documentId: string) => void
  /** Decisão confirmada: fecha, descarta o acumulador e devolve a medição. */
  encerrar: (documentId: string) => ReviewTiming | null
  destruir: () => void
}

const NOOP: CronometroRevisao = {
  abrir: () => {},
  fechar: () => {},
  registrarPdfExterno: () => {},
  encerrar: () => null,
  destruir: () => {},
}

export function criarCronometroRevisao(): CronometroRevisao {
  // SSR e ambientes sem performance: no-op. O PATCH sai sem cronometragem e a
  // revisão segue idêntica — medir nunca pode bloquear decidir.
  if (typeof document === "undefined" || typeof performance === "undefined") {
    return NOOP
  }

  const acumuladores = new Map<string, Acumulador>()
  let atual: string | null = null
  let tique: number | null = null
  let listenersAtivos = false

  const agora = () => performance.now()

  const accAtual = () => (atual ? acumuladores.get(atual) : undefined)

  // Foco dentro do viewer de PDF. O único iframe da tela de revisão é o preview
  // do documento, então checar a tag basta.
  const focoNoPdf = () => document.activeElement?.tagName === "IFRAME"

  const ocultoOuSemFoco = () =>
    document.visibilityState !== "visible" || !document.hasFocus()

  const emUso = (t: number, acc: Acumulador) => {
    if (acc.paredeInicio !== null && t - acc.paredeInicio >= TETO_SESSAO_MS) return false
    if (ocultoOuSemFoco()) {
      return acc.pdfExternoAte !== null && t < acc.pdfExternoAte
    }
    if (focoNoPdf()) return true
    return t - acc.ultimaAtividade < TIMEOUT_OCIOSO_MS
  }

  // Espelha emUso: cada motivo de parar de contar tem o seu instante de corte.
  const fimDoTrecho = (t: number, acc: Acumulador) => {
    if (acc.paredeInicio !== null && t - acc.paredeInicio >= TETO_SESSAO_MS) {
      return acc.paredeInicio + TETO_SESSAO_MS
    }
    if (ocultoOuSemFoco()) return t
    // Sobrou o ocioso: o trecho termina onde a atividade parou.
    return acc.ultimaAtividade
  }

  const encerrarTrechoAtivo = (t: number, acc: Acumulador) => {
    if (acc.ativoInicio === null) return
    const fim = Math.min(t, Math.max(fimDoTrecho(t, acc), acc.ativoInicio))
    acc.ativoMs += fim - acc.ativoInicio
    acc.ativoInicio = null
  }

  const sincronizar = (t: number) => {
    const acc = accAtual()
    if (!acc) return
    if (!ocultoOuSemFoco()) acc.pdfExternoAte = null
    if (emUso(t, acc)) {
      if (acc.ativoInicio === null) acc.ativoInicio = t
    } else {
      encerrarTrechoAtivo(t, acc)
    }
  }

  const onAtividade = () => {
    const acc = accAtual()
    if (!acc) return
    const t = agora()
    if (acc.ativoInicio !== null && t - acc.ultimaAtividade < THROTTLE_ATIVIDADE_MS) {
      acc.ultimaAtividade = t
      return
    }
    acc.ultimaAtividade = t
    sincronizar(t)
  }

  const onEstado = () => sincronizar(agora())

  const eventosAtividade = ["pointerdown", "keydown", "wheel", "scroll"] as const

  const garantirListeners = () => {
    if (listenersAtivos) return
    document.addEventListener("visibilitychange", onEstado)
    window.addEventListener("focus", onEstado)
    window.addEventListener("blur", onEstado)
    for (const evento of eventosAtividade) {
      document.addEventListener(evento, onAtividade, { capture: true, passive: true })
    }
    listenersAtivos = true
  }

  const removerListeners = () => {
    if (!listenersAtivos) return
    document.removeEventListener("visibilitychange", onEstado)
    window.removeEventListener("focus", onEstado)
    window.removeEventListener("blur", onEstado)
    for (const evento of eventosAtividade) {
      document.removeEventListener(evento, onAtividade, { capture: true })
    }
    listenersAtivos = false
  }

  const pararTique = () => {
    if (tique !== null) {
      window.clearInterval(tique)
      tique = null
    }
  }

  const iniciarTique = () => {
    if (tique !== null) return
    tique = window.setInterval(() => sincronizar(agora()), INTERVALO_TIQUE_MS)
  }

  const fecharSessao = (acc: Acumulador, t: number) => {
    encerrarTrechoAtivo(t, acc)
    if (acc.paredeInicio !== null) {
      acc.paredeMs += Math.min(t - acc.paredeInicio, TETO_SESSAO_MS)
      acc.paredeInicio = null
    }
    acc.pdfExternoAte = null
  }

  const fechar = (documentId: string) => {
    const acc = acumuladores.get(documentId)
    if (acc) fecharSessao(acc, agora())
    if (atual === documentId) {
      atual = null
      pararTique()
    }
  }

  const abrir = (documentId: string) => {
    // Defensivo: a UI abre um modal por vez, mas se aparecer outro caminho o
    // documento anterior não pode ficar com o cronômetro correndo.
    if (atual !== null && atual !== documentId) fechar(atual)

    const t = agora()
    let acc = acumuladores.get(documentId)
    if (!acc) {
      acc = {
        startedAt: new Date().toISOString(),
        ativoMs: 0,
        paredeMs: 0,
        aberturas: 0,
        paredeInicio: null,
        ativoInicio: null,
        ultimaAtividade: t,
        pdfExternoAte: null,
      }
      acumuladores.set(documentId, acc)
    }
    acc.aberturas += 1
    acc.paredeInicio = t
    acc.ultimaAtividade = t
    acc.pdfExternoAte = null
    atual = documentId

    garantirListeners()
    sincronizar(t)
    iniciarTique()
  }

  const registrarPdfExterno = (documentId: string) => {
    const acc = acumuladores.get(documentId)
    if (!acc) return
    acc.pdfExternoAte = agora() + TETO_PDF_EXTERNO_MS
  }

  const encerrar = (documentId: string): ReviewTiming | null => {
    const acc = acumuladores.get(documentId)
    if (!acc) return null
    fecharSessao(acc, agora())
    acumuladores.delete(documentId)
    if (atual === documentId) {
      atual = null
      pararTique()
    }
    const wall = Math.round(acc.paredeMs)
    if (wall <= 0) return null
    return {
      started_at: acc.startedAt,
      active_ms: Math.min(Math.round(acc.ativoMs), wall),
      wall_ms: wall,
      open_count: Math.min(acc.aberturas, MAX_ABERTURAS),
    }
  }

  const destruir = () => {
    pararTique()
    removerListeners()
    acumuladores.clear()
    atual = null
  }

  return { abrir, fechar, registrarPdfExterno, encerrar, destruir }
}
