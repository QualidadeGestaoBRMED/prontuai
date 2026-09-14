"use client";

import { useSession } from "next-auth/react";

export type UserRole = "ADMIN" | "MANAGER" | "CURATOR" | "CHECKER" | "SENDER";

/**
 * Quem vê o dashboard de indicadores. Espelho de `DASHBOARD_ROLES` em
 * back-end/app/core/auth.py — é o back-end que protege o dado; esta lista só
 * decide o que aparece na tela. Mude as duas juntas.
 */
export const DASHBOARD_ROLES: UserRole[] = ["ADMIN", "MANAGER"];

/**
 * Papéis que VEEM as telas do Menu Principal, mas não agem nelas: não enviam
 * documento nem aprovam/rejeitam. Aqui só se escondem os botões — quem barra a
 * escrita de verdade é o back-end (`require_checker` / `require_sender`).
 */
export const READ_ONLY_ROLES: UserRole[] = ["CURATOR"];

export interface PermissionsHook {
  user: any;
  role?: UserRole;
  isAdmin: boolean;
  /** ADMIN ou MANAGER: acesso administrativo (MANAGER sem operações destrutivas) */
  isManagement: boolean;
  /** ADMIN ou CURATOR: curadoria do catálogo de exames. MANAGER fica de fora. */
  canCurateExams: boolean;
  /** Dashboard de indicadores. MANAGER fica de fora — ver `DASHBOARD_ROLES`. */
  canViewDashboard: boolean;
  /** Vê o Menu Principal sem poder agir — ver `READ_ONLY_ROLES`. */
  isReadOnly: boolean;
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
  // Curadoria do catálogo é separada da gestão: MANAGER não entra de propósito.
  const canCurateExams = role === "ADMIN" || role === "CURATOR";
  const canViewDashboard = role !== undefined && DASHBOARD_ROLES.includes(role);
  const isReadOnly = role !== undefined && READ_ONLY_ROLES.includes(role);
  const isChecker = role === "CHECKER" || isManagement;
  const isSender = role === "SENDER" || isManagement;

  return {
    isAdmin,
    isManagement,
    canCurateExams,
    canViewDashboard,
    isReadOnly,
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
