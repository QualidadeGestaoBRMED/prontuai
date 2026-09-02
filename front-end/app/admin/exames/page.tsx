"use client";

/**
 * Painel de curadoria do catálogo de exames similares.
 *
 * Modelo de dois níveis: um exame pai (nome canônico, o mesmo que o BRNET usa)
 * e N variações — os nomes alternativos que aparecem nos documentos.
 *
 * Nesta fase o painel só cataloga. O motor de comparação continua lendo os
 * artefatos de disco; a geração de vetor e a troca da fonte vêm depois.
 */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { API_ENDPOINTS } from "@/lib/config";
import { authFetch } from "@/lib/auth-fetch";

interface ExamVariation {
  id: string;
  parent_id: string;
  name: string;
  name_normalized: string;
  is_active: boolean;
  source: string | null;
  occurrences: number | null;
}

interface ExamParent {
  id: string;
  name: string;
  name_normalized: string;
  status: "ativo" | "quarentena";
  is_external: boolean;
  is_active: boolean;
  source: string | null;
  notes: string | null;
  variation_count: number;
}

interface ExamParentDetail extends ExamParent {
  variations: ExamVariation[];
}

interface ExamConflict {
  id: string;
  name: string;
  candidate_parents: string[];
  source: string | null;
}

interface ExamPendency {
  name: string;
  name_normalized: string;
  documents: number;
  requests: number;
}

interface CatalogStats {
  parents_total: number;
  parents_ativo: number;
  parents_quarentena: number;
  parents_sem_variacao: number;
  variations_total: number;
  conflicts_pending: number;
  terms_without_vector?: number;
  brnet_without_parent?: number;
}

/** Extrai a mensagem de erro do backend (409 traz o motivo da colisão). */
async function mensagemDeErro(response: Response, fallback: string) {
  try {
    const corpo = await response.json();
    return corpo?.detail || fallback;
  } catch {
    return fallback;
  }
}

