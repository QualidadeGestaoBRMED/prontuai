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
import { API_ENDPOINTS } from "@/lib/config";

type UserRole = "ADMIN" | "CHECKER" | "SENDER";

interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const roleLabels: Record<UserRole, string> = {
  ADMIN: "Administrador",
  CHECKER: "Checador",
  SENDER: "Enviador",
};

const roleDescriptions: Record<UserRole, string> = {
  ADMIN: "Acesso total + gerenciar usuários",
  CHECKER: "Apenas checagem de exames",
  SENDER: "Apenas enviar documentos",
};

export default function UsersAdminPage() {
  const { data: session } = useSession();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);

  // Form states
  const [formEmail, setFormEmail] = useState("");
  const [formName, setFormName] = useState("");
  const [formRole, setFormRole] = useState<UserRole>("CHECKER");
  const [emailError, setEmailError] = useState("");

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
    if (!session?.accessToken) return;

    try {
      const response = await fetch(API_ENDPOINTS.USERS, {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) throw new Error("Erro ao carregar usuários");

      const data = await response.json();
      setUsers(data);
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar usuários");
    } finally {
      setLoading(false);
    }
  }, [session?.accessToken]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreateUser = async () => {
    if (!session?.accessToken || !formEmail || !formName) {
      toast.error("Preencha todos os campos");
      return;
    }

    // Validar formato de email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formEmail)) {
      toast.error("Email inválido. Use o formato: exemplo@dominio.com");
      return;
    }

    try {
      const response = await fetch(API_ENDPOINTS.USERS, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: formEmail,
          name: formName,
          role: formRole,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao criar usuário");
      }

      toast.success("Usuário criado com sucesso!");
      setCreateModalOpen(false);
      setFormEmail("");
      setFormName("");
      setFormRole("CHECKER");
      setEmailError("");
      fetchUsers();
    } catch (error) {
      console.error("Erro:", error);
      const errorMessage = error instanceof Error ? error.message : "Erro ao criar usuário";
      toast.error(errorMessage);
    }
  };

  const handleUpdateUser = async () => {
    if (!session?.accessToken || !selectedUser) return;

    try {
      const response = await fetch(API_ENDPOINTS.USER_BY_ID(selectedUser.id), {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: formName,
          role: formRole,
          is_active: selectedUser.is_active,
        }),
      });

      if (!response.ok) throw new Error("Erro ao atualizar usuário");

      toast.success("Usuário atualizado com sucesso!");
      setEditModalOpen(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao atualizar usuário");
    }
  };

  const handleToggleActive = async (user: User) => {
    if (!session?.accessToken) return;

    try {
      const response = await fetch(API_ENDPOINTS.USER_BY_ID(user.id), {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          is_active: !user.is_active,
        }),
      });

      if (!response.ok) throw new Error("Erro ao atualizar status");

      toast.success(
        `Usuário ${user.is_active ? "desativado" : "ativado"} com sucesso!`
      );
      fetchUsers();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao atualizar status");
    }
  };

  const openEditModal = (user: User) => {
    setSelectedUser(user);
    setFormName(user.name);
    setFormRole(user.role);
    setEditModalOpen(true);
  };

  return (
    <RequireRole allowedRoles={["ADMIN"]}>
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
                      Role
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
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-1 text-xs rounded-full ${
                              user.role === "ADMIN"
                                ? "bg-purple-100 text-purple-800"
                                : user.role === "CHECKER"
                                ? "bg-blue-100 text-blue-800"
                                : "bg-green-100 text-green-800"
                            }`}
                          >
                            {roleLabels[user.role]}
                          </span>
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
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => openEditModal(user)}
                          >
                            Editar
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleToggleActive(user)}
                          >
                            {user.is_active ? "Desativar" : "Ativar"}
                          </Button>
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

              <div>
                <Label htmlFor="role">Role</Label>
                <Select value={formRole} onValueChange={(v) => setFormRole(v as UserRole)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ADMIN">
                      <div>
                        <div className="font-medium">{roleLabels.ADMIN}</div>
                        <div className="text-xs text-gray-500 group-hover:text-white">
                          {roleDescriptions.ADMIN}
                        </div>
                      </div>
                    </SelectItem>
                    <SelectItem value="CHECKER">
                      <div>
                        <div className="font-medium">{roleLabels.CHECKER}</div>
                        <div className="text-xs text-gray-500 group-hover:text-white">
                          {roleDescriptions.CHECKER}
                        </div>
                      </div>
                    </SelectItem>
                    <SelectItem value="SENDER">
                      <div>
                        <div className="font-medium">{roleLabels.SENDER}</div>
                        <div className="text-xs text-gray-500 group-hover:text-white">
                          {roleDescriptions.SENDER}
                        </div>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => {
                setCreateModalOpen(false);
                setEmailError("");
              }}>
                Cancelar
              </Button>
              <Button
                onClick={handleCreateUser}
                disabled={!!emailError || !formEmail || !formName}
              >
                Criar Usuário
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

              <div>
                <Label htmlFor="edit-role">Role</Label>
                <Select value={formRole} onValueChange={(v) => setFormRole(v as UserRole)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ADMIN">{roleLabels.ADMIN}</SelectItem>
                    <SelectItem value="CHECKER">{roleLabels.CHECKER}</SelectItem>
                    <SelectItem value="SENDER">{roleLabels.SENDER}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setEditModalOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleUpdateUser}>Salvar</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </SidebarProvider>
    </RequireRole>
  );
}
