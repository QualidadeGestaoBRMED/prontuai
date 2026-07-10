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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { API_ENDPOINTS } from "@/lib/config";
import { authFetch } from "@/lib/auth-fetch";

interface Clinic {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export default function ClinicsAdminPage() {
  const { data: session } = useSession();
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedClinic, setSelectedClinic] = useState<Clinic | null>(null);

  // Estados do formulário
  const [formEmail, setFormEmail] = useState("");
  const [formName, setFormName] = useState("");
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

  const fetchClinics = useCallback(async () => {
    if (!session?.user?.email) return;

    try {
      const response = await authFetch(API_ENDPOINTS.CLINICS);

      if (!response.ok) throw new Error("Erro ao carregar clínicas");

      const data = await response.json();
      setClinics(data);
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar clínicas");
    } finally {
      setLoading(false);
    }
  }, [session?.user?.email]);

  useEffect(() => {
    fetchClinics();
  }, [fetchClinics]);

  const handleCreateClinic = async () => {
    if (!session?.user?.email || !formEmail || !formName) {
      toast.error("Preencha todos os campos");
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
      const response = await authFetch(API_ENDPOINTS.CLINICS, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: formEmail,
          name: formName,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        console.error("Erro do servidor:", error);

        // Tentar extrair mensagem de erro detalhada
        let errorMessage = "Erro ao criar clínica";

        if (error.detail) {
          if (typeof error.detail === 'string') {
            errorMessage = error.detail;
          } else if (Array.isArray(error.detail)) {
            // Erros de validação do Pydantic
            errorMessage = error.detail.map((e: { loc?: string[]; msg: string }) =>
              `${e.loc?.join('.') || 'campo'} - ${e.msg}`
            ).join(', ');
          }
        }

        throw new Error(errorMessage);
      }

      toast.success("Clínica criada com sucesso!");
      setCreateModalOpen(false);
      setFormEmail("");
      setFormName("");
      setEmailError("");
      fetchClinics();
    } catch (error) {
      console.error("Erro completo:", error);
      const errorMessage = error instanceof Error ? error.message : "Erro ao criar clínica";
      toast.error(errorMessage);
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateClinic = async () => {
    if (!session?.user?.email || !selectedClinic) return;

    try {
      const response = await authFetch(API_ENDPOINTS.CLINIC_BY_ID(selectedClinic.id), {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: formName,
          is_active: selectedClinic.is_active,
        }),
      });

      if (!response.ok) throw new Error("Erro ao atualizar clínica");

      toast.success("Clínica atualizada com sucesso!");
      setEditModalOpen(false);
      setSelectedClinic(null);
      fetchClinics();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao atualizar clínica");
    }
  };

  const handleToggleActive = async (clinic: Clinic) => {
    if (!session?.user?.email) return;

    try {
      const response = await authFetch(API_ENDPOINTS.CLINIC_BY_ID(clinic.id), {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          is_active: !clinic.is_active,
        }),
      });

      if (!response.ok) throw new Error("Erro ao atualizar status");

      toast.success(
        `Clínica ${clinic.is_active ? "desativada" : "ativada"} com sucesso!`
      );
      fetchClinics();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao atualizar status");
    }
  };

  const openEditModal = (clinic: Clinic) => {
    setSelectedClinic(clinic);
    setFormName(clinic.name);
    setEditModalOpen(true);
  };

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground" />
            <h1 className="text-lg font-semibold">Gerenciar Clínicas</h1>
            <div className="ml-auto">
              <UserDropdown />
            </div>
          </header>

          <main className="p-4 md:p-6 lg:p-8">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold text-white">Clínicas Credenciadas</h2>
                <p className="text-sm text-white/80 mt-1">
                  Gerencie as clínicas credenciadas do sistema
                </p>
              </div>
              <Button
                onClick={() => setCreateModalOpen(true)}
                className="hover:scale-105 transition-transform"
              >
                + Nova Clínica
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
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Criado em
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Ações
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {loading ? (
                    // Skeleton loader
                    Array.from({ length: 3 }).map((_, i) => (
                      <tr key={i} className="animate-pulse">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-4 bg-gray-200 rounded w-32"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-4 bg-gray-200 rounded w-48"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-6 bg-gray-200 rounded-full w-16"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="h-4 bg-gray-200 rounded w-24"></div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex gap-2">
                            <div className="h-8 bg-gray-200 rounded w-16"></div>
                            <div className="h-8 bg-gray-200 rounded w-20"></div>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : clinics.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                        Nenhuma clínica encontrada
                      </td>
                    </tr>
                  ) : (
                    clinics.map((clinic) => (
                      <tr key={clinic.id}>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                          {clinic.name}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                          {clinic.email}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-1 text-xs rounded-full ${
                              clinic.is_active
                                ? "bg-green-100 text-green-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {clinic.is_active ? "Ativa" : "Inativa"}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                          {new Date(clinic.created_at).toLocaleDateString("pt-BR")}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => openEditModal(clinic)}
                          >
                            Editar
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleToggleActive(clinic)}
                          >
                            {clinic.is_active ? "Desativar" : "Ativar"}
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

        {/* Create Clinic Modal */}
        <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Nova Clínica</DialogTitle>
              <DialogDescription>
                Adicione uma nova clínica credenciada ao sistema
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="clinica@example.com"
                  value={formEmail}
                  onChange={handleEmailChange}
                  className={emailError ? "border-red-500" : ""}
                />
                {emailError ? (
                  <p className="text-xs text-red-500 mt-1">{emailError}</p>
                ) : (
                  <p className="text-xs text-gray-500 mt-1">
                    Este email será usado para login da clínica
                  </p>
                )}
              </div>

              <div>
                <Label htmlFor="name">Nome da Clínica</Label>
                <Input
                  id="name"
                  placeholder="Nome completo da clínica"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setCreateModalOpen(false);
                  setEmailError("");
                }}
                disabled={creating}
              >
                Cancelar
              </Button>
              <Button
                onClick={handleCreateClinic}
                disabled={creating || !!emailError || !formEmail || !formName}
              >
                {creating ? "Criando..." : "Criar Clínica"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Edit Clinic Modal */}
        <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Editar Clínica</DialogTitle>
              <DialogDescription>
                Atualize as informações da clínica
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <Label>Email</Label>
                <Input value={selectedClinic?.email || ""} disabled />
                <p className="text-xs text-gray-500 mt-1">
                  O email não pode ser alterado
                </p>
              </div>

              <div>
                <Label htmlFor="edit-name">Nome da Clínica</Label>
                <Input
                  id="edit-name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setEditModalOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleUpdateClinic}>Salvar</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </SidebarProvider>
    </RequireRole>
  );
}