interface CamposVariacaoProps {
  valores: string[];
  erros?: (string | null)[];
  onChange: (valores: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Lista de campos de variação com "+ Adicionar" e remoção por linha.
 *
 * Sempre mantém pelo menos um campo aberto: remover o último apenas o limpa,
 * para o formulário nunca ficar sem lugar onde digitar.
 */
function CamposVariacao({
  valores,
  erros,
  onChange,
  placeholder = "ex: transaminase pirúvica",
  disabled = false,
}: CamposVariacaoProps) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const focarUltimo = useRef(false);

  useEffect(() => {
    if (!focarUltimo.current) return;
    focarUltimo.current = false;
    refs.current[valores.length - 1]?.focus();
  }, [valores.length]);

  const alterar = (indice: number, valor: string) =>
    onChange(valores.map((atual, i) => (i === indice ? valor : atual)));

  const remover = (indice: number) => {
    const restantes = valores.filter((_, i) => i !== indice);
    onChange(restantes.length > 0 ? restantes : [""]);
  };

  const adicionar = () => {
    focarUltimo.current = true;
    onChange([...valores, ""]);
  };

  return (
    <div className="space-y-2">
      {valores.map((valor, indice) => (
        <div key={indice}>
          <div className="flex items-center gap-2">
            <Input
              ref={(elemento) => {
                refs.current[indice] = elemento;
              }}
              placeholder={placeholder}
              value={valor}
              disabled={disabled}
              onChange={(e) => alterar(indice, e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                e.preventDefault();
                // Enter abre o próximo campo, para cadastrar vários em sequência.
                if (valor.trim() && indice === valores.length - 1) adicionar();
                else refs.current[indice + 1]?.focus();
              }}
              className={erros?.[indice] ? "border-red-500" : ""}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Remover este campo"
              disabled={disabled || (valores.length === 1 && !valor)}
              onClick={() => remover(indice)}
            >
              ×
            </Button>
          </div>
          {erros?.[indice] && (
            <p className="text-xs text-red-500 mt-1">{erros[indice]}</p>
          )}
        </div>
      ))}

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={adicionar}
        disabled={disabled}
      >
        + Adicionar variação
      </Button>
    </div>
  );
}


export default function ExamesAdminPage() {
  const { data: session, status: statusSessao } = useSession();

  // Com DEV_AUTH_BYPASS não existe sessão do NextAuth, mas o proxy injeta o
  // Bearer do mesmo jeito. Esperar por session.user.email deixaria a tabela
  // presa no skeleton para sempre em dev.
  const bypassAuth =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";
  const podeCarregar = bypassAuth || !!session?.user?.email;

  const [aba, setAba] = useState<"pendencias" | "catalogo" | "conflitos">("pendencias");
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [parents, setParents] = useState<ExamParent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [filtroStatus, setFiltroStatus] = useState<"todos" | "ativo" | "quarentena">("todos");
  const [somenteSemVariacao, setSomenteSemVariacao] = useState(false);

  // Detalhe expandido: pai -> variações carregadas
  const [expandido, setExpandido] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<ExamParentDetail | null>(null);
  const [novasVariacoes, setNovasVariacoes] = useState<string[]>([""]);
  const [errosVariacao, setErrosVariacao] = useState<(string | null)[]>([]);
  const [adicionandoVariacoes, setAdicionandoVariacoes] = useState(false);

  const [modalCriar, setModalCriar] = useState(false);
  const [modalEditar, setModalEditar] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [formNome, setFormNome] = useState("");
  const [formStatus, setFormStatus] = useState<"ativo" | "quarentena">("ativo");
  const [formExterno, setFormExterno] = useState(false);
  const [formNotas, setFormNotas] = useState("");
  const [formVariacoes, setFormVariacoes] = useState<string[]>([""]);
  const [emEdicao, setEmEdicao] = useState<ExamParent | null>(null);

  const [pendencias, setPendencias] = useState<ExamPendency[]>([]);
  const [carregandoPendencias, setCarregandoPendencias] = useState(true);
  const [conflitos, setConflitos] = useState<ExamConflict[]>([]);
  const [todosPais, setTodosPais] = useState<ExamParent[]>([]);
  const [escolhaConflito, setEscolhaConflito] = useState<Record<string, string>>({});

  const carregarStats = useCallback(async () => {
    try {
      const response = await authFetch(API_ENDPOINTS.EXAM_STATS);
      if (!response.ok) return;
      setStats(await response.json());
    } catch (error) {
      console.error("Erro ao carregar estatísticas:", error);
    }
  }, []);

  const carregarParents = useCallback(async () => {
    if (!podeCarregar) {
      // Sessão resolvida e ainda sem acesso: para o skeleton em vez de girar.
      if (statusSessao !== "loading") setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "500" });
      if (buscaAplicada) params.set("search", buscaAplicada);
      if (filtroStatus !== "todos") params.set("status", filtroStatus);
      if (somenteSemVariacao) params.set("only_without_variations", "true");

      const response = await authFetch(`${API_ENDPOINTS.EXAMS}?${params.toString()}`);
      if (!response.ok) throw new Error("Erro ao carregar exames");
      const data = await response.json();
      setParents(data.items || []);
      setTotal(data.total || 0);
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar catálogo de exames");
    } finally {
      setLoading(false);
    }
  }, [podeCarregar, statusSessao, buscaAplicada, filtroStatus, somenteSemVariacao]);

  const carregarPendencias = useCallback(async () => {
    if (!podeCarregar) {
      if (statusSessao !== "loading") setCarregandoPendencias(false);
      return;
    }
    setCarregandoPendencias(true);
    try {
      const response = await authFetch(`${API_ENDPOINTS.EXAM_PENDENCIES}?limit=300`);
      if (!response.ok) throw new Error("Erro ao carregar pendências");
      setPendencias(await response.json());
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar pendências do catálogo");
    } finally {
      setCarregandoPendencias(false);
    }
  }, [podeCarregar, statusSessao]);

  const carregarConflitos = useCallback(async () => {
    try {
      const [respConflitos, respPais] = await Promise.all([
        authFetch(API_ENDPOINTS.EXAM_CONFLICTS),
        authFetch(`${API_ENDPOINTS.EXAMS}?limit=500`),
      ]);
      if (respConflitos.ok) setConflitos(await respConflitos.json());
      if (respPais.ok) {
        const data = await respPais.json();
        setTodosPais(data.items || []);
      }
    } catch (error) {
      console.error("Erro ao carregar conflitos:", error);
      toast.error("Erro ao carregar conflitos de importação");
    }
  }, []);

  useEffect(() => {
    carregarStats();
  }, [carregarStats]);

  useEffect(() => {
    if (aba === "catalogo") carregarParents();
  }, [aba, carregarParents]);

  useEffect(() => {
    if (aba === "pendencias") carregarPendencias();
  }, [aba, carregarPendencias]);

  useEffect(() => {
    if (aba === "conflitos") carregarConflitos();
  }, [aba, carregarConflitos]);

  const abrirDetalhe = async (parent: ExamParent) => {
    if (expandido === parent.id) {
      setExpandido(null);
      setDetalhe(null);
      setNovasVariacoes([""]);
      setErrosVariacao([]);
      return;
    }
    setExpandido(parent.id);
    setDetalhe(null);
    setNovasVariacoes([""]);
    setErrosVariacao([]);
    try {
      const response = await authFetch(API_ENDPOINTS.EXAM_BY_ID(parent.id));
      if (!response.ok) throw new Error("Erro ao carregar variações");
      setDetalhe(await response.json());
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar variações");
    }
  };

  const limparFormulario = () => {
    setFormNome("");
    setFormStatus("ativo");
    setFormExterno(false);
    setFormNotas("");
    setFormVariacoes([""]);
    setEmEdicao(null);
  };

  const criarExame = async () => {
    if (!formNome.trim()) {
      toast.error("Informe o nome do exame");
      return;
    }
    setSalvando(true);
    try {
      const variacoes = formVariacoes
        .map((valor) => valor.trim())
        .filter(Boolean);

      const response = await authFetch(API_ENDPOINTS.EXAMS, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formNome.trim(),
          status: formStatus,
          is_external: formExterno,
          notes: formNotas.trim() || null,
          variations: variacoes,
        }),
      });

      if (!response.ok) {
        toast.error(await mensagemDeErro(response, "Erro ao criar exame"));
        return;
      }

      toast.success("Exame criado");
      setModalCriar(false);
      limparFormulario();
      carregarParents();
      carregarStats();
      carregarPendencias();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao criar exame");
    } finally {
      setSalvando(false);
    }
  };

  /** Abre "Novo Exame" com o nome do BRNET já preenchido: o curador só acrescenta variações. */
  const cadastrarPendencia = (pendencia: ExamPendency) => {
    limparFormulario();
    setFormNome(pendencia.name);
    setFormStatus("ativo");
    setFormVariacoes([""]);
    setModalCriar(true);
  };

  const abrirEdicao = (parent: ExamParent) => {
    setEmEdicao(parent);
    setFormNome(parent.name);
    setFormStatus(parent.status);
    setFormExterno(parent.is_external);
    setFormNotas(parent.notes || "");
    setModalEditar(true);
  };

  const salvarEdicao = async () => {
    if (!emEdicao) return;
    setSalvando(true);
    try {
      const response = await authFetch(API_ENDPOINTS.EXAM_BY_ID(emEdicao.id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formNome.trim(),
          status: formStatus,
          is_external: formExterno,
          notes: formNotas.trim() || null,
        }),
      });

      if (!response.ok) {
        toast.error(await mensagemDeErro(response, "Erro ao salvar exame"));
        return;
      }

      toast.success("Exame atualizado");
      setModalEditar(false);
      limparFormulario();
      carregarParents();
      carregarStats();
      if (expandido) {
        const atualizado = await authFetch(API_ENDPOINTS.EXAM_BY_ID(expandido));
        if (atualizado.ok) setDetalhe(await atualizado.json());
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao salvar exame");
    } finally {
      setSalvando(false);
    }
  };

  /**
   * Envia todos os campos preenchidos de uma vez.
   *
   * Cada variação é um POST próprio, então o resultado é parcial por natureza:
   * as que entraram saem do formulário, as que falharam (409 de colisão, em
   * geral) permanecem com o motivo embaixo do campo, para corrigir sem
   * redigitar o resto.
   */
  const adicionarVariacoes = async (parentId: string) => {
    const entradas = novasVariacoes.map((valor) => valor.trim()).filter(Boolean);
    if (entradas.length === 0) {
      toast.error("Preencha ao menos uma variação");
      return;
    }

    setAdicionandoVariacoes(true);
    const falhas: { valor: string; erro: string }[] = [];
    let sucessos = 0;

    try {
      for (const nome of entradas) {
        try {
          const response = await authFetch(API_ENDPOINTS.EXAM_VARIATIONS(parentId), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: nome }),
          });
          if (response.ok) {
            sucessos += 1;
          } else {
            falhas.push({
              valor: nome,
              erro: await mensagemDeErro(response, "Erro ao adicionar"),
            });
          }
        } catch {
          falhas.push({ valor: nome, erro: "Falha de rede" });
        }
      }

      setNovasVariacoes(falhas.length > 0 ? falhas.map((f) => f.valor) : [""]);
      setErrosVariacao(falhas.map((f) => f.erro));

      if (sucessos > 0) {
        toast.success(
          sucessos === 1 ? "Variação adicionada" : `${sucessos} variações adicionadas`
        );
        const atualizado = await authFetch(API_ENDPOINTS.EXAM_BY_ID(parentId));
        if (atualizado.ok) setDetalhe(await atualizado.json());
        carregarParents();
        carregarStats();
      }
      if (falhas.length > 0) {
        toast.error(
          falhas.length === 1
            ? falhas[0].erro
            : `${falhas.length} variações não entraram — veja o motivo em cada campo`
        );
      }
    } finally {
      setAdicionandoVariacoes(false);
    }
  };

  const removerVariacao = async (variationId: string, parentId: string) => {
    try {
      const response = await authFetch(
        API_ENDPOINTS.EXAM_VARIATION_BY_ID(variationId),
        { method: "DELETE" }
      );
      if (!response.ok) {
        toast.error(await mensagemDeErro(response, "Erro ao remover variação"));
        return;
      }
      toast.success("Variação removida");
      const atualizado = await authFetch(API_ENDPOINTS.EXAM_BY_ID(parentId));
      if (atualizado.ok) setDetalhe(await atualizado.json());
      carregarParents();
      carregarStats();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao remover variação");
    }
  };

  const resolverConflito = async (
    conflito: ExamConflict,
    resolucao: "atribuida" | "descartada"
  ) => {
    const parentId = escolhaConflito[conflito.id];
    if (resolucao === "atribuida" && !parentId) {
      toast.error("Escolha o exame pai antes de atribuir");
      return;
    }
    try {
      const response = await authFetch(API_ENDPOINTS.EXAM_CONFLICT_RESOLVE(conflito.id), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resolution: resolucao,
          parent_id: resolucao === "atribuida" ? parentId : null,
        }),
      });

      if (!response.ok) {
        toast.error(await mensagemDeErro(response, "Erro ao resolver conflito"));
        return;
      }

      toast.success(
        resolucao === "atribuida" ? "Variação atribuída" : "Termo descartado"
      );
      carregarConflitos();
      carregarStats();
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao resolver conflito");
    }
  };

  const paisOrdenados = useMemo(
    () => [...todosPais].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")),
    [todosPais]
  );

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground" />
            <h1 className="text-lg font-semibold">Catálogo de Exames</h1>
            <div className="ml-auto">
              <UserDropdown />
            </div>
          </header>

          <main className="p-4 md:p-6 lg:p-8">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold text-white">Exames e Variações</h2>
                <p className="text-sm text-white/80 mt-1">
                  Gerencie o catálogo de exames e suas variações de nome.
                </p>
              </div>
              <Button
                onClick={() => {
                  limparFormulario();
                  setModalCriar(true);
                }}
                className="hover:scale-105 transition-transform"
              >
                + Novo Exame
              </Button>
            </div>

            {/* Abas */}
            <div className="mb-4 flex gap-2">
              <Button
                variant={aba === "pendencias" ? "default" : "outline"}
                size="sm"
                onClick={() => setAba("pendencias")}
              >
                Pendências
                {stats?.brnet_without_parent ? ` (${stats.brnet_without_parent})` : ""}
              </Button>
              <Button
                variant={aba === "catalogo" ? "default" : "outline"}
                size="sm"
                onClick={() => setAba("catalogo")}
              >
                Catálogo
              </Button>
              <Button
                variant={aba === "conflitos" ? "default" : "outline"}
                size="sm"
                onClick={() => setAba("conflitos")}
              >
                Conflitos de importação
                {stats?.conflicts_pending ? ` (${stats.conflicts_pending})` : ""}
              </Button>
            </div>

            {aba === "pendencias" ? (
              /* Pendências: exames que o BRNET pede e o catálogo não tem */
              <div className="bg-white rounded-lg shadow overflow-hidden">
                <p className="text-sm text-gray-600 p-6 pb-4">
                  Exames que o BRNET pede e que <strong>não têm pai no catálogo</strong>.
                  Sem pai, a comparação nunca encontra o exame — nem por sinônimo, nem
                  pela varredura do texto. Ordenado por quantidade de documentos em que
                  o BRNET pediu o exame.
                </p>
                <table className="w-full">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Exame pedido pelo BRNET
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Documentos
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {carregandoPendencias ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <tr key={i} className="animate-pulse">
                          <td className="px-6 py-4">
                            <div className="h-4 bg-gray-200 rounded w-64" />
                          </td>
                          <td className="px-6 py-4">
                            <div className="h-4 bg-gray-200 rounded w-12" />
                          </td>
                          <td className="px-6 py-4">
                            <div className="h-8 bg-gray-200 rounded w-24" />
                          </td>
                        </tr>
                      ))
                    ) : pendencias.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-6 py-12 text-center text-gray-500">
                          Nenhuma pendência: todo exame que o BRNET pede tem pai no catálogo.
                        </td>
                      </tr>
                    ) : (
                      pendencias.map((pendencia) => (
                        <tr key={pendencia.name_normalized} className="hover:bg-gray-50">
                          <td className="px-6 py-4 text-sm font-medium">
                            {pendencia.name}
                            <div className="text-xs text-gray-400 font-normal mt-0.5">
                              {pendencia.name_normalized}
                            </div>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-600">
                            {pendencia.documents.toLocaleString("pt-BR")}
                          </td>
                          <td className="px-6 py-4 text-sm">
                            <Button size="sm" onClick={() => cadastrarPendencia(pendencia)}>
                              Cadastrar
                            </Button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ) : aba === "catalogo" ? (
              <>
                {/* Filtros */}
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <Input
                    placeholder="Buscar por exame ou variação..."
                    value={busca}
                    onChange={(e) => setBusca(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setBuscaAplicada(busca);
                    }}
                    className="max-w-xs bg-white"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setBuscaAplicada(busca)}
                  >
                    Buscar
                  </Button>
                  {buscaAplicada && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setBusca("");
                        setBuscaAplicada("");
                      }}
                    >
                      Limpar
                    </Button>
                  )}
                  <Select
                    value={filtroStatus}
                    onValueChange={(v) => setFiltroStatus(v as typeof filtroStatus)}
                  >
                    <SelectTrigger className="w-[200px] bg-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="todos">Todos os status</SelectItem>
                      <SelectItem value="ativo">Confirmado no BRNET</SelectItem>
                      <SelectItem value="quarentena">Em quarentena</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    variant={somenteSemVariacao ? "default" : "outline"}
                    onClick={() => setSomenteSemVariacao((v) => !v)}
                  >
                    Só sem variação
                  </Button>
                  <span className="ml-auto text-sm text-white/70">
                    {total} exame{total === 1 ? "" : "s"}
                  </span>
                </div>

                <div className="bg-white rounded-lg shadow overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-gray-50 border-b">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Exame pai
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Status
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Variações
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Ações
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {loading ? (
                        Array.from({ length: 5 }).map((_, i) => (
                          <tr key={i} className="animate-pulse">
                            <td className="px-6 py-4">
                              <div className="h-4 bg-gray-200 rounded w-48" />
                            </td>
                            <td className="px-6 py-4">
                              <div className="h-6 bg-gray-200 rounded-full w-28" />
                            </td>
                            <td className="px-6 py-4">
                              <div className="h-4 bg-gray-200 rounded w-8" />
                            </td>
                            <td className="px-6 py-4">
                              <div className="h-8 bg-gray-200 rounded w-32" />
                            </td>
                          </tr>
                        ))
                      ) : parents.length === 0 ? (
                        <tr>
                          <td
                            colSpan={4}
                            className="px-6 py-12 text-center text-gray-500"
                          >
                            Nenhum exame encontrado. Rode{" "}
                            <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">
                              scripts/seed_exam_catalog.py
                            </code>{" "}
                            para importar o CSV.
                          </td>
                        </tr>
                      ) : (
                        parents.map((parent) => (
                          <Fragment key={parent.id}>
                            <tr className="hover:bg-gray-50">
                              <td className="px-6 py-4 text-sm font-medium">
                                {parent.name}
                                {parent.is_external && (
                                  <Badge variant="outline" className="ml-2 text-xs">
                                    externo
                                  </Badge>
                                )}
                                {!parent.is_active && (
                                  <Badge variant="secondary" className="ml-2 text-xs">
                                    inativo
                                  </Badge>
                                )}
                              </td>
                              <td className="px-6 py-4">
                                <span
                                  className={`px-2 py-1 text-xs rounded-full ${
                                    parent.status === "ativo"
                                      ? "bg-green-100 text-green-800"
                                      : "bg-amber-100 text-amber-800"
                                  }`}
                                  title={
                                    parent.status === "ativo"
                                      ? "Nome confirmado no BRNET: vale como canônico"
                                      : "Herdado do CSV sem correspondência no BRNET: serve só como vocabulário"
                                  }
                                >
                                  {parent.status === "ativo"
                                    ? "Confirmado no BRNET"
                                    : "Em quarentena"}
                                </span>
                              </td>
                              <td className="px-6 py-4 text-sm text-gray-600">
                                {parent.variation_count}
                              </td>
                              <td className="px-6 py-4 text-sm space-x-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => abrirDetalhe(parent)}
                                >
                                  {expandido === parent.id ? "Fechar" : "Variações"}
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => abrirEdicao(parent)}
                                >
                                  Editar
                                </Button>
                              </td>
                            </tr>

                            {expandido === parent.id && (
                              <tr className="bg-gray-50">
                                <td colSpan={4} className="px-6 py-4">
                                  {!detalhe ? (
                                    <p className="text-sm text-gray-500">
                                      Carregando variações...
                                    </p>
                                  ) : (
                                    <div className="space-y-3">
                                      {detalhe.variations.length === 0 ? (
                                        <p className="text-sm text-gray-500">
                                          Nenhuma variação cadastrada.
                                        </p>
                                      ) : (
                                        <ul className="space-y-1">
                                          {detalhe.variations.map((variacao) => (
                                            <li
                                              key={variacao.id}
                                              className="flex items-center gap-2 text-sm"
                                            >
                                              <span className="flex-1">
                                                {variacao.name}
                                                {variacao.occurrences != null && (
                                                  <span className="ml-2 text-xs text-gray-500">
                                                    {variacao.occurrences} ocorrência
                                                    {variacao.occurrences === 1 ? "" : "s"}
                                                  </span>
                                                )}
                                              </span>
                                              <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() =>
                                                  removerVariacao(variacao.id, parent.id)
                                                }
                                              >
                                                Remover
                                              </Button>
                                            </li>
                                          ))}
                                        </ul>
                                      )}

                                      <div className="pt-3 border-t space-y-2">
                                        <Label className="text-xs text-gray-500">
                                          Novas variações
                                        </Label>
                                        <div className="max-w-md">
                                          <CamposVariacao
                                            valores={novasVariacoes}
                                            erros={errosVariacao}
                                            onChange={(valores) => {
                                              setNovasVariacoes(valores);
                                              setErrosVariacao([]);
                                            }}
                                            disabled={adicionandoVariacoes}
                                          />
                                        </div>
                                        <Button
                                          size="sm"
                                          onClick={() => adicionarVariacoes(parent.id)}
                                          disabled={
                                            adicionandoVariacoes ||
                                            novasVariacoes.every((v) => !v.trim())
                                          }
                                        >
                                          {adicionandoVariacoes
                                            ? "Salvando..."
                                            : "Salvar variações"}
                                        </Button>
                                      </div>
                                    </div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              /* Conflitos de importação */
              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-sm text-gray-600 mb-4">
                  Termos que a importação viu sob mais de um exame pai, ou que já
                  existem como pai. Nenhuma escolha automática foi feita: cada um
                  espera decisão. Atribuir cria a variação sob o pai escolhido;
                  descartar apenas encerra o conflito.
                </p>

                {conflitos.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    Nenhum conflito aberto.
                  </p>
                ) : (
                  <ul className="space-y-4">
                    {conflitos.map((conflito) => (
                      <li
                        key={conflito.id}
                        className="border rounded-lg p-4 space-y-3"
                      >
                        <div>
                          <div className="font-medium text-sm">{conflito.name}</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            <span className="text-xs text-gray-500 mr-1">
                              candidatos:
                            </span>
                            {conflito.candidate_parents.map((nome) => (
                              <Badge key={nome} variant="outline" className="text-xs">
                                {nome}
                              </Badge>
                            ))}
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <Select
                            value={escolhaConflito[conflito.id] || ""}
                            onValueChange={(valor) =>
                              setEscolhaConflito((atual) => ({
                                ...atual,
                                [conflito.id]: valor,
                              }))
                            }
                          >
                            <SelectTrigger className="w-[340px]">
                              <SelectValue placeholder="Escolha o exame pai..." />
                            </SelectTrigger>
                            <SelectContent>
                              {paisOrdenados.map((pai) => (
                                <SelectItem key={pai.id} value={pai.id}>
                                  {pai.name}
                                  {conflito.candidate_parents.some(
                                    (nome) =>
                                      nome.toLowerCase() === pai.name.toLowerCase()
                                  )
                                    ? "  ← candidato"
                                    : ""}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Button
                            size="sm"
                            onClick={() => resolverConflito(conflito, "atribuida")}
                          >
                            Atribuir
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => resolverConflito(conflito, "descartada")}
                          >
                            Descartar termo
                          </Button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </main>
        </SidebarInset>

        {/* Modal: novo exame */}
        <Dialog open={modalCriar} onOpenChange={setModalCriar}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo Exame</DialogTitle>
              <DialogDescription>
                O nome do exame pai deve ser o mesmo que o BRNET usa — é por ele que
                a comparação acontece.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <Label htmlFor="nome">Nome do exame pai</Label>
                <Input
                  id="nome"
                  placeholder="ex: TGP (ALT)"
                  value={formNome}
                  onChange={(e) => setFormNome(e.target.value)}
                />
              </div>

              <div>
                <Label htmlFor="status">Status</Label>
                <Select
                  value={formStatus}
                  onValueChange={(v) => setFormStatus(v as typeof formStatus)}
                >
                  <SelectTrigger id="status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ativo">Confirmado no BRNET</SelectItem>
                    <SelectItem value="quarentena">Em quarentena</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-500 mt-1">
                  Só exame confirmado no BRNET vale como canônico na comparação.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="externo"
                  type="checkbox"
                  checked={formExterno}
                  onChange={(e) => setFormExterno(e.target.checked)}
                  className="h-4 w-4"
                />
                <Label htmlFor="externo" className="font-normal">
                  Exame realizado externamente
                </Label>
              </div>

              <div>
                <Label>Variações</Label>
                <div className="mt-2">
                  <CamposVariacao
                    valores={formVariacoes}
                    onChange={setFormVariacoes}
                    disabled={salvando}
                  />
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Campos vazios são ignorados. Enter abre o próximo.
                </p>
              </div>

              <div>
                <Label htmlFor="notas">Observações</Label>
                <Textarea
                  id="notas"
                  rows={2}
                  value={formNotas}
                  onChange={(e) => setFormNotas(e.target.value)}
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setModalCriar(false)}
                disabled={salvando}
              >
                Cancelar
              </Button>
              <Button onClick={criarExame} disabled={salvando || !formNome.trim()}>
                {salvando ? "Criando..." : "Criar Exame"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Modal: editar exame */}
        <Dialog open={modalEditar} onOpenChange={setModalEditar}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Editar Exame</DialogTitle>
              <DialogDescription>
                Renomear o exame pai muda a chave de comparação do catálogo.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <Label htmlFor="edit-nome">Nome do exame pai</Label>
                <Input
                  id="edit-nome"
                  value={formNome}
                  onChange={(e) => setFormNome(e.target.value)}
                />
              </div>

              <div>
                <Label htmlFor="edit-status">Status</Label>
                <Select
                  value={formStatus}
                  onValueChange={(v) => setFormStatus(v as typeof formStatus)}
                >
                  <SelectTrigger id="edit-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ativo">Confirmado no BRNET</SelectItem>
                    <SelectItem value="quarentena">Em quarentena</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="edit-externo"
                  type="checkbox"
                  checked={formExterno}
                  onChange={(e) => setFormExterno(e.target.checked)}
                  className="h-4 w-4"
                />
                <Label htmlFor="edit-externo" className="font-normal">
                  Exame realizado externamente
                </Label>
              </div>

              <div>
                <Label htmlFor="edit-notas">Observações</Label>
                <Textarea
                  id="edit-notas"
                  rows={2}
                  value={formNotas}
                  onChange={(e) => setFormNotas(e.target.value)}
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setModalEditar(false)}
                disabled={salvando}
              >
                Cancelar
              </Button>
              <Button onClick={salvarEdicao} disabled={salvando || !formNome.trim()}>
                {salvando ? "Salvando..." : "Salvar"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </SidebarProvider>
    </RequireRole>
  );
}
