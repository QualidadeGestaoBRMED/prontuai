import { NextResponse } from "next/server"

import { API_URL } from "@/lib/config"

export const runtime = "nodejs"
// Impede que o handler seja pré-renderizado no build (congelaria o status).
// O cache vem do header Cache-Control explícito abaixo, não da inferência do
// Next: como o header é definido na resposta, o Next não o sobrescreve.
export const dynamic = "force-dynamic"

// A resposta é idêntica para todos os navegadores, então é cacheada na CDN:
// os polls de todas as abas colapsam em ~1 invocação por minuto em vez de uma
// por aba. A latência de propagação (60s) é a mesma que o intervalo de poll do
// MaintenanceWrapper já tinha, e o stale-while-revalidate evita que a
// revalidação apareça como latência para o usuário.
const CACHE_CONTROL = "public, s-maxage=60, stale-while-revalidate=300"

const EMPTY_STATUS = { status: "none", message: "", eta: "" }

export async function GET() {
  try {
    const response = await fetch(`${API_URL}/v1/maintenance/status`, {
      cache: "no-store",
    })
    if (!response.ok) {
      // Falha do backend não é cacheada: a próxima requisição tenta de novo.
      return NextResponse.json(EMPTY_STATUS, {
        status: 200,
        headers: { "Cache-Control": "no-store" },
      })
    }
    const payload = await response.json()
    return NextResponse.json(payload, {
      status: 200,
      headers: { "Cache-Control": CACHE_CONTROL },
    })
  } catch {
    return NextResponse.json(EMPTY_STATUS, {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    })
  }
}
