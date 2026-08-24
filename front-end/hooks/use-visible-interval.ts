"use client"

// Polling que só roda com a aba visível.
//
// Motivação: cada request do cliente atravessa /api/proxy (uma Vercel Function
// que faz fetch no backend), então um poll custa 3 Observability Events na
// Vercel — edge request + function invocation + external API request. Abas
// abandonadas em background queimavam essa cota sem ninguém olhando.
//
// Ao voltar para a aba, dispara um fetch imediato: o usuário vê dados mais
// frescos do que veria com o setInterval cru, que poderia estar no meio do
// intervalo.

import { useEffect, useRef } from "react"

export function useVisibleInterval(
  callback: () => void,
  intervalMs: number,
  enabled = true,
) {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return
    if (typeof document === "undefined") return

    let interval: number | null = null

    const stop = () => {
      if (interval !== null) {
        window.clearInterval(interval)
        interval = null
      }
    }

    const start = () => {
      if (interval !== null) return
      interval = window.setInterval(() => callbackRef.current(), intervalMs)
    }

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        // Refetch imediato: a aba pode ter ficado horas oculta.
        callbackRef.current()
        start()
      } else {
        stop()
      }
    }

    if (document.visibilityState === "visible") {
      start()
    }
    document.addEventListener("visibilitychange", onVisibilityChange)

    return () => {
      stop()
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [enabled, intervalMs])
}
