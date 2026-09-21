import { NextRequest, NextResponse } from "next/server"
import { getToken } from "next-auth/jwt"
import { API_URL } from "@/lib/config"
import { sessionTokenParams } from "@/lib/session-cookie"

/**
 * Revoga a sessão de refresh no back-end antes do `signOut` do NextAuth.
 *
 * O `signOut` sozinho só apaga o cookie do browser: o refresh token seguia
 * válido no banco pelos 30 dias da família, e quem tivesse uma cópia dele
 * continuava emitindo access tokens depois do logout. O endpoint
 * `/v1/auth/logout` do back-end já existia e revoga a família inteira; faltava
 * alguém chamá-lo.
 *
 * O refresh token vive só no cookie HttpOnly, então essa chamada tem de sair
 * daqui (server-side) — o cliente não tem como fazê-la.
 */
export async function POST(request: NextRequest) {
  const token = await getToken({ req: request, ...sessionTokenParams })

  if (!token?.refreshToken) {
    // Sem sessão para revogar; o `signOut` do cliente ainda limpa o cookie.
    return NextResponse.json({ ok: true, revoked: false })
  }

  try {
    const backendRes = await fetch(`${API_URL}/v1/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token.refreshToken }),
    })
    // Falha aqui não pode impedir o logout local: o usuário sai de qualquer
    // jeito, e o pior caso é o refresh token expirar sozinho.
    return NextResponse.json({ ok: true, revoked: backendRes.ok })
  } catch {
    return NextResponse.json({ ok: true, revoked: false })
  }
}
