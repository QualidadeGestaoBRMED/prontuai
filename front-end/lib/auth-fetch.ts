"use client"

import { getSession, signOut } from "next-auth/react"

const hasAuthorizationHeader = (headers?: HeadersInit): boolean => {
  if (!headers) return false
  if (headers instanceof Headers) {
    return headers.has("authorization") || headers.has("Authorization")
  }
  if (Array.isArray(headers)) {
    return headers.some(([key]) => key.toLowerCase() === "authorization")
  }
  return Object.keys(headers).some((key) => key.toLowerCase() === "authorization")
}

let signOutInProgress = false
let refreshInProgress: Promise<string | null> | null = null

const getAuthorizationHeader = (headers?: HeadersInit): string | null => {
  if (!headers) return null
  if (headers instanceof Headers) {
    return headers.get("authorization") || headers.get("Authorization")
  }
  if (Array.isArray(headers)) {
    const match = headers.find(([key]) => key.toLowerCase() === "authorization")
    return match ? match[1] : null
  }
  const key = Object.keys(headers).find((k) => k.toLowerCase() === "authorization")
  return key ? (headers as Record<string, string>)[key] : null
}

const withAuthorizationHeader = (headers: HeadersInit | undefined, token: string): HeadersInit => {
  if (!headers) return { Authorization: `Bearer ${token}` }
  if (headers instanceof Headers) {
    const next = new Headers(headers)
    next.set("Authorization", `Bearer ${token}`)
    return next
  }
  if (Array.isArray(headers)) {
    const filtered = headers.filter(([key]) => key.toLowerCase() !== "authorization")
    return [...filtered, ["Authorization", `Bearer ${token}`]]
  }
  return {
    ...(headers as Record<string, string>),
    Authorization: `Bearer ${token}`,
  }
}

const getFreshAccessToken = async (): Promise<string | null> => {
  if (!refreshInProgress) {
    refreshInProgress = getSession()
      .then((session) => (session?.accessToken as string | undefined) ?? null)
      .catch(() => null)
      .finally(() => {
        refreshInProgress = null
      })
  }
  return refreshInProgress
}

export async function authFetch(input: RequestInfo | URL, init?: RequestInit, retry = false) {
  const response = await fetch(input, init)

  if (response.status === 401) {
    const shouldSignOut =
      typeof window !== "undefined" &&
      window.location.pathname !== "/login" &&
      hasAuthorizationHeader(init?.headers)

    if (shouldSignOut) {
      if (!retry) {
        const currentAuth = getAuthorizationHeader(init?.headers) || ""
        const currentToken = currentAuth.replace(/^Bearer\\s+/i, "").trim()
        const freshToken = await getFreshAccessToken()
        if (freshToken && freshToken !== currentToken) {
          const nextInit: RequestInit = {
            ...init,
            headers: withAuthorizationHeader(init?.headers, freshToken),
          }
          return authFetch(input, nextInit, true)
        }
      }

      if (!signOutInProgress) {
        signOutInProgress = true
        try {
          await signOut({ callbackUrl: "/login" })
        } finally {
          window.setTimeout(() => {
            signOutInProgress = false
          }, 10000)
        }
      }
    }
  }

  return response
}
