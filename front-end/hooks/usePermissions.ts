"use client";

import { useSession } from "next-auth/react";

export type UserRole = "ADMIN" | "MANAGER" | "CURATOR" | "CHECKER" | "SENDER" | "VIEWER";

/**
 * Um usuário pode ter mais de um cargo. Esta é a ordem do back-end
 * (`PRECEDENCIA_PAPEIS` em back-end/app/models/user.py): o primeiro da lista é
 * o papel principal, o que vai para a auditoria. Mude as duas juntas.
 */
export const PRECEDENCIA_PAPEIS: UserRole[] = ["ADMIN", "MANAGER", "CHECKER", "CURATOR", "SENDER", "VIEWER"];

/**
 * Os cargos do usuário, na ordem de precedência. Sessão aberta antes do deploy
 * dos cargos múltiplos ainda não tem `roles` — aí vale o `role` único que ela
 * trouxe, até o próximo login.
 */
export function papeisDoUsuario(user?: { role?: UserRole; roles?: UserRole[] } | null): UserRole[] {
  const lista = user?.roles?.length ? user.roles : user?.role ? [user.role] : [];
  return PRECEDENCIA_PAPEIS.filter((p) => lista.includes(p));
}

/** Tem pelo menos um dos cargos permitidos — a mesma regra do `_exigir_papel` do back. */
export function temAlgumPapel(papeis: UserRole[], permitidos: UserRole[]): boolean {
  return papeis.some((p) => permitidos.includes(p));
}

/**
 * Quem vê o dashboard de indicadores. Espelho de `DASHBOARD_ROLES` em
 * back-end/app/core/auth.py — é o back-end que protege o dado; esta lista só
 * decide o que aparece na tela. Mude as duas juntas.
 */
// VIEWER (Visualizador) existe só para isto: somado a outro cargo, dá os
// indicadores sem dar a gestão.
export const DASHBOARD_ROLES: UserRole[] = ["ADMIN", "MANAGER", "VIEWER"];

export interface PermissionsHook {
  user: any;
  /** Papel principal (o primeiro de `roles`). Para PERMISSÃO, use as flags abaixo. */
  role?: UserRole;
  /** Todos os cargos do usuário, na ordem de `PRECEDENCIA_PAPEIS`. */
  roles: UserRole[];
  isAdmin: boolean;
  /** ADMIN ou MANAGER: acesso administrativo (MANAGER sem operações destrutivas) */
  isManagement: boolean;
  /** ADMIN ou CURATOR: curadoria do catálogo de exames. MANAGER fica de fora. */
  canCurateExams: boolean;
  /** Dashboard de indicadores: ADMIN e MANAGER — ver `DASHBOARD_ROLES`. */
  canViewDashboard: boolean;
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

/**
 * Cada flag é "tem algum cargo que permite". Somar cargos só soma acesso: o
 * CURATOR + SENDER continua sem aprovar na Checagem (nenhum dos dois aprova),
 * mas envia documento, porque o SENDER envia. Quem barra de verdade é o
 * back-end; aqui só se decide o que aparece.
 */
function buildPermissions(roles: UserRole[]) {
  const tem = (...permitidos: UserRole[]) => temAlgumPapel(roles, permitidos);
  const isAdmin = tem("ADMIN");
  const isManagement = tem("ADMIN", "MANAGER");
  // Curadoria do catálogo é separada da gestão: MANAGER não entra de propósito.
  const canCurateExams = tem("ADMIN", "CURATOR");
  const canViewDashboard = temAlgumPapel(roles, DASHBOARD_ROLES);
  const isChecker = tem("CHECKER") || isManagement;
  const isSender = tem("SENDER") || isManagement;

  return {
    isAdmin,
    isManagement,
    canCurateExams,
    canViewDashboard,
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
  // Aceita vários separados por vírgula ("CHECKER,SENDER") para testar combinações.
  const devRoles = papeisDoUsuario({
    roles: (process.env.NEXT_PUBLIC_DEV_ROLE || "ADMIN").split(",").map((r) => r.trim() as UserRole),
  });

  if (bypassAuth) {
    return {
      user: { role: devRoles[0], roles: devRoles, email: "dev@local" },
      role: devRoles[0],
      roles: devRoles,
      ...buildPermissions(devRoles),
      isLoading: false,
      isAuthenticated: true,
    };
  }

  const user = session?.user;
  const roles = papeisDoUsuario(user);

  const isLoading = status === "loading";
  const isAuthenticated = status === "authenticated";

  return {
    user,
    role: roles[0],
    roles,
    ...buildPermissions(roles),
    isLoading,
    isAuthenticated,
  };
}
