"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import { AppSidebar } from "@/components/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import UserDropdown from "@/components/user-dropdown";
import { RequireRole } from "@/components/require-role";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { API_ENDPOINTS } from "@/lib/config";
import { authFetch } from "@/lib/auth-fetch";
import {
  PRECEDENCIA_PAPEIS,
  papeisDoUsuario,
  usePermissions,
  type UserRole,
} from "@/hooks/usePermissions";

interface User {
  id: string;
  email: string;
  name: string;
  /** Papel principal; os cargos todos estão em `roles`. */
  role: UserRole;
  roles?: UserRole[];
  clinic_id?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface Clinic {
  id: string;
  name: string;
  cnpj?: string;
  phone?: string;
  is_active: boolean;
}

const roleLabels: Record<UserRole, string> = {
  ADMIN: "Administrador",
  MANAGER: "Gestor",
  // Rótulo de exibição. O identificador (CURATOR) vive no enum do Postgres e
  // não acompanha mudanças de nome — trocar o texto aqui basta.
  CURATOR: "Saúde",
  CHECKER: "Checador",
  SENDER: "Enviador",
  VIEWER: "Visualizador",
};

// Sem o "Apenas" de antes: com cargos somados, cada linha diz o que o cargo
// ACRESCENTA, e "apenas checagem" ao lado de "envio" marcado se contradizia.
const roleDescriptions: Record<UserRole, string> = {
  ADMIN: "Acesso total + gerenciar usuários",
  MANAGER: "Gerencia clínicas e usuários",
  CURATOR: "Catálogo de exames",
  CHECKER: "Checagem de documentos",
  SENDER: "Envio de documentos de uma clínica",
  VIEWER: "Dashboard de indicadores",
};

const roleBadges: Record<UserRole, string> = {
  ADMIN: "bg-purple-100 text-purple-800",
  MANAGER: "bg-amber-100 text-amber-800",
  CURATOR: "bg-teal-100 text-teal-800",
  CHECKER: "bg-blue-100 text-blue-800",
  SENDER: "bg-green-100 text-green-800",
  VIEWER: "bg-slate-100 text-slate-800",
};

// Espelho de `PAPEIS_DO_GESTOR` em back-end/app/api/v1/users.py: o que o
// MANAGER pode atribuir, em qualquer combinação, e quem ele pode editar.
const PAPEIS_DO_GESTOR: UserRole[] = ["CHECKER", "SENDER"];

/** O corpo de erro do back, que é JSON nos erros de negócio e texto num 500. */
async function mensagemDeErro(response: Response, padrao: string) {
  const corpo = await response.text();
  try {
    return JSON.parse(corpo).detail ?? corpo ?? padrao;
  } catch {
    return corpo || padrao;
  }
}

/**
 * Caixas de marcar dos cargos. O MANAGER só vê os que pode atribuir — os
 * outros nem aparecem, porque o servidor recusaria.
 */
function SeletorCargos({
  idPrefixo,
  value,
  onChange,
  podeTodos,
}: {
  idPrefixo: string;
  value: UserRole[];
  onChange: (papeis: UserRole[]) => void;
  podeTodos: boolean;
}) {
  const opcoes = podeTodos ? PRECEDENCIA_PAPEIS : PRECEDENCIA_PAPEIS.filter((p) => PAPEIS_DO_GESTOR.includes(p));
  const alternar = (papel: UserRole, marcado: boolean) =>
    onChange(marcado ? [...value.filter((p) => p !== papel), papel] : value.filter((p) => p !== papel));

  return (
    <div>
      <Label>Cargos</Label>
      <div className="mt-2 divide-y rounded-md border">
        {opcoes.map((papel) => (
          <label
            key={papel}
            htmlFor={`${idPrefixo}-${papel}`}
            className="flex cursor-pointer items-start gap-3 px-3 py-2.5 hover:bg-gray-50"
          >
            <Checkbox
              id={`${idPrefixo}-${papel}`}
              checked={value.includes(papel)}
              onCheckedChange={(v) => alternar(papel, v === true)}
              className="mt-0.5"
            />
            <div>
              <div className="text-sm font-medium">{roleLabels[papel]}</div>
              <div className="text-xs text-gray-500">{roleDescriptions[papel]}</div>
            </div>
          </label>
        ))}
      </div>
      <p className="mt-1 text-xs text-gray-500">
        Marque um ou mais. O acesso do usuário é a soma dos cargos marcados.
      </p>
    </div>
  );
}

function SeletorClinica({
  value,
  onChange,
  clinics,
  loading,
}: {
  value: string;
  onChange: (id: string) => void;
  clinics: Clinic[];
  loading: boolean;
}) {
  return (
    <div>
      <Label htmlFor="clinic">Clínica *</Label>
      <Select value={value} onValueChange={onChange} disabled={loading}>
        <SelectTrigger>
          <SelectValue placeholder={loading ? "Carregando..." : "Selecione uma clínica"} />
        </SelectTrigger>
        <SelectContent>
          {clinics.length === 0 ? (
            <div className="px-2 py-3 text-sm text-gray-500 text-center">
              Nenhuma clínica disponível
            </div>
          ) : (
            clinics.map((clinic) => (
              <SelectItem key={clinic.id} value={clinic.id}>
                <div>
                  <div className="font-medium">{clinic.name}</div>
                  {clinic.cnpj && (
                    <div className="text-xs text-gray-500">
                      CNPJ: {clinic.cnpj}
                    </div>
                  )}
                </div>
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
      <p className="text-xs text-gray-500 mt-1">
        Quem tem o cargo de Enviador precisa estar vinculado a uma clínica
      </p>
    </div>
  );
}

export default function UsersAdminPage() {
  const { data: session } = useSession();
  // MANAGER pode gerenciar usuários, mas só atribui roles CHECKER/SENDER
  const { isAdmin: canAssignAdmin } = usePermissions();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);

  // Estados das clínicas
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [loadingClinics, setLoadingClinics] = useState(false);

  // Modal de confirmação de desativação
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [userToDeactivate, setUserToDeactivate] = useState<User | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  // Estados do formulário
  const [formEmail, setFormEmail] = useState("");
  const [formName, setFormName] = useState("");
  const [formRoles, setFormRoles] = useState<UserRole[]>(["CHECKER"]);
  const [formClinicId, setFormClinicId] = useState("");
  const [emailError, setEmailError] = useState("");
  const [creating, setCreating] = useState(false);

  const validateEmail = (email: string) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email) {
      setEmailError("");
      return false;
    }
    if (!emailRegex.test(email)) {
      setEmailError("Email inválido. Use o formato: exemplo@dominio.com");
      return false;
    }
    setEmailError("");
    return true;
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setFormEmail(value);
    if (value) {
      validateEmail(value);
    } else {
      setEmailError("");
    }
  };

  const fetchUsers = useCallback(async () => {
    if (!session?.user?.email) return;

    try {
      const response = await authFetch(API_ENDPOINTS.USERS);

      if (!response.ok) throw new Error("Erro ao carregar usuários");

      const data = await response.json();
      setUsers(data);
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar usuários");
    } finally {
      setLoading(false);
    }
  }, [session?.user?.email]);

  const fetchClinics = useCallback(async () => {
    if (!session?.user?.email) return;

    setLoadingClinics(true);
    try {
      const response = await authFetch(API_ENDPOINTS.CLINICS);

      if (!response.ok) throw new Error("Erro ao carregar clínicas");

      const data = await response.json();
      setClinics(data);
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar clínicas");
    } finally {
      setLoadingClinics(false);
    }
  }, [session?.user?.email]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  useEffect(() => {
    if (createModalOpen || editModalOpen) {
      fetchClinics();
    }
  }, [createModalOpen, editModalOpen, fetchClinics]);

  const temEnviador = formRoles.includes("SENDER");

  const handleCreateUser = async () => {
    if (!session?.user?.email || !formEmail || !formName) {
      toast.error("Preencha todos os campos");
      return;
    }

    if (formRoles.length === 0) {
      toast.error("Selecione pelo menos um cargo");
      return;
    }

    // Validar clínica para quem tem SENDER
    if (temEnviador && !formClinicId) {
      toast.error("Selecione uma clínica para quem tem o cargo de Enviador");
      return;
    }

    // Validar formato de email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formEmail)) {
      toast.error("Email inválido. Use o formato: exemplo@dominio.com");
      return;
    }

    setCreating(true);
    try {
      const body: {
        email: string;
        name: string;
        roles: UserRole[];
        clinic_id?: string;
      } = {
        email: formEmail,
        name: formName,
        roles: formRoles,
      };

      // Adicionar clinic_id apenas para quem tem SENDER
      if (temEnviador) {
        body.clinic_id = formClinicId;
      }

      const response = await authFetch(API_ENDPOINTS.USERS, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        // O back-end devolve JSON nos erros de negócio, mas um 500 vem como
        // texto puro ("Internal Server Error"). Fazer .json() direto estourava
        // no parse e o toast mostrava o erro do parse em vez da causa.
        throw new Error(await mensagemDeErro(response, "Erro ao criar usuário"));
      }

      toast.success("Usuário criado com sucesso!");
      setCreateModalOpen(false);
      setFormEmail("");
      setFormName("");
      setFormRoles(["CHECKER"]);
      setFormClinicId("");
      setEmailError("");
      fetchUsers();
    } catch (error) {
      console.error("Erro:", error);
      const errorMessage = error instanceof Error ? error.message : "Erro ao criar usuário";
      toast.error(errorMessage);
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!session?.user?.email || !selectedUser) return;

    if (formRoles.length === 0) {
      toast.error("Selecione pelo menos um cargo");
      return;
    }
    if (temEnviador && !formClinicId) {
      toast.error("Selecione uma clínica para quem tem o cargo de Enviador");
      return;
    }

    try {
      const response = await authFetch(API_ENDPOINTS.USER_BY_ID(selectedUser.id), {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: formName,
          roles: formRoles,
          is_active: selectedUser.is_active,
          // Sem SENDER a clínica não vai: se ele tinha e perdeu o cargo, o
          // back-end tira a clínica junto.
          ...(temEnviador ? { clinic_id: formClinicId } : {}),
        }),
      });

      if (!response.ok) throw new Error(await mensagemDeErro(response, "Erro ao atualizar usuário"));

      toast.success("Usuário atualizado com sucesso!");
      setEditModalOpen(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (error) {
      console.error("Erro:", error);
      toast.error(error instanceof Error ? error.message : "Erro ao atualizar usuário");
    }
  };

  const handleToggleActive = async (user: User) => {
    // Se estiver desativando, mostrar modal de confirmação
    if (user.is_active) {
      setUserToDeactivate(user);
      setDeactivateModalOpen(true);
      return;
    }

    // Se estiver ativando, executar diretamente
    if (!session?.user?.email) return;

    try {
      const response = await authFetch(API_ENDPOINTS.USER_BY_ID(user.id), {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          is_active: true,
        }),
      });

      if (!response.ok) throw new Error("Erro ao atualizar status");

      toast.success("Usuário ativado com sucesso!");
      fetchUsers();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao atualizar status");
    }
  };

