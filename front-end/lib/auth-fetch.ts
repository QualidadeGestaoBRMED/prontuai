"use client"

import { signOut } from "next-auth/react"

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

export async function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)

  if (response.status === 401) {
    const shouldSignOut =
      typeof window !== "undefined" &&
      window.location.pathname !== "/login" &&
      hasAuthorizationHeader(init?.headers)

    if (shouldSignOut && !signOutInProgress) {
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

  return response
}
