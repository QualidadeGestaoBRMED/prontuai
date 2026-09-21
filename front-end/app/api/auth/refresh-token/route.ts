import { NextRequest, NextResponse } from "next/server"
import { getToken, encode } from "next-auth/jwt"
import { API_URL } from "@/lib/config"
import {
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE,
  sessionTokenParams,
  useSecureCookies,
} from "@/lib/session-cookie"

export async function POST(request: NextRequest) {
  const token = await getToken({ req: request, ...sessionTokenParams })

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
