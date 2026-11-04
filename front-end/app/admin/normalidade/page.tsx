"use client";

/**
 * O que o ProntuAI lê nos laudos de laboratório.
 *
 * É só leitura: desde a reunião com a Saúde de 28/10/2026 não se cadastra faixa de
 * referência. Normal ou alterado segue a faixa que o laboratório imprimiu em cada
 * laudo, e por isso a mesma tela não mostra faixa nenhuma.
 */

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AppSidebar } from "@/components/app-sidebar";
import { RequireRole } from "@/components/require-role";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import UserDropdown from "@/components/user-dropdown";
import { authFetch } from "@/lib/auth-fetch";
import { API_ENDPOINTS } from "@/lib/config";
import { ParametroLeitura } from "@/types/normalidade";

export default function NormalidadePage() {
  const [parametros, setParametros] = useState<ParametroLeitura[]>([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let ativo = true;
    (async () => {
      try {
        const resposta = await authFetch(API_ENDPOINTS.NORMALIDADE_PARAMETROS);
        if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
        const lista: ParametroLeitura[] = await resposta.json();
        if (ativo) setParametros(lista);
      } catch {
        if (ativo) toast.error("Erro ao carregar os parâmetros de normalidade");
      } finally {
        if (ativo) setCarregando(false);
      }
    })();
    return () => {
      ativo = false;
    };
  }, []);

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
              <h2 className="text-2xl font-bold text-white">Parâmetros lidos nos laudos</h2>
              <p className="text-sm text-white/80 mt-1 max-w-3xl">
                O ProntuAI lê o resultado destes parâmetros e a faixa de referência impressa pelo laboratório no mesmo
                laudo. Fora dela, o exame aparece como alterado na coluna Normalidade da Comparação Detalhada. Quando a
                faixa não pode ser lida com segurança, o valor aparece como &quot;Sem referência&quot; e nada é classificado.
              </p>
            </div>

            <div className="bg-white rounded-lg shadow overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    {["Parâmetro", "Unidade", "Como é avaliado"].map((t) => (
                      <th key={t} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase whitespace-nowrap">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {carregando
                    ? Array.from({ length: 6 }).map((_, i) => (
                        <tr key={i} className="animate-pulse">
                          <td colSpan={3} className="px-6 py-4"><div className="h-4 bg-gray-200 rounded w-2/3" /></td>
                        </tr>
                      ))
                    : parametros.map((p) => (
                        <tr key={p.parametro} className="hover:bg-gray-50">
                          <td className="px-6 py-3 text-sm font-medium whitespace-nowrap">{p.nome}</td>
                          <td className="px-6 py-3 text-sm text-gray-500 whitespace-nowrap">{p.unidade || "—"}</td>
                          <td className="px-6 py-3 text-sm text-gray-600">
                            {p.qualitativo
                              ? `Qualitativo: ${p.normal_texto ?? "sem critério"} é normal`
                              : "Faixa impressa no laudo"}
                          </td>
                        </tr>
                      ))}
                </tbody>
              </table>
            </div>
          </main>
        </SidebarInset>
      </SidebarProvider>
    </RequireRole>
  );
}
