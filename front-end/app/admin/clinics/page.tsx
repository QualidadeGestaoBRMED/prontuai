"use client";

import { useState, useEffect, useCallback, useRef } from "react";
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
import {
  CredenciadoBrnetAutocomplete,
  descreverClinicas,
  type CredenciadoBrnet,
} from "@/components/credenciado-brnet-autocomplete";
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

/** Usuário vinculado a uma clínica, como volta de `GET /v1/clinics/{id}/users`. */
interface ClinicUser {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  /** Último documento enviado por este usuário. ISO, ou null se nunca enviou. */
  last_upload_at: string | null;
  /** Último `auth.login.success` deste e-mail. ISO, ou null se nunca logou. */
  last_login_at: string | null;
}

/** Corpo de `GET /v1/clinics/{id}/users`. */
interface ClinicUsersResposta {
  /**
   * Último envio da clínica por QUALQUER usuário, inclusive quem já foi
   * desvinculado — por isso não é o máximo da lista abaixo.
   */
  ultimo_envio_clinica: string | null;
  usuarios: ClinicUser[];
}

/**
 * "há 3 dias", "hoje", "nunca".
 *
 * Numa investigação a pergunta é "faz quanto tempo?", e a data crua obriga a
 * fazer a conta de cabeça. A data exata vai no `title`, para quem precisar
 * dela.
 */
function haQuantoTempo(iso: string | null): { texto: string; titulo?: string; alerta: boolean } {
  if (!iso) return { texto: "nunca", alerta: true };
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return { texto: "—", alerta: false };

  const dias = Math.floor((Date.now() - data.getTime()) / 86_400_000);
  const titulo = data.toLocaleString("pt-BR");
  // 30 dias é o corte do alerta: abaixo disso a clínica está em uso normal.
  const alerta = dias >= 30;

  if (dias <= 0) return { texto: "hoje", titulo, alerta: false };
  if (dias === 1) return { texto: "ontem", titulo, alerta: false };
  if (dias < 30) return { texto: `há ${dias} dias`, titulo, alerta };
  if (dias < 365) return { texto: `há ${Math.floor(dias / 30)} meses`, titulo, alerta };
  return { texto: `há mais de um ano`, titulo, alerta };
}

