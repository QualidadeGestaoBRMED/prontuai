"use client";

/**
 * As três abas do dashboard. Recebem a visão já calculada por `metricas.ts` —
 * aqui só tem layout. As medidas (tamanhos de fonte quebrados, alturas de
 * barra) vêm do protótipo aprovado e são intencionais.
 */
import { useState } from "react";

import type {
  BarraPercentual,
  GraficoPrazo,
  Kpi,
  LinhaSemProntuai,
  VisaoDashboard,
} from "./metricas";
import styles from "./dashboard.module.css";

const CARTAO = "rounded-[14px] border border-[#DFE0E2] bg-white";
const TITULO = "text-[16.5px] font-semibold text-[#193B4F]";
const SUB = "mt-[5px] text-[13px] text-[#767A7B]";
const CABECALHO_TABELA =
  "text-[11.5px] font-medium uppercase tracking-[0.06em] text-[#767A7B]";
const COLUNAS_SEM_PRONTUAI = "grid-cols-[2fr_1.3fr_0.9fr_1.3fr]";

/**
 * Linha da lista de credenciados fora do ProntuAI, com as datas previstas num
 * painel que abre. A quebra por dia já esteve num balão de hover: com meia
 * dúzia de datas virava um parágrafo, ilegível. Aqui cada data é uma linha.
 */
function LinhaClinica({ c }: { c: LinhaSemProntuai }) {
  const [aberta, setAberta] = useState(false);
  return (
    <div className="border-b border-[#F3F3F3]">
      <button
        type="button"
        onClick={() => setAberta((v) => !v)}
        aria-expanded={aberta}
        className={`grid w-full ${COLUNAS_SEM_PRONTUAI} items-center gap-x-[18px] rounded-[6px] px-1 py-3 text-left text-[13.5px] text-[#193B4F] transition-colors hover:bg-[#F7F9FA]`}
      >
        <div className="flex min-w-0 items-center gap-2">
          <svg
            viewBox="0 0 16 16"
            aria-hidden="true"
            className={`size-3.5 flex-none text-[#767A7B] transition-transform ${aberta ? "rotate-90" : ""}`}
          >
            <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="truncate">{c.name}</span>
        </div>
        <div className="min-w-0 truncate text-[#767A7B]">{c.local}</div>
        <div className="font-medium tabular-nums">{c.pedidos}</div>
        <div className="tabular-nums">{c.proxima}</div>
      </button>

      {aberta && (
        <div className="mb-3 ml-[26px] mr-1 rounded-[10px] border border-[#DFE0E2] bg-[#FAFBFC] px-4 py-3">
          <div className={CABECALHO_TABELA}>Datas das previsões</div>
          <div className="mt-2.5 flex flex-col">
            {c.datas.map((d) => (
              <div
                key={d.label}
                className="flex items-baseline justify-between gap-6 border-b border-[#EDEFF0] py-[7px] text-[13px] last:border-b-0"
              >
                <span className="text-[#5F6B72]">{d.label}</span>
                <span className="font-medium tabular-nums text-[#193B4F]">{d.pedidos}</span>
              </div>
            ))}
          </div>
          <div className="mt-2.5 text-[12.5px] text-[#767A7B]">{c.resumo}</div>
          <div className="mt-1 text-[12px] text-[#9AA3A8]">{c.credenciado}</div>
        </div>
      )}
    </div>
  );
}

function CartaoKpi({ kpi, onAjuda }: { kpi: Kpi; onAjuda?: () => void }) {
  return (
    <div
      className={`${styles.tip} ${styles.tipBaixo} flex flex-col gap-4 rounded-xl border border-[#DFE0E2] bg-white px-[22px] pt-5 pb-[22px]`}
      data-tip={kpi.tip}
    >
      <div className="flex items-center gap-2">
        <div className="text-[13px] text-[#767A7B]">{kpi.label}</div>
        {kpi.temAjuda && (
          <button
            type="button"
            onClick={onAjuda}
            aria-label="Como a acurácia é calculada"
            className="size-[17px] flex-none rounded-full border border-[#7EBFCC] bg-[#E8F2F4] text-[11px] font-semibold leading-[15px] text-[#007891]"
          >
            ?
          </button>
        )}
      </div>
      <div className="flex flex-col items-start gap-2">
        <div className="whitespace-nowrap text-[36px] font-medium leading-none tracking-[-0.025em] text-[#193B4F] tabular-nums">
          {kpi.value}
        </div>
        <div className="whitespace-nowrap text-[13px] font-medium" style={{ color: kpi.deltaColor }}>
          {kpi.delta}
        </div>
        <div className="text-[12.5px] text-[#767A7B]">{kpi.sub}</div>
      </div>
    </div>
  );
}

