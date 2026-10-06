import { NextRequest, NextResponse } from "next/server"
import { getToken, encode } from "next-auth/jwt"
import { API_URL } from "@/lib/config"
import {
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE,
  sessionTokenParams,
  useSecureCookies,
} from "@/lib/session-cookie"

/**
 * Avisa o back-end que uma sessão morreu aqui, sem chegar ao `/v1/auth/refresh`.
 *
 * Este era o único desfecho de autenticação sem rastro: o 401 saía daqui
 * mesmo, o usuário lia "Sessão expirada" e não ficava registro de quem tinha
 * sido deslogado nem por quê.
 *
 * `cookie_ausente` (o navegador descartou o cookie ao fim do `maxAge`) e
 * `cookie_sem_refresh` (o cookie veio, mas sem refresh token dentro) são causas
 * distintas, com correções distintas, e só dá para separá-las deste lado.
 *
 * Observabilidade não pode derrubar o logout: qualquer falha aqui é engolida e
 * o 401 segue normalmente.
 */
async function avisarSessaoPerdida(request: NextRequest) {
  const dica = (await request.json().catch(() => ({}))) as {
    email?: string
    iat?: number
    url?: string
  }
  try {
    await fetch(`${API_URL}/v1/auth/session-lost`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        motivo: request.cookies.has(SESSION_COOKIE_NAME)
          ? "cookie_sem_refresh"
          : "cookie_ausente",
        email: dica.email ?? null,
        sessao_iniciada_em: dica.iat ?? null,
        url: dica.url ?? null,
      }),
      signal: AbortSignal.timeout(2000),
    })
  } catch {
    // Back-end fora do ar ou lento: o usuário sai do mesmo jeito.
  }
}

export async function POST(request: NextRequest) {
  const token = await getToken({ req: request, ...sessionTokenParams })

  if (!token?.refreshToken) {
    await avisarSessaoPerdida(request)
    return NextResponse.json({ error: "no_refresh_token" }, { status: 401 })
  }

  try {
    const backendRes = await fetch(`${API_URL}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token.refreshToken }),
    })

    if (!backendRes.ok) {
      return NextResponse.json({ error: "refresh_failed" }, { status: 401 })
    }

    const data = await backendRes.json()

    const newToken = {
      ...token,
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
    }

    const encoded = await encode({
      token: newToken,
      secret: process.env.NEXTAUTH_SECRET!,
      maxAge: SESSION_MAX_AGE,
    })

    const res = NextResponse.json({ ok: true })
    res.cookies.set(SESSION_COOKIE_NAME, encoded, {
      httpOnly: true,
      secure: useSecureCookies,
      sameSite: "lax",
      maxAge: SESSION_MAX_AGE,
      path: "/",
    })
    return res
  } catch {
    return NextResponse.json({ error: "refresh_error" }, { status: 500 })
  }
}
