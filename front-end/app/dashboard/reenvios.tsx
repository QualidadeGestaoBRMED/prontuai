"use client";

/**
 * Clínicas que reenviam prontuário (STC-827). O reenvio — de prontuário já
 * liberado ou ainda em revisão — não entra na Checagem; sem este card ninguém
 * o veria, e a operação não saberia com quem conversar. Busca própria, fora do
 * cálculo diário do painel: conta até agora, não até as 7h.
 */
import { useEffect, useState } from "react";

import { authFetch } from "@/lib/auth-fetch";
import { API_ENDPOINTS } from "@/lib/config";
import { dataCurta } from "@/lib/reenvio";

import type { IdIndicador } from "./metricas";

const CARTAO = "rounded-[14px] border border-[#DFE0E2] bg-white";
const TITULO = "text-[16.5px] font-semibold text-[#193B4F]";
const SUB = "mt-[5px] text-[13px] text-[#767A7B]";
const CABECALHO = "text-[11.5px] font-medium uppercase tracking-[0.06em] text-[#767A7B]";
const DIAS = 30;
const LINHAS_VISIVEIS = 10;

type LinhaReenvio = {
  clinic_id: string;
  clinica: string | null;
  envios: number;
  reenvios: number;
  em_revisao: number;
  complementos: number;
  ultimo: string | null;
};

export function CartaoReenvios({ onAjuda }: { onAjuda: (id: IdIndicador) => void }) {
  const [linhas, setLinhas] = useState<LinhaReenvio[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [todas, setTodas] = useState(false);

  useEffect(() => {
    let cancelado = false;
    authFetch(API_ENDPOINTS.REENVIOS_POR_CLINICA(DIAS))
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error("Não foi possível carregar os reenvios.");
        return (await resposta.json()) as { clinicas: LinhaReenvio[] };
      })
      .then((corpo) => !cancelado && setLinhas(corpo.clinicas ?? []))
      .catch((e: unknown) => !cancelado && setErro(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelado = true;
    };
  }, []);

  const total = (linhas ?? []).reduce((soma, l) => soma + l.reenvios, 0);
  const maior = Math.max(1, ...(linhas ?? []).map((l) => l.reenvios));
  const visiveis = todas ? linhas ?? [] : (linhas ?? []).slice(0, LINHAS_VISIVEIS);

  return (
    <div className={`${CARTAO} px-[22px] pt-5 pb-5`}>
      <div className="flex items-center gap-2.5">
        <div className={TITULO}>Clínicas para orientar sobre reenvio</div>
        <button
          type="button"
          onClick={() => onAjuda("reenvios")}
          aria-label='Como "Clínicas para orientar sobre reenvio" é calculado'
          title="Como é calculado"
          className="size-[17px] flex-none rounded-full border border-[#7EBFCC] bg-[#E8F2F4] text-[11px] font-semibold leading-[15px] text-[#007891] transition-colors hover:bg-[#D3E9EE]"
        >
          ?
        </button>
      </div>
      <div className={SUB}>
        {erro
          ? erro
          : linhas === null
            ? "Carregando…"
            : linhas.length === 0
              ? `Nenhum reenvio nos últimos ${DIAS} dias`
              : `${total} ${total === 1 ? "reenvio" : "reenvios"} em ${linhas.length} ${linhas.length === 1 ? "clínica" : "clínicas"} nos últimos ${DIAS} dias · não entraram na Checagem`}
      </div>

      {visiveis.length > 0 && (
        <div className="mt-4">
          <div className={`grid grid-cols-[minmax(0,1.6fr)_minmax(0,1.4fr)_70px_80px_90px] gap-3 border-b border-[#EEF0F1] pb-2 ${CABECALHO}`}>
            <span>Clínica</span>
            <span>Reenvios</span>
            <span className="text-right">Envios</span>
            <span className="text-right">% reenvio</span>
            <span className="text-right">Último</span>
          </div>
          <ul>
            {visiveis.map((l) => (
              <li
                key={l.clinic_id}
                className="grid grid-cols-[minmax(0,1.6fr)_minmax(0,1.4fr)_70px_80px_90px] items-center gap-3 border-b border-[#F3F3F3] py-2.5 text-[13.5px] text-[#193B4F]"
              >
                <span className="truncate" title={l.clinica ?? undefined}>
                  {l.clinica ?? "Clínica sem nome"}
                </span>
                <span className="flex items-center gap-2" title={`${l.reenvios - l.em_revisao} de prontuário já liberado · ${l.em_revisao} de prontuário ainda em revisão · ${l.complementos} devolvidos como complemento`}>
                  <span className="relative h-[8px] flex-1 overflow-hidden rounded-full bg-[#EEF0F1]">
                    <span
                      className="absolute inset-y-0 left-0 rounded-full bg-[#007891]"
                      style={{ width: `${(l.reenvios / maior) * 100}%` }}
                    />
                  </span>
                  <span className="w-8 text-right font-medium tabular-nums">{l.reenvios}</span>
                </span>
                <span className="text-right tabular-nums text-[#767A7B]">{l.envios}</span>
                <span className="text-right tabular-nums">
                  {l.envios ? `${Math.round((l.reenvios / l.envios) * 100)}%` : "—"}
                </span>
                <span className="text-right tabular-nums text-[#767A7B]">{dataCurta(l.ultimo)}</span>
              </li>
            ))}
          </ul>
          {(linhas?.length ?? 0) > LINHAS_VISIVEIS && (
            <button
              type="button"
              onClick={() => setTodas((v) => !v)}
              className="mt-3 text-[13px] font-medium text-[#007891] hover:underline"
            >
              {todas ? "Ver só as 10 primeiras" : `Ver todas as ${linhas?.length} clínicas`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
