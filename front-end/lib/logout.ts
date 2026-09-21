"use client"

import { signOut } from "next-auth/react"

/**
 * Encerra a sessão revogando o refresh token no back-end e só então limpando
 * o cookie local. Use isto em vez de chamar `signOut` direto — ver
 * `app/api/auth/logout/route.ts`.
 */
export async function logout(callbackUrl: string) {
  try {
    await fetch("/api/auth/logout", { method: "POST" })
  } catch {
    // Rede fora: sai localmente mesmo assim.
  }
  await signOut({ callbackUrl })
}
