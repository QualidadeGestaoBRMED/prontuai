"use client"

/**
 * Última sessão conhecida, alimentada pelo `AuthGuard` em `components/providers.tsx`.
 *
 * Quando o cookie de sessão vence, o navegador para de enviá-lo e o servidor
 * deixa de saber de quem era a sessão — mas a aba que ficou aberta ainda tem o
 * usuário em memória no React. É daí que sai o "quem" no aviso de sessão
 * perdida; sem isto o aviso chega ao back-end sem identificar ninguém.
 */
let sessaoConhecida: { email?: string; iat?: number } = {}

/**
 * Motivo pelo qual a sessão morreu, ou `null` enquanto ela estiver viva.
 *
 * Serve de trava: o proxy (`app/api/proxy/[...path]/route.ts`) devolve 401
 * localmente enquanto o cookie estiver morto, sem chegar ao back-end. Sem esta
 * trava cada requisição repetia a renovação e gerava mais um aviso idêntico —
 * foram 6.041 avisos em duas horas, para algumas dezenas de sessões.
 */
let sessaoMorta: string | null = null

export function registrarSessaoConhecida(sessao: { email?: string; iat?: number }) {
  // Nunca apagar. Quando o cookie morre, o `useSession` passa a devolver null;
  // sobrescrever aqui descartava o e-mail exatamente no instante em que ele
  // vira a única pista de quem foi deslogado.
  if (!sessao.email) return
  sessaoConhecida = sessao
  sessaoMorta = null
}

let refreshPromise: Promise<string | null> | null = null

/** Resolve com `null` quando renovou, ou com o código do motivo quando não. */
async function tryRefresh(url: string): Promise<string | null> {
  if (refreshPromise) return refreshPromise
  refreshPromise = fetch("/api/auth/refresh-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...sessaoConhecida, url }),
  })
    .then(async (r) => {
      if (r.ok) {
        sessaoMorta = null
        return null
      }
      // O motivo vinha sendo descartado por um `.then((r) => r.ok)`: quatro
      // desfechos diferentes viravam o mesmo "Sessão expirada" e não dava para
      // separar cookie vencido de back-end fora do ar na hora de investigar.
      const corpo = (await r.json().catch(() => ({}))) as { error?: string }
      return corpo.error ?? "refresh_failed"
    })
    .catch(() => "refresh_error")
    .finally(() => {
      refreshPromise = null
    })
  return refreshPromise
}

export async function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)
  if (response.status !== 401) return response

  const url = typeof input === "string" ? input : input.toString()
  let motivo = sessaoMorta

  if (motivo === null) {
    motivo = await tryRefresh(url)

    if (motivo === null) {
      const retry = await fetch(input, init)
      if (retry.status !== 401) return retry
      // Renovou e mesmo assim 401: o problema é permissão neste recurso, não a
      // sessão. O logout continua como era, mas com motivo próprio — antes isto
      // se misturava com sessão expirada e sumia no meio dos outros casos.
      // Não marca a sessão como morta: ela está viva.
      motivo = "retry_ainda_401"
    } else {
      sessaoMorta = motivo
    }
  }

  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("auth:unauthorized", { detail: { url, motivo } }),
    )
  }

  return response
}