  const confirmDeactivate = async () => {
    if (!session?.user?.email || !userToDeactivate) return;

    setDeactivating(true);
    try {
      const response = await authFetch(API_ENDPOINTS.USER_BY_ID(userToDeactivate.id), {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          is_active: false,
        }),
      });

      if (!response.ok) throw new Error("Erro ao desativar usuário");

      toast.success("Usuário desativado com sucesso!");
      setDeactivateModalOpen(false);
      setUserToDeactivate(null);
      fetchUsers();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao desativar usuário");
    } finally {
      setDeactivating(false);
    }
  };

  const openEditModal = (user: User) => {
    setSelectedUser(user);
    setFormName(user.name);
    setFormRoles(papeisDoUsuario(user));
    setFormClinicId(user.clinic_id ?? "");
    setEditModalOpen(true);
  };

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground" />
            <h1 className="text-lg font-semibold">Gerenciar Usuários</h1>
            <div className="ml-auto">
              <UserDropdown />
            </div>
          </header>

          <main className="p-4 md:p-6 lg:p-8">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold text-white">Usuários do Sistema</h2>
                <p className="text-sm text-white/80 mt-1">
                  Gerencie permissões e acesso dos usuários
                </p>
              </div>
              <Button
                onClick={() => setCreateModalOpen(true)}
                className="hover:scale-105 transition-transform"
              >
                + Novo Usuário
              </Button>
            </div>

            <div className="bg-white rounded-lg shadow">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Nome
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Email
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Cargos
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Ações
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {loading ? (
                    // Skeleton loader - mostra 3 linhas placeholder
                    Array.from({ length: 3 }).map((_, i) => (
                      <tr key={i} className="animate-pulse">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-4 bg-gray-200 rounded w-32"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-4 bg-gray-200 rounded w-48"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-6 bg-gray-200 rounded-full w-24"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-6 bg-gray-200 rounded-full w-16"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex gap-2">
                            <div className="h-8 bg-gray-200 rounded w-16"></div>
                            <div className="h-8 bg-gray-200 rounded w-20"></div>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : users.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                        Nenhum usuário encontrado
                      </td>
                    </tr>
                  ) : (
                    users.map((user) => (
                      <tr key={user.id}>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          {user.name}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                          {user.email}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-wrap gap-1">
                            {papeisDoUsuario(user).map((papel) => (
                              <span
                                key={papel}
                                className={`whitespace-nowrap px-2 py-1 text-xs rounded-full ${roleBadges[papel]}`}
                              >
                                {roleLabels[papel]}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-1 text-xs rounded-full ${
                              user.is_active
                                ? "bg-green-100 text-green-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {user.is_active ? "Ativo" : "Inativo"}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                          {/* Espelha `_assert_manager_can_edit` do back-end: o
                              gestor só edita quem tem apenas CHECKER/SENDER e
                              nunca ativa ou desativa. Esconder aqui é só para
                              não oferecer um botão que o servidor vai recusar. */}
                          {(canAssignAdmin ||
                            papeisDoUsuario(user).every((p) => PAPEIS_DO_GESTOR.includes(p))) && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openEditModal(user)}
                            >
                              Editar
                            </Button>
                          )}
                          {canAssignAdmin && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleToggleActive(user)}
                            >
                              {user.is_active ? "Desativar" : "Ativar"}
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </main>
        </SidebarInset>

        {/* Create User Modal */}
        <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo Usuário</DialogTitle>
              <DialogDescription>
                Adicione um novo usuário ao sistema
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="usuario@example.com"
                  value={formEmail}
                  onChange={handleEmailChange}
                  className={emailError ? "border-red-500" : ""}
                />
                {emailError && (
                  <p className="text-xs text-red-500 mt-1">{emailError}</p>
                )}
              </div>

              <div>
                <Label htmlFor="name">Nome</Label>
                <Input
                  id="name"
                  placeholder="Nome completo"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>

              <SeletorCargos
                idPrefixo="novo-cargo"
                value={formRoles}
                onChange={setFormRoles}
                podeTodos={canAssignAdmin}
              />

              {temEnviador && (
                <SeletorClinica
                  value={formClinicId}
                  onChange={setFormClinicId}
                  clinics={clinics}
                  loading={loadingClinics}
                />
              )}
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setCreateModalOpen(false);
                  setEmailError("");
                  setFormClinicId("");
                }}
                disabled={creating}
              >
                Cancelar
              </Button>
              <Button
                onClick={handleCreateUser}
                disabled={
                  creating ||
                  !!emailError ||
                  !formEmail ||
                  !formName ||
                  formRoles.length === 0 ||
                  (temEnviador && !formClinicId)
                }
              >
                {creating ? "Criando..." : "Criar Usuário"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Edit User Modal */}
        <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Editar Usuário</DialogTitle>
              <DialogDescription>
                Atualize as informações do usuário
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <Label>Email</Label>
                <Input value={selectedUser?.email || ""} disabled />
              </div>

              <div>
                <Label htmlFor="edit-name">Nome</Label>
                <Input
                  id="edit-name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>

              <SeletorCargos
                idPrefixo="editar-cargo"
                value={formRoles}
                onChange={setFormRoles}
                podeTodos={canAssignAdmin}
              />

              {temEnviador && (
                <SeletorClinica
                  value={formClinicId}
                  onChange={setFormClinicId}
                  clinics={clinics}
                  loading={loadingClinics}
                />
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setEditModalOpen(false)}>
                Cancelar
              </Button>
              <Button
                onClick={handleUpdateUser}
                disabled={formRoles.length === 0 || (temEnviador && !formClinicId)}
              >
                Salvar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Deactivate Confirmation Modal */}
        <Dialog open={deactivateModalOpen} onOpenChange={setDeactivateModalOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Confirmar Desativação</DialogTitle>
              <DialogDescription>
                Tem certeza que deseja desativar este usuário?
              </DialogDescription>
            </DialogHeader>

            <div className="py-4">
              <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
                <div className="flex items-start">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <h3 className="text-sm font-medium text-yellow-800">
                      Atenção
                    </h3>
                    <div className="mt-2 text-sm text-yellow-700">
                      <p>
                        O usuário <span className="font-semibold">{userToDeactivate?.name}</span> ({userToDeactivate?.email}) será desativado e não poderá mais acessar o sistema.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setDeactivateModalOpen(false);
                  setUserToDeactivate(null);
                }}
                disabled={deactivating}
              >
                Cancelar
              </Button>
              <Button
                variant="destructive"
                onClick={confirmDeactivate}
                disabled={deactivating}
              >
                {deactivating ? "Desativando..." : "Desativar Usuário"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </SidebarProvider>
    </RequireRole>
  );
}