/**
 * Barras empilhadas de prazo contra a previsão do BRNET. Usado duas vezes: a
 * clínica (envio) e o técnico de credenciados (liberação) são medidos à parte
 * para o atraso de um não cair na conta do outro.
 */
function CartaoPrazo({ titulo, sub, grafico }: { titulo: string; sub: string; grafico: GraficoPrazo }) {
  return (
    <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <div className={TITULO}>{titulo}</div>
          <div className={SUB}>{sub}</div>
          {grafico.resumo && (
            <div className="mt-1.5 text-[13px] font-medium text-[#193B4F]">{grafico.resumo}</div>
          )}
        </div>
        <div className="flex shrink-0 gap-3 text-xs text-[#767A7B]">
          <div className="flex items-center gap-1.5 whitespace-nowrap">
            <div className="size-2.5 rounded-[2px] bg-[#7EBFCC]" />
            Antecipado
          </div>
          <div className="flex items-center gap-1.5 whitespace-nowrap">
            <div className="size-2.5 rounded-[2px] bg-[#00AFAA]" />
            No dia
          </div>
          <div className="flex items-center gap-1.5 whitespace-nowrap">
            <div className="size-2.5 rounded-[2px] bg-[#B4453A]" />
            Atrasado
          </div>
        </div>
      </div>
      <div className="mt-[22px] flex h-[220px] items-end gap-[2.6%]">
        {grafico.barras.map((e, i) => (
          <div
            key={`${e.month}-${i}`}
            className={`${styles.tip} flex flex-1 flex-col items-center gap-[7px]`}
            data-tip={e.tip}
          >
            <div className="text-xs font-medium text-[#193B4F]">{e.total}</div>
            <div className="flex w-full flex-col overflow-hidden rounded-[5px]">
              <div className="bg-[#7EBFCC]" style={{ height: `${e.hAnt}px` }} />
              <div className="bg-[#00AFAA]" style={{ height: `${e.hDia}px` }} />
              <div className="bg-[#B4453A]" style={{ height: `${e.hAtr}px` }} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2.5 flex gap-[2.6%]">
        {grafico.barras.map((e, i) => (
          <div key={`${e.month}-${i}`} className="flex-1 text-center text-xs font-medium text-[#767A7B]">
            {e.month}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Gráfico de barras simples com rótulo em cima — usado por cobertura e acurácia. */
function BarrasPercentuais({ series, cor }: { series: BarraPercentual[]; cor: string }) {
  return (
    <>
      <div className="mt-[22px] flex h-[220px] items-end gap-[2.6%]">
        {series.map((k, i) => (
          <div
            key={`${k.month}-${i}`}
            className={`${styles.tip} flex flex-1 flex-col items-center gap-[7px]`}
            data-tip={k.tip}
          >
            <div className="text-xs font-medium text-[#193B4F]">{k.label}</div>
            <div
              className="w-full rounded-t-[5px]"
              style={{ height: `${k.h}px`, background: cor }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2.5 flex gap-[2.6%]">
        {series.map((k, i) => (
          <div key={`${k.month}-${i}`} className="flex-1 text-center text-xs font-medium text-[#767A7B]">
            {k.month}
          </div>
        ))}
      </div>
    </>
  );
}

export function AbaUtilizacao({
  visao,
  verTodas,
  onVerTodas,
}: {
  visao: VisaoDashboard;
  verTodas: boolean;
  onVerTodas: () => void;
}) {
  return (
    <div className="flex flex-col gap-5 px-[34px] pt-[26px] pb-10">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {visao.kpiPrimary.map((k) => (
          <CartaoKpi key={k.label} kpi={k} />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        {/* Documentos enviados: volume por período, em barra */}
        <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
          <div className={TITULO}>Documentos enviados</div>
          <div className={SUB}>{visao.graficoLegenda} · volume · último ponto em andamento</div>

          <div className="relative mt-[22px] h-[268px]">
            <div className="absolute inset-0 flex flex-col justify-between">
              <div className="h-px bg-[#F3F3F3]" />
              <div className="h-px bg-[#F3F3F3]" />
              <div className="h-px bg-[#F3F3F3]" />
              <div className="h-px bg-[#DFE0E2]" />
            </div>
            <div className="absolute inset-0 flex items-end gap-[2.4%]">
              {visao.docsSeries.map((d, i) => (
                <div
                  key={`${d.month}-${i}`}
                  className={`${styles.tip} flex flex-1 flex-col items-center gap-2`}
                  data-tip={d.tip}
                >
                  <div className="rounded-[5px] bg-[#193B4F] px-2 py-[3px] text-xs font-medium text-white">
                    {d.value}
                  </div>
                  <div className="w-full rounded-t-[5px] bg-[#193B4F]" style={{ height: `${d.h}px` }} />
                </div>
              ))}
            </div>
          </div>
          <div className="mt-2.5 flex gap-[2.4%]">
            {visao.docsSeries.map((d, i) => (
              <div key={`${d.month}-${i}`} className="flex-1 text-center text-xs font-medium text-[#767A7B]">
                {d.month}
              </div>
            ))}
          </div>
        </div>

        <div className={`${CARTAO} flex flex-col px-[22px] pt-5 pb-[18px]`}>
          <div className={TITULO}>Ranking de clínicas</div>
          <div className={SUB}>Volume no período selecionado</div>
          <div className="mt-[18px] flex flex-col gap-[13px]">
            {visao.ranking.map((r) => (
              <div key={r.name} className={`${styles.tip} flex flex-col gap-1.5`} data-tip={r.tip}>
                <div className="flex items-baseline justify-between gap-2.5">
                  <div className="text-[13.5px] text-[#193B4F]">{r.name}</div>
                  <div className="flex items-baseline gap-[9px]">
                    <div className="text-[13.5px] font-medium text-[#193B4F]">{r.docs}</div>
                    <div className="text-xs" style={{ color: r.deltaColor }}>
                      {r.delta}
                    </div>
                  </div>
                </div>
                <div className="h-[7px] overflow-hidden rounded-[4px] bg-[#F3F3F3]">
                  <div
                    className="h-full rounded-[4px]"
                    style={{ width: `${r.pct}%`, background: r.color }}
                  />
                </div>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={onVerTodas}
            className="mt-auto pt-4 text-left text-[12.5px] text-[#007891]"
          >
            {verTodas ? "← Ver só as 6 maiores" : `Ver todas as ${visao.totalClinicas} clínicas →`}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <CartaoPrazo
          titulo="Envio da clínica × prazo do credenciado"
          sub={`${visao.graficoLegenda} · prontuário enviado antes, no dia ou depois do prazo da clínica no BRNET`}
          grafico={visao.prazoClinica}
        />
        <CartaoPrazo
          titulo="Liberação do técnico de credenciados × prazo da BR MED"
          sub={`${visao.graficoLegenda} · prazo da BR MED = 1 dia útil após o da clínica · só aprovações do técnico`}
          grafico={visao.prazoTecnico}
        />
      </div>

      <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
        <div className={TITULO}>Cobertura das expedições</div>
        <div className={SUB}>
          % dos pedidos atendidos nas credenciadas que passaram pelo ProntuAI · meta 100%
        </div>
        <BarrasPercentuais series={visao.coberturaSeries} cor="#00AFAA" />
      </div>

      <div className={`${CARTAO} px-[22px] pt-5 pb-2`}>
        <div className={TITULO}>Adoção por clínica</div>
        {/* O rótulo acompanha o "ver todas" do ranking: as duas tabelas leem a
            mesma lista, então dizer "top 6" com 43 linhas na tela seria mentira. */}
        <div className={SUB}>
          {visao.adocao.length === visao.totalClinicas
            ? `Todas as ${visao.totalClinicas} clínicas`
            : `Top ${visao.adocao.length} por volume`}{" "}
          · documentos enviados, revisados e liberados
        </div>
        <div className="mt-4 overflow-x-auto">
          <div className="min-w-[720px]">
            <div
              className={`${CABECALHO_TABELA} grid grid-cols-[2fr_1fr_1fr_1fr_1fr_1.2fr] gap-x-[18px] border-b border-[#DFE0E2] px-1 pb-2.5`}
            >
              <div>Clínica</div>
              <div>Usuários</div>
              <div>Docs</div>
              <div>Revisados</div>
              <div>Liberados</div>
              <div>% liberados</div>
            </div>
            {visao.adocao.map((a) => (
              <div
                key={a.name}
                className={`${styles.linhaTip} grid grid-cols-[2fr_1fr_1fr_1fr_1fr_1.2fr] items-center gap-x-[18px] border-b border-[#F3F3F3] px-1 py-3 text-[13.5px] text-[#193B4F]`}
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <div className="size-2 flex-shrink-0 rounded-full" style={{ background: a.statusColor }} />
                  <span className={`${styles.tip} ${styles.tipNome} min-w-0`} data-tip={a.tip}>
                    <span className="block truncate">{a.name}</span>
                  </span>
                </div>
                <div>{a.users}</div>
                <div>{a.docs}</div>
                <div>{a.reviewed}</div>
                <div>{a.exped}</div>
                <div className="flex items-center gap-2.5">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-[3px] bg-[#F3F3F3]">
                    <div className="h-full rounded-[3px] bg-[#007891]" style={{ width: `${a.pct}%` }} />
                  </div>
                  <div className="w-[42px] text-right font-medium">{a.pctLabel}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={`${CARTAO} px-[22px] pt-5 pb-2`}>
        <div className={TITULO}>Clínicas com expedições previstas fora do ProntuAI</div>
        <div className={SUB}>
          {visao.semProntuai === null
            ? "Lista indisponível: não foi possível consultar o BRNET na última atualização"
            : `${visao.semProntuai.length} credenciadas · ${visao.pedidosSemProntuai} pedidos com previsão de liberação a partir de hoje · menos de 3 documentos no ProntuAI`}
        </div>
        {visao.semProntuai && visao.semProntuai.length > 0 && (
          <div className="mt-4 max-h-[420px] overflow-auto">
            <div className="min-w-[640px]">
              <div
                className={`${CABECALHO_TABELA} sticky top-0 z-10 grid ${COLUNAS_SEM_PRONTUAI} gap-x-[18px] border-b border-[#DFE0E2] bg-white px-1 pb-2.5`}
              >
                <div>Clínica</div>
                <div>Cidade</div>
                <div>Previstos</div>
                <div>Próxima previsão</div>
              </div>
              {visao.semProntuai.map((c) => (
                <LinhaClinica key={`${c.name}-${c.local}`} c={c} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function AbaAcuracia({ visao, onAjuda }: { visao: VisaoDashboard; onAjuda: () => void }) {
  return (
    <div className="flex flex-col gap-5 px-[34px] pt-[26px] pb-10">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {visao.kpisAcuracia.map((k) => (
          <CartaoKpi key={k.label} kpi={k} onAjuda={onAjuda} />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
          <div className={TITULO}>Acurácia por período</div>
          <div className={SUB}>
            {visao.graficoLegenda} · concordância entre IA e revisor · escala a partir de 70%
          </div>
          <BarrasPercentuais series={visao.acuraciaSeries} cor="#007891" />
        </div>

        <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
          <div className="flex items-center gap-2.5">
            <div className={TITULO}>Por que a acurácia não está maior</div>
            <div className="rounded-[5px] bg-[#F7EDDC] px-2 py-1 text-[10.5px] font-medium tracking-[0.08em] text-[#A05E1E]">
              A CONFIRMAR
            </div>
          </div>
          <div className={SUB}>{visao.fatorPrincipal}</div>
          <div className="mt-[18px] flex flex-col gap-[13px]">
            {visao.penteFino.map((p) => (
              <div key={p.name} className={`${styles.tip} flex flex-col gap-1.5`} data-tip={p.tip}>
                <div className="flex items-baseline justify-between gap-2.5">
                  <div className="text-[13.5px] text-[#193B4F]">{p.name}</div>
                  <div className="text-[13px] font-medium text-[#767A7B]">{p.count}</div>
                </div>
                <div className="h-[7px] overflow-hidden rounded-[4px] bg-[#F3F3F3]">
                  <div className="h-full rounded-[4px]" style={{ width: `${p.pct}%`, background: p.color }} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-[18px] rounded-[10px] bg-[#F3F3F3] px-3.5 py-3 text-[12.5px] leading-[1.5] text-[#767A7B]">
            {visao.notaSemJustificativa}
          </div>
        </div>
      </div>

      <div className={`${CARTAO} px-[22px] pt-5 pb-2`}>
        <div className={TITULO}>Matriz de decisão</div>
        <div className={SUB}>Todo desfecho possível entre IA e revisor, no período selecionado</div>
        <div className="mt-4 overflow-x-auto">
          <div className="min-w-[680px]">
            <div
              className={`${CABECALHO_TABELA} grid grid-cols-[2fr_1fr_1fr_1fr_1.4fr] border-b border-[#DFE0E2] px-1 pb-2.5`}
            >
              <div>Situação</div>
              <div>Volume</div>
              <div>% do total</div>
              <div>Classificação</div>
              <div>Peso</div>
            </div>
            {visao.porTipo.map((t) => (
              <div
                key={t.name}
                className="grid grid-cols-[2fr_1fr_1fr_1fr_1.4fr] items-center border-b border-[#F3F3F3] px-1 py-3 text-[13.5px] text-[#193B4F]"
              >
                <div>{t.name}</div>
                <div>{t.vol}</div>
                <div className="font-medium">{t.acc}</div>
                <div className="font-medium" style={{ color: t.classificacaoColor }}>
                  {t.classificacao}
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-[3px] bg-[#F3F3F3]">
                    <div className="h-full rounded-[3px]" style={{ width: `${t.peso}%`, background: t.cor }} />
                  </div>
                  <div className="w-[42px] text-right" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
