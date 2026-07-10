"use client";

import { useSession } from "next-auth/react";

export type UserRole = "ADMIN" | "MANAGER" | "CHECKER" | "SENDER";

export interface PermissionsHook {
  user: any;
  role?: UserRole;
  isAdmin: boolean;
  /** ADMIN ou MANAGER: acesso administrativo (MANAGER sem operações destrutivas) */
  isManagement: boolean;
  isChecker: boolean;
  isSender: boolean;
  canManageUsers: boolean;
  canValidateExams: boolean;
  canSendDocuments: boolean;
  /** Apenas ADMIN: exclusões e operações de sistema */
  canDelete: boolean;
  isLoading: boolean;
  isAuthenticated: boolean;
}

function buildPermissions(role: UserRole | undefined) {
  const isAdmin = role === "ADMIN";
  const isManagement = role === "ADMIN" || role === "MANAGER";
  const isChecker = role === "CHECKER" || isManagement;
  const isSender = role === "SENDER" || isManagement;

  return {
    isAdmin,
    isManagement,
    isChecker,
    isSender,
    canManageUsers: isManagement,
    canValidateExams: isChecker,
    canSendDocuments: isSender,
    canDelete: isAdmin,
  };
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
    return {
      user: { role: devRole, email: "dev@local" },
      role: devRole,
      ...buildPermissions(devRole),
      isLoading: false,
      isAuthenticated: true,
    };
  }

  const user = session?.user;
  const role = user?.role;

  const isLoading = status === "loading";
  const isAuthenticated = status === "authenticated";

  return {
    user,
    role,
    ...buildPermissions(role),
    isLoading,
    isAuthenticated,
  };
}
