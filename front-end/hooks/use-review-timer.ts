"use client"

// Cronômetro da tela de revisão, com ciclo de vida colado no da página.
//
// Os listeners são religados no próximo abrir(), então o duplo mount do
// StrictMode em dev (que dispara o destruir do primeiro ciclo) não deixa o
// cronômetro morto.

import { useEffect, useRef } from "react"
import { criarCronometroRevisao, type CronometroRevisao } from "@/lib/review-timer"

export function useReviewTimer(): CronometroRevisao {
  const ref = useRef<CronometroRevisao | null>(null)
  if (ref.current === null) {
    ref.current = criarCronometroRevisao()
  }
  const cronometro = ref.current

  useEffect(() => {
    return () => cronometro.destruir()
  }, [cronometro])

  return cronometro
}
