"use client"

import { useEffect } from "react"
import { SessionProvider, useSession } from "next-auth/react"
import { logout } from "@/lib/logout"
import { registrarSessaoConhecida } from "@/lib/auth-fetch"
import { toast } from "sonner"
import { NotificationProvider } from "@/hooks/use-notifications"
import { MaintenanceWrapper } from "@/components/maintenance/maintenance-wrapper"

/**
 * Mensagem por motivo da sessão perdida.
 *
 * Todos os desfechos caíam em "Sessão expirada", e com isso um relato de
 * usuário não distinguia cookie vencido de back-end fora do ar — a mesma frase
 * descrevia quatro causas com correções diferentes.
 */
const MENSAGEM_POR_MOTIVO: Record<string, string> = {
  no_refresh_token: "Sua sessão expirou por inatividade. Faça login novamente.",
  refresh_failed: "Não foi possível renovar sua sessão. Faça login novamente.",
  refresh_error: "Não conseguimos falar com o servidor. Faça login novamente.",
  retry_ainda_401: "Seu acesso a este recurso foi negado. Faça login novamente.",
}
const MENSAGEM_PADRAO = "Sessão expirada. Faça login novamente."

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession()
  const email = session?.user?.email ?? undefined
  // `iat` só chega aqui se for exposto no callback de sessão do NextAuth;
  // enquanto não for, a duração da sessão fica nula no aviso e o resto segue.
  const iat = (session as { iat?: number } | null)?.iat

  // `authFetch` roda fora do React e não enxerga a sessão. Só registra quando
  // há e-mail: assim que o cookie morre o `useSession` devolve null, e é
  // justamente aí que a última dica precisa sobreviver — quem guarda essa
  // regra é `registrarSessaoConhecida`.
  useEffect(() => {
    registrarSessaoConhecida({ email, iat })
  }, [email, iat])

  useEffect(() => {
    let fired = false
    const handle = (evento: Event) => {
      if (fired) return
      fired = true
      const motivo = (evento as CustomEvent<{ motivo?: string }>).detail?.motivo
      toast.error(
        (motivo && MENSAGEM_POR_MOTIVO[motivo]) || MENSAGEM_PADRAO,
        { duration: 4000 },
      )
      logout("/login")
    }
    window.addEventListener("auth:unauthorized", handle)
    return () => window.removeEventListener("auth:unauthorized", handle)
  }, [])

  return <>{children}</>
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <AuthGuard>
        <MaintenanceWrapper>
          <NotificationProvider>
            {children}
          </NotificationProvider>
        </MaintenanceWrapper>
      </AuthGuard>
    </SessionProvider>
  )
}
