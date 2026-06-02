"use client"

export async function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)

  if (response.status === 401) {
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("auth:unauthorized", {
          detail: {
            url: typeof input === "string" ? input : input.toString(),
          },
        }),
      )
    }
  }

  return response
}
