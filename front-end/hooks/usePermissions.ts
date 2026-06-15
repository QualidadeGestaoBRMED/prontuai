"use client";

import { useSession } from "next-auth/react";

export type UserRole = "ADMIN" | "CHECKER" | "SENDER" | "BOTH";

export interface PermissionsHook {
  user: any;
  role?: UserRole;
  isAdmin: boolean;
  isChecker: boolean;
  isSender: boolean;
  canManageUsers: boolean;
  canValidateExams: boolean;
  canSendDocuments: boolean;
  isLoading: boolean;
  isAuthenticated: boolean;
}

/**
 * Hook para verificar permissões do usuário baseado em seu role.
 *
 * @example
 * ```tsx
 * const { canManageUsers, canValidateExams } = usePermissions();
 *
 * return (
 *   <>
 *     {canManageUsers && <AdminPanel />}
 *     {canValidateExams && <ValidationPanel />}
 *   </>
 * );
 * ```
 */
export function usePermissions(): PermissionsHook {
  const { data: session, status } = useSession();

  const bypassAuth =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";
  const devRole = (process.env.NEXT_PUBLIC_DEV_ROLE || "ADMIN") as UserRole;

  if (bypassAuth) {
    const isAdmin = devRole === "ADMIN";
    const isChecker = devRole === "CHECKER" || devRole === "BOTH" || devRole === "ADMIN";
    const isSender = devRole === "SENDER" || devRole === "BOTH" || devRole === "ADMIN";

    return {
      user: { role: devRole, email: "dev@local" },
      role: devRole,
      isAdmin,
      isChecker,
      isSender,
      canManageUsers: isAdmin,
      canValidateExams: isChecker,
      canSendDocuments: isSender,
      isLoading: false,
      isAuthenticated: true,
    };
  }

  const user = session?.user;
  const role = user?.role;

  const isLoading = status === "loading";
  const isAuthenticated = status === "authenticated";

  // Verificações de role
  const isAdmin = role === "ADMIN";
  const isChecker = role === "CHECKER" || role === "BOTH" || role === "ADMIN";
  const isSender = role === "SENDER" || role === "BOTH" || role === "ADMIN";

  // Permissões específicas
  const canManageUsers = isAdmin;
  const canValidateExams = role === "CHECKER" || role === "BOTH" || role === "ADMIN";
  const canSendDocuments = role === "SENDER" || role === "BOTH" || role === "ADMIN";

  return {
    user,
    role,
    isAdmin,
    isChecker,
    isSender,
    canManageUsers,
    canValidateExams,
    canSendDocuments,
    isLoading,
    isAuthenticated,
  };
}
