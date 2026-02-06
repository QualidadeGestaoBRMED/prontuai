"use client"

import { signOut } from "next-auth/react"

let signOutInProgress = false

export async function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)

  if (response.status === 401) {
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

  return response
}