export default function ClinicsAdminPage() {
  const { data: session } = useSession();
  const [clinics, setClinics] = useState<Clinic[]>([]);
  // Usuários da clínica que está aberta no modal de edição. Só ADMIN enxerga a
  // seção, e o back-end recusa de qualquer forma (`require_admin`).
  const [usuariosClinica, setUsuariosClinica] = useState<ClinicUsersResposta | null>(null);
  const [carregandoUsuarios, setCarregandoUsuarios] = useState(false);
  const [erroUsuarios, setErroUsuarios] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedClinic, setSelectedClinic] = useState<Clinic | null>(null);

  // Estados do formulário
  const [formEmail, setFormEmail] = useState("");
  const [formName, setFormName] = useState("");
  const [emailError, setEmailError] = useState("");
  const [creating, setCreating] = useState(false);

  // Vínculo com o credenciado do BRNET, só na criação: o nome sugere os
  // credenciados conforme a digitação, e escolher uma sugestão é o que vincula.
  // Nome digitado sem escolher fica sem vínculo — permitido só ao ADMIN (contas
  // internas, credenciado fora da rede); o back-end recusa o Gestor com 403.
  const [credenciados, setCredenciados] = useState<CredenciadoBrnet[]>([]);
  const [carregandoCredenciados, setCarregandoCredenciados] = useState(false);
  const [erroCredenciados, setErroCredenciados] = useState<string | null>(null);
  const [formBrnetId, setFormBrnetId] = useState<string | null>(null);
  const credenciadoEscolhido = formBrnetId
    ? credenciados.find((c) => c.identificador === formBrnetId)
    : undefined;
  // Com credenciado escolhido, o e-mail é opcional: vazio, o back-end grava o
  // do BRNET; digitado, vence o digitado (o do BRNET pode estar desatualizado).
  const emailBrnet = credenciadoEscolhido?.email ?? null;

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

  // Mesmo tratamento da tela de Auditoria: esperar por `session.user.email`
  // deixava a tabela presa no skeleton para sempre quando o bypass de dev está
  // ligado, porque nesse modo não existe sessão do NextAuth. Vale só para a
  // LEITURA — criar, editar e desativar continuam exigindo sessão de verdade.
  const bypassAuth =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";
  const podeCarregar = bypassAuth || !!session?.user?.email;
  const ehAdmin = bypassAuth || session?.user?.role === "ADMIN";

  // Qual clínica a busca em voo está carregando. Abrir uma clínica, fechar e
  // abrir outra depressa deixa duas respostas correndo, e a primeira pode
  // chegar por último — sem esta trava, o modal mostraria os usuários da
  // clínica errada.
  const usuariosPedidosRef = useRef<string | null>(null);

  /**
   * Busca os usuários da clínica aberta no modal de edição.
   *
   * Sob demanda de propósito: são 117 clínicas na base, e trazer os usuários de
   * todas no carregamento da tela custaria uma consulta por clínica para uma
   * informação que só é olhada uma de cada vez, numa investigação pontual.
   *
   * Sem cache entre aberturas: `last_login_at` e `last_upload_at` envelhecem, e
   * guardar a resposta faria o modal mostrar "há 2 dias" de uma consulta da
   * manhã. Uma requisição por abertura é barata — é um clique explícito.
   */
  const carregarUsuarios = useCallback(async (clinicId: string) => {
    usuariosPedidosRef.current = clinicId;
    setUsuariosClinica(null);
    setErroUsuarios(null);
    setCarregandoUsuarios(true);
    try {
      const resposta = await authFetch(API_ENDPOINTS.CLINIC_USERS(clinicId));
      if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
      const corpo: ClinicUsersResposta = await resposta.json();
      if (usuariosPedidosRef.current !== clinicId) return;
      setUsuariosClinica({
        ultimo_envio_clinica: corpo.ultimo_envio_clinica ?? null,
        usuarios: corpo.usuarios ?? [],
      });
    } catch {
      if (usuariosPedidosRef.current !== clinicId) return;
      setErroUsuarios("Não foi possível carregar os usuários.");
    } finally {
      if (usuariosPedidosRef.current === clinicId) setCarregandoUsuarios(false);
    }
  }, []);

  /**
   * Rede credenciada do BRNET, a cada abertura de modal: o back-end guarda a
   * rede por uma hora, mas as clínicas já vinculadas a cada credenciado vêm do
   * banco, e mudam a cada cadastro.
   */
  const carregarCredenciados = useCallback(async () => {
    setCarregandoCredenciados(true);
    setErroCredenciados(null);
    try {
      const resposta = await authFetch(API_ENDPOINTS.CLINICS_CREDENCIADOS_BRNET);
      if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
      setCredenciados(await resposta.json());
    } catch {
      setErroCredenciados("Não foi possível carregar a rede credenciada do BRNET. Tente de novo em instantes.");
    } finally {
      setCarregandoCredenciados(false);
    }
  }, []);

  const fetchClinics = useCallback(async () => {
    if (!podeCarregar) return;

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
  }, [podeCarregar]);

  useEffect(() => {
    fetchClinics();
  }, [fetchClinics]);

  const abrirCriacao = () => {
    setFormBrnetId(null);
    setFormName("");
    setCreateModalOpen(true);
    carregarCredenciados();
  };

  const handleCreateClinic = async () => {
    if (!session?.user?.email || !formName || (!formEmail && !emailBrnet)) {
      toast.error("Preencha todos os campos");
      return;
    }
    if (!ehAdmin && !formBrnetId) {
      toast.error("Escolha a clínica na lista da rede credenciada do BRNET");
      return;
    }

    // Validar formato de email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (formEmail && !emailRegex.test(formEmail)) {
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
          ...(formEmail ? { email: formEmail } : {}),
          name: formName,
          ...(formBrnetId ? { brnet_id: formBrnetId } : {}),
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
      setFormBrnetId(null);
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

      if (!response.ok) {
        let detalhe = "Erro ao atualizar clínica";
        try {
          const corpo = await response.json();
          if (typeof corpo.detail === "string") detalhe = corpo.detail;
        } catch {
          // corpo não-JSON (500): fica a mensagem padrão
        }
        throw new Error(detalhe);
      }

      toast.success("Clínica atualizada com sucesso!");
      setEditModalOpen(false);
      setSelectedClinic(null);
      fetchClinics();
    } catch (error) {
      console.error("Erro:", error);
      toast.error(error instanceof Error ? error.message : "Erro ao atualizar clínica");
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
    // Só para ADMIN: a seção nem é renderizada para MANAGER, e o back-end
    // responderia 403 (`require_admin`) — pedir à toa só geraria erro no log.
    if (ehAdmin) carregarUsuarios(clinic.id);
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
                onClick={abrirCriacao}
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
              <div className="space-y-1">
                <Label htmlFor="name">Nome da Clínica</Label>
                <CredenciadoBrnetAutocomplete
                  id="name"
                  value={formName}
                  onChange={(nome) => {
                    setFormName(nome);
                    setFormBrnetId(null);
                  }}
                  onEscolher={(c) => {
                    setFormName(c.nome);
                    setFormBrnetId(c.identificador);
                  }}
                  opcoes={credenciados}
                  placeholder="Digite cidade ou nome da clínica"
                />
                {carregandoCredenciados ? (
                  <p className="text-xs text-gray-500">Carregando a rede credenciada do BRNET…</p>
                ) : erroCredenciados ? (
                  <p className="text-xs text-red-600">{erroCredenciados}</p>
                ) : credenciadoEscolhido ? (
                  credenciadoEscolhido.clinicas.length > 0 ? (
                    <p className="text-xs text-amber-700">
                      Já existe clínica para este credenciado: {descreverClinicas(credenciadoEscolhido.clinicas)}.
                      Prefira usar a existente.
                    </p>
                  ) : (
                    <p className="text-xs text-green-700">Clínica da rede credenciada do BRNET.</p>
                  )
                ) : formName.trim() ? (
                  <p className="text-xs text-gray-500">
                    {ehAdmin
                      ? "Sem vínculo com o BRNET — escolha um nome da lista ou siga assim para conta interna ou credenciado fora da rede."
                      : "Escolha a clínica na lista da rede credenciada do BRNET."}
                  </p>
                ) : null}
              </div>

              <div>
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder={emailBrnet ?? "clinica@example.com"}
                  value={formEmail}
                  onChange={handleEmailChange}
                  className={emailError ? "border-red-500" : ""}
                />
                {emailError ? (
                  <p className="text-xs text-red-500 mt-1">{emailError}</p>
                ) : emailBrnet ? (
                  <div className="mt-1 space-y-0.5 text-xs text-gray-500">
                    <p>
                      E-mail no BRNET: <span className="font-medium text-gray-700">{emailBrnet}</span>
                    </p>
                    <p>
                      Se este campo ficar vazio, o e-mail registrado será este. Se estiver desatualizado ou
                      errado, preencha o campo com o novo.
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-gray-500 mt-1">
                    Este email será usado para login da clínica
                  </p>
                )}
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
                disabled={
                  creating ||
                  !!emailError ||
                  (!formEmail && !emailBrnet) ||
                  !formName.trim() ||
                  (!ehAdmin && !formBrnetId)
                }
              >
                {creating ? "Criando..." : "Criar Clínica"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Edit Clinic Modal */}
        <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
          {/* Rolagem: com a lista de usuários dentro, o modal passa da altura
              da tela numa clínica com muitos SENDER. */}
          <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[640px]">
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

              {/* Usuários vinculados — só ADMIN. MANAGER edita a clínica sem
                  enxergar as pessoas dela, e o back-end recusa de qualquer
                  forma (`require_admin`). É leitura: nada aqui é salvo pelo
                  botão Salvar, que continua mexendo só no nome. */}
              {ehAdmin && (
                <div className="border-t border-gray-200 pt-4">
                  <Label className="text-xs uppercase tracking-wide text-gray-500">
                    Usuários vinculados
                  </Label>

                  {carregandoUsuarios ? (
                    <p className="mt-2 text-sm text-gray-500">Carregando usuários…</p>
                  ) : erroUsuarios ? (
                    <p className="mt-2 text-sm text-red-600">{erroUsuarios}</p>
                  ) : !usuariosClinica ? null : (
                    <div className="mt-2 space-y-3">
                      <p className="text-xs uppercase tracking-wide text-gray-500">
                        Último envio da clínica:{" "}
                        <span
                          title={haQuantoTempo(usuariosClinica.ultimo_envio_clinica).titulo}
                          className={
                            haQuantoTempo(usuariosClinica.ultimo_envio_clinica).alerta
                              ? "font-semibold text-amber-700"
                              : "font-semibold text-gray-700"
                          }
                        >
                          {haQuantoTempo(usuariosClinica.ultimo_envio_clinica).texto}
                        </span>
                      </p>

                      {usuariosClinica.usuarios.length === 0 ? (
                        /* Distingue de erro: a clínica existe e não tem ninguém
                           vinculado — numa investigação isso é a resposta. */
                        <p className="text-sm text-gray-500">
                          Nenhum usuário vinculado a esta clínica.
                        </p>
                      ) : (
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-gray-400">
                              <th className="py-1 pr-4 font-normal">Usuário</th>
                              {/* nowrap: "Último envio" quebrava em duas linhas
                                  dentro da largura do modal. */}
                              <th className="py-1 pr-4 font-normal whitespace-nowrap">Último envio</th>
                              <th className="py-1 font-normal whitespace-nowrap">Último login</th>
                            </tr>
                          </thead>
                          <tbody>
                            {usuariosClinica.usuarios.map((u) => {
                              const envio = haQuantoTempo(u.last_upload_at);
                              const login = haQuantoTempo(u.last_login_at);
                              return (
                                <tr key={u.id} className="align-top">
                                  <td className="py-1 pr-4">
                                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                      <span className="font-mono text-gray-800">{u.email}</span>
                                      <span className="text-gray-500">{u.name}</span>
                                      {!u.is_active && (
                                        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-800">
                                          inativo
                                        </span>
                                      )}
                                    </div>
                                  </td>
                                  <td
                                    className={`py-1 pr-4 whitespace-nowrap ${
                                      envio.alerta ? "text-amber-700" : "text-gray-600"
                                    }`}
                                    title={envio.titulo}
                                  >
                                    {envio.texto}
                                  </td>
                                  <td
                                    className={`py-1 whitespace-nowrap ${
                                      login.alerta ? "text-amber-700" : "text-gray-600"
                                    }`}
                                    title={login.titulo}
                                  >
                                    {login.texto}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      )}
                    </div>
                  )}
                </div>
              )}
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
