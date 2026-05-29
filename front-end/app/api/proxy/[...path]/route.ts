import { NextRequest, NextResponse } from "next/server"
import { getToken } from "next-auth/jwt"
import { API_URL } from "@/lib/config"

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
])

function buildUpstreamUrl(request: NextRequest, path: string[]): URL {
  const normalizedPath = path.join("/")
  const upstream = new URL(`${API_URL}/${normalizedPath}`)
  upstream.search = request.nextUrl.search
  return upstream
}

function buildForwardHeaders(request: NextRequest, bearerToken?: string): Headers {
  const headers = new Headers()

  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase()
    if (HOP_BY_HOP_HEADERS.has(lower)) return
    if (lower === "host" || lower === "content-length" || lower === "cookie") return
    if (lower === "accept-encoding") return
    if (lower === "authorization") return
    headers.set(key, value)
  })

  if (bearerToken) {
    headers.set("Authorization", `Bearer ${bearerToken}`)
  }

  return headers
}

async function buildUpstreamBody(request: NextRequest): Promise<BodyInit | undefined> {
  if (request.method === "GET" || request.method === "HEAD") {
    return undefined
  }

  const hasTransferEncoding = request.headers.has("transfer-encoding")
  const contentLength = request.headers.get("content-length")
  const hasBodyByLength = contentLength !== null && contentLength !== "0"

  if (!hasTransferEncoding && !hasBodyByLength) {
    return undefined
  }

  const payload = await request.arrayBuffer()
  if (payload.byteLength === 0) {
    return undefined
  }

  return payload
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  if (!path || path.length === 0) {
    return NextResponse.json({ detail: "Proxy path inválido." }, { status: 400 })
  }

  const token = await getToken({ req: request, secret: process.env.NEXTAUTH_SECRET })
  const bearerToken = typeof token?.accessToken === "string" ? token.accessToken : undefined
  const devBypassEnabled = process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true"
  if (!bearerToken && !devBypassEnabled) {
    return NextResponse.json(
      {
        detail:
          "Sessão sem token de acesso. Faça login novamente para enviar requisições autenticadas.",
      },
      { status: 401 }
    )
  }

  const upstreamUrl = buildUpstreamUrl(request, path)
  const headers = buildForwardHeaders(request, bearerToken)
  const body = await buildUpstreamBody(request)

  const upstreamInit: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  }
  if (body !== undefined) {
    upstreamInit.body = body
  }

  let upstreamResponse: Response
  try {
    upstreamResponse = await fetch(upstreamUrl, upstreamInit)
  } catch {
    return NextResponse.json(
      { detail: "Falha ao encaminhar requisição para o backend." },
      { status: 502 }
    )
  }

  const responseHeaders = new Headers(upstreamResponse.headers)
  HOP_BY_HOP_HEADERS.forEach((header) => responseHeaders.delete(header))
  // Evita incompatibilidade entre corpo já descomprimido pelo runtime e headers de compressão.
  responseHeaders.delete("content-encoding")
  responseHeaders.delete("content-length")

  return new NextResponse(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  })
}

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
export const OPTIONS = proxy
