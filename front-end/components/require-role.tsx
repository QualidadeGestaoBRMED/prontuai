"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { ReactNode } from "react";
import Link from "next/link";
import { UserRole } from "@/hooks/usePermissions";

interface RequireRoleProps {
  children: ReactNode;
  allowedRoles: UserRole[];
  fallback?: ReactNode;
  redirectTo?: string;
}

/**
 * Componente guard que protege conteúdo baseado em roles.
 * Redireciona para /login se não autenticado.
 * Mostra fallback ou mensagem de acesso negado se não autorizado.
 *
 * @example
 * ```tsx
 * <RequireRole allowedRoles={["ADMIN"]}>
 *   <AdminPanel />
 * </RequireRole>
 * ```
 *
 * @example
 * ```tsx
 * <RequireRole
 *   allowedRoles={["ADMIN", "CHECKER", "BOTH"]}
 *   fallback={<div>Você não tem permissão</div>}
 * >
 *   <ValidationPanel />
 * </RequireRole>
 * ```
 */
export function RequireRole({
  children,
  allowedRoles,
  fallback,
  redirectTo = "/login"
}: RequireRoleProps) {
  const { data: session, status } = useSession();
  const bypassAuth =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";

  if (bypassAuth) {
    return <>{children}</>;
  }

  if (status === "loading") {
    return fallback ? <>{fallback}</> : null;
  }

  // Not authenticated
  if (status === "unauthenticated") {
    redirect(redirectTo);
  }

  const userRole = session?.user?.role;

  // Not authorized
  if (!userRole || !allowedRoles.includes(userRole)) {
    if (userRole === "CHECKER") {
      redirect("/checagem");
    }
    if (userRole === "SENDER") {
      redirect("/anexar-prontuario");
    }
    if (userRole === "BOTH") {
      redirect("/anexar-prontuario");
    }
    if (fallback) {
      return <>{fallback}</>;
    }

    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-8 text-center">
          <div className="mb-4">
            <svg
              className="mx-auto h-16 w-16 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Acesso Negado</h1>
          <p className="text-gray-600 mb-6">
            Você não tem permissão para acessar esta página.
          </p>
          <div className="space-y-2 text-sm text-gray-500">
            <p>
              <strong>Sua role:</strong> {userRole || "Nenhuma"}
            </p>
            <p>
              <strong>Roles necessárias:</strong> {allowedRoles.join(", ")}
            </p>
          </div>
          <div className="mt-6">
            <Link
              href="/"
              className="inline-block px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              Voltar para Início
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Authorized
  return <>{children}</>;
}
