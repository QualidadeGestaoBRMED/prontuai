"use client";

/**
 * Faixas de referência da normalidade de exames.
 *
 * Cada parâmetro (glicose, HbA1c, hemoglobina...) tem uma faixa padrão no
 * back-end; aqui a gestão ajusta a faixa em vigor ou volta ao padrão. O ajuste
 * vale na hora, inclusive para documentos já processados: a coluna
 * "Normalidade" da checagem é calculada quando o documento é aberto.
 *
 * Quem checa vê a tela; só ADMIN e MANAGER editam (`require_management` no back).
 */

import { useCallback, useEffect, useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";

import { AppSidebar } from "@/components/app-sidebar";
import { RequireRole } from "@/components/require-role";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import UserDropdown from "@/components/user-dropdown";
import { usePermissions } from "@/hooks/usePermissions";
import { authFetch } from "@/lib/auth-fetch";
import { API_ENDPOINTS } from "@/lib/config";
import { FaixaNormalidade } from "@/types/normalidade";

type Rascunho = { minimo: string; maximo: string };

/** "0,7" → 0.7; "150.000" → 150000; vazio → null; texto inválido → NaN. */
function lerNumero(texto: string): number | null {
  const t = texto.trim();
  if (!t) return null;
  if (t.includes(",")) return Number(t.replace(/\./g, "").replace(",", "."));
  if (/^\d{1,3}(\.\d{3})+$/.test(t)) return Number(t.replace(/\./g, ""));
  return Number(t);
}

function mostrarNumero(n: number | null): string {
  return n === null ? "" : n.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

async function mensagemDeErro(resposta: Response, padrao: string): Promise<string> {
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
    if (Array.isArray(corpo?.detail) && corpo.detail[0]?.msg) return String(corpo.detail[0].msg).replace(/^Value error, /, "");
  } catch {}
  return padrao;
}

export default function NormalidadePage() {
  const { isManagement } = usePermissions();
  const [faixas, setFaixas] = useState<FaixaNormalidade[]>([]);
  const [rascunhos, setRascunhos] = useState<Record<string, Rascunho>>({});
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState<string | null>(null);

  const aplicar = (lista: FaixaNormalidade[]) => {
    setFaixas(lista);
    setRascunhos(Object.fromEntries(lista.map((f) => [f.parametro, { minimo: mostrarNumero(f.minimo), maximo: mostrarNumero(f.maximo) }])));
  };

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const resposta = await authFetch(API_ENDPOINTS.NORMALIDADE_FAIXAS);
      if (!resposta.ok) throw new Error(await mensagemDeErro(resposta, "Erro ao carregar as faixas"));
      aplicar(await resposta.json());
    } catch (erro) {
      toast.error(erro instanceof Error ? erro.message : "Erro ao carregar as faixas");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const substituir = (nova: FaixaNormalidade) => {
    aplicar(faixas.map((f) => (f.parametro === nova.parametro ? nova : f)));
  };

  const salvar = async (f: FaixaNormalidade) => {
    const r = rascunhos[f.parametro];
    const minimo = lerNumero(r.minimo);
    const maximo = lerNumero(r.maximo);
    if (Number.isNaN(minimo) || Number.isNaN(maximo)) return toast.error("Use só números, com vírgula para decimal.");
    setSalvando(f.parametro);
    try {
      const resposta = await authFetch(API_ENDPOINTS.NORMALIDADE_FAIXA(f.parametro), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minimo, maximo }),
      });
      if (!resposta.ok) return toast.error(await mensagemDeErro(resposta, "Erro ao salvar a faixa"));
      const nova: FaixaNormalidade = await resposta.json();
      substituir(nova);
      toast.success(`${nova.nome}: faixa salva (${nova.referencia})`);
    } finally {
      setSalvando(null);
    }
  };

  const restaurar = async (f: FaixaNormalidade) => {
    setSalvando(f.parametro);
    try {
      const resposta = await authFetch(API_ENDPOINTS.NORMALIDADE_FAIXA(f.parametro), { method: "DELETE" });
      if (!resposta.ok) return toast.error(await mensagemDeErro(resposta, "Erro ao restaurar a faixa"));
      const nova: FaixaNormalidade = await resposta.json();
      substituir(nova);
      toast.success(`${nova.nome}: faixa padrão restaurada (${nova.referencia})`);
    } finally {
      setSalvando(null);
    }
  };

  const mudou = (f: FaixaNormalidade) => {
    const r = rascunhos[f.parametro];
    return r && (lerNumero(r.minimo) !== f.minimo || lerNumero(r.maximo) !== f.maximo);
  };

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER", "CHECKER", "CURATOR"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground" />
            <h1 className="text-lg font-semibold">Normalidade de Exames</h1>
            <div className="ml-auto">
              <UserDropdown />
            </div>
          </header>

          <main className="p-4 md:p-6 lg:p-8">
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-white">Faixas de referência</h2>
              <p className="text-sm text-white/80 mt-1 max-w-3xl">
                O ProntuAI lê o resultado destes parâmetros nos laudos de laboratório e compara com a faixa abaixo.
                Fora dela, o exame aparece como alterado na coluna Normalidade da Comparação Detalhada, na checagem.
                A mudança vale na hora, inclusive para documentos já processados.
                {!isManagement && " Só administradores e gestores alteram as faixas."}
              </p>
            </div>

            <div className="bg-white rounded-lg shadow overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    {["Parâmetro", "Mínimo", "Máximo", "Unidade", "Faixa em vigor", "Última alteração", ""].map((t) => (
                      <th key={t} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase whitespace-nowrap">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {carregando ? (
                    Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i} className="animate-pulse">
                        <td colSpan={7} className="px-6 py-4"><div className="h-4 bg-gray-200 rounded w-2/3" /></td>
                      </tr>
                    ))
                  ) : (
                    faixas.map((f) => (
                      <tr key={f.parametro} className="hover:bg-gray-50">
                        <td className="px-6 py-3 text-sm font-medium whitespace-nowrap">{f.nome}</td>
                        {f.qualitativo ? (
                          <td colSpan={2} className="px-6 py-3 text-sm text-gray-500">
                            Qualitativo: reagente ou positivo é alterado
                          </td>
                        ) : (
                          (["minimo", "maximo"] as const).map((lado) => (
                            <td key={lado} className="px-6 py-3">
                              <Input
                                value={rascunhos[f.parametro]?.[lado] ?? ""}
                                onChange={(e) =>
                                  setRascunhos((atual) => ({ ...atual, [f.parametro]: { ...atual[f.parametro], [lado]: e.target.value } }))
                                }
                                disabled={!isManagement || salvando === f.parametro}
                                placeholder="—"
                                inputMode="decimal"
                                aria-label={`${f.nome}: ${lado === "minimo" ? "mínimo" : "máximo"}`}
                                className="w-28 text-right tabular-nums"
                              />
                            </td>
                          ))
                        )}
                        <td className="px-6 py-3 text-sm text-gray-500 whitespace-nowrap">{f.unidade || "—"}</td>
                        <td className="px-6 py-3 text-sm whitespace-nowrap">
                          {f.referencia}
                          {f.ajustada && (
                            <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-sky-100 text-sky-800">ajustada</span>
                          )}
                        </td>
                        <td className="px-6 py-3 text-xs text-gray-500">
                          {f.ajustada && f.atualizado_em ? (
                            <>
                              {f.atualizado_por_nome || f.atualizado_por_email}
                              <br />
                              {format(new Date(f.atualizado_em), "dd/MM/yyyy HH:mm", { locale: ptBR })}
                            </>
                          ) : (
                            "Padrão"
                          )}
                        </td>
                        <td className="px-6 py-3 text-sm whitespace-nowrap space-x-2">
                          {isManagement && !f.qualitativo && (
                            <>
                              <Button size="sm" onClick={() => salvar(f)} disabled={!mudou(f) || salvando === f.parametro}>
                                Salvar
                              </Button>
                              {f.ajustada && (
                                <Button size="sm" variant="outline" onClick={() => restaurar(f)} disabled={salvando === f.parametro}>
                                  Restaurar padrão
                                </Button>
                              )}
                            </>
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
      </SidebarProvider>
    </RequireRole>
  );
}
