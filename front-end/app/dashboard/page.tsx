"use client";

import { useMemo, useState } from "react";
import { RiBarChartBoxLine, RiRefreshLine } from "@remixicon/react";

import { AppSidebar } from "@/components/app-sidebar";
import { RequireRole } from "@/components/require-role";
import UserDropdown from "@/components/user-dropdown";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

import { AbaAcuracia, AbaUtilizacao } from "./abas";
import { useDadosDashboard } from "./dados";
import {
  ABAS,
  AJUDA_ACURACIA,
  ORDEM_FILTROS,
  ROTULO_FILTRO,
  calcularVisao,
  type Aba,
  type FiltroPeriodo,
} from "./metricas";

/**
 * "Última atualização às 7:00". O horário é o `gerado_em` do back-end — muda
 * tanto na rotina das 7h quanto no botão "Atualizar", então o texto acompanha
 * o que foi apertado sem nenhum estado extra aqui.
 *
 * Fora do dia de hoje o texto ganha a data: antes das 7h o número na tela
 * ainda é o de ontem, e "às 7:00" sozinho sugeriria o de hoje.
 */
function textoUltimaAtualizacao(data: Date): string {
  const hora = data.toLocaleTimeString("pt-BR", { hour: "numeric", minute: "2-digit" });
  const dia = (d: Date) => d.toLocaleDateString("pt-BR");
  const hoje = new Date();
  const ontem = new Date(hoje);
  ontem.setDate(hoje.getDate() - 1);

  if (dia(data) === dia(hoje)) return `Última atualização às ${hora}`;
  if (dia(data) === dia(ontem)) return `Última atualização ontem às ${hora}`;
  const dataCurta = data.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  return `Última atualização em ${dataCurta} às ${hora}`;
}

