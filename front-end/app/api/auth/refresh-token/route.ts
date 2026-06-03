import { NextRequest, NextResponse } from "next/server"
import { getToken, encode } from "next-auth/jwt"
import { API_URL } from "@/lib/config"

const useSecureCookies = process.env.NEXTAUTH_URL?.startsWith("https://") ?? process.env.NODE_ENV === "production"
const COOKIE_NAME = useSecureCookies ? "__Secure-next-auth.session-token" : "next-auth.session-token"
const SESSION_MAX_AGE = Number(process.env.NEXTAUTH_SESSION_MAX_AGE || 60 * 60 * 8)

export async function POST(request: NextRequest) {
  const token = await getToken({ req: request, secret: process.env.NEXTAUTH_SECRET })

  if (!token?.refreshToken) {
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
    res.cookies.set(COOKIE_NAME, encoded, {
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
