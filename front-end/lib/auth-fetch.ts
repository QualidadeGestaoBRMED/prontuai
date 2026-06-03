"use client"

let refreshPromise: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise
  refreshPromise = fetch("/api/auth/refresh-token", { method: "POST" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshPromise = null
    })
  return refreshPromise
}

export async function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)

  if (response.status === 401) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      const retry = await fetch(input, init)
      if (retry.status !== 401) return retry
    }

    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("auth:unauthorized", {
          detail: { url: typeof input === "string" ? input : input.toString() },
        }),
      )
    }
  }

  return response
}