export default function DashboardPage() {
  const [aba, setAba] = useState<Aba>("utilizacao");
  const [filtro, setFiltro] = useState<FiltroPeriodo>("Mensal");
  const [comparar, setComparar] = useState(true);
  const [verTodas, setVerTodas] = useState(false);
  const [ajudaAberta, setAjudaAberta] = useState(false);

  const {
    dados,
    geradoEm,
    carregando,
    atualizando,
    erro,
    recarregar,
  } = useDadosDashboard();

  const visao = useMemo(
    () => (dados ? calcularVisao({ dados, filtro, comparar, verTodasClinicas: verTodas }) : null),
    [dados, filtro, comparar, verTodas],
  );

  return (
    <RequireRole allowedRoles={["ADMIN", "MANAGER"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar group/sidebar-inset">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <div className="flex items-center gap-2">
              <RiBarChartBoxLine className="size-5" />
              <h1 className="text-lg font-semibold">Dashboard</h1>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <UserDropdown />
            </div>
          </header>

          <div className="flex-1 overflow-auto bg-[#F3F3F3] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
            <div className="flex flex-col text-[#193B4F]">
              {/* título, filtro de período e comparação */}
              <div className="flex flex-wrap items-end justify-between gap-7 px-[34px] pt-[30px]">
                <div>
                  <div className="text-[11px] font-semibold tracking-[0.15em] text-[#767A7B]">
                    PRONTUAI
                  </div>
                  <h2 className="mt-[7px] text-[30px] font-semibold tracking-[-0.01em] text-[#193B4F]">
                    Dashboard de Indicadores
                  </h2>
                  <div className="mt-[7px] text-sm text-[#767A7B]">
                    {visao
                      ? `${visao.rangeLabel} · comparado com ${visao.compareLabel}`
                      : carregando
                        ? "carregando indicadores…"
                        : "sem dados"}
                  </div>
                  {geradoEm && (
                    <div className="mt-1.5 text-[12.5px] text-[#767A7B]">
                      {textoUltimaAtualizacao(geradoEm)}
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2.5">
                  <div className="flex gap-0.5 rounded-[10px] border border-[#DFE0E2] bg-white p-1">
                    {ORDEM_FILTROS.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => setFiltro(id)}
                        className={`rounded-[7px] px-[15px] py-2 text-[13px] font-medium transition-colors ${
                          filtro === id ? "bg-[#193B4F] text-white" : "text-[#767A7B] hover:bg-[#F3F3F3]"
                        }`}
                      >
                        {ROTULO_FILTRO(id)}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-[9px] rounded-[10px] border border-[#DFE0E2] bg-white px-[15px] py-2.5 text-[13.5px] text-[#193B4F]">
                    <div className="size-[7px] rounded-full bg-[#00AFAA]" />
                    {visao?.chipPeriodo ?? "—"}
                  </div>

                  <button
                    type="button"
                    onClick={() => setComparar((v) => !v)}
                    aria-pressed={comparar}
                    className={`flex items-center gap-2.5 rounded-[10px] border px-[15px] py-2.5 text-[13.5px] transition-colors ${
                      comparar
                        ? "border-[#7EBFCC] bg-[#E8F2F4] text-[#193B4F]"
                        : "border-[#DFE0E2] bg-white text-[#767A7B]"
                    }`}
                  >
                    <span
                      className={`flex h-4 w-[30px] rounded-[9px] p-0.5 ${
                        comparar ? "justify-end bg-[#007891]" : "justify-start bg-[#BFC3C6]"
                      }`}
                    >
                      <span className="size-3 rounded-full bg-white" />
                    </span>
                    Comparar períodos
                  </button>

                  <button
                    type="button"
                    onClick={() => recarregar(true)}
                    disabled={atualizando || carregando}
                    title="Recalcula agora, sem esperar a atualização automática"
                    className="flex items-center gap-2 rounded-[10px] bg-[#193B4F] px-4 py-2.5 text-[13.5px] font-medium text-white transition-colors hover:bg-[#007891] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <RiRefreshLine
                      size={16}
                      aria-hidden="true"
                      className={atualizando ? "animate-spin" : undefined}
                    />
                    {atualizando ? "Atualizando…" : "Atualizar"}
                  </button>
                </div>
              </div>

              {/* abas */}
              <div className="mt-[22px] flex gap-[26px] border-b border-[#DFE0E2] px-[34px] pt-6">
                {ABAS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setAba(t.id)}
                    className={`border-b-[2.5px] px-0.5 pb-[13px] text-[15px] font-medium ${
                      aba === t.id
                        ? "border-[#007891] text-[#193B4F]"
                        : "border-transparent text-[#767A7B]"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {erro && (
                <div className="mx-[34px] mt-6 rounded-[14px] border border-[#E7C3BE] bg-[#FBF0EE] px-[22px] py-5">
                  <div className="text-[15px] font-semibold text-[#B4453A]">
                    Não foi possível carregar os indicadores
                  </div>
                  <div className="mt-1.5 text-[13px] text-[#767A7B]">{erro}</div>
                  <button
                    type="button"
                    onClick={() => recarregar(true)}
                    className="mt-3.5 rounded-[9px] bg-[#193B4F] px-4 py-2 text-[13px] font-medium text-white"
                  >
                    Tentar de novo
                  </button>
                </div>
              )}

              {!erro && carregando && !visao && (
                <div className="px-[34px] py-14 text-[13px] text-[#767A7B]">
                  Calculando indicadores do ambiente…
                </div>
              )}

              {visao && (
                <>
                  {aba === "utilizacao" && (
                    <AbaUtilizacao
                      visao={visao}
                      verTodas={verTodas}
                      onVerTodas={() => setVerTodas((v) => !v)}
                    />
                  )}
                  {aba === "acuracia" && (
                    <AbaAcuracia visao={visao} onAjuda={() => setAjudaAberta(true)} />
                  )}
                </>
              )}
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>

      <Dialog open={ajudaAberta} onOpenChange={setAjudaAberta}>
        <DialogContent className="max-h-[82vh] overflow-y-auto sm:max-w-[620px]">
          <DialogHeader>
            <DialogTitle>Como a acurácia é calculada</DialogTitle>
            <DialogDescription>
              Concordância entre a decisão da IA e a do revisor humano
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col">
            {AJUDA_ACURACIA.map((b) => (
              <div key={b.titulo} className="border-b border-[#F3F3F3] py-4 last:border-b-0">
                <div className="text-sm font-semibold text-[#193B4F]">{b.titulo}</div>
                <div className="mt-1.5 text-[13.5px] leading-[1.6] text-[#4A5560]">{b.texto}</div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </RequireRole>
  );
}
