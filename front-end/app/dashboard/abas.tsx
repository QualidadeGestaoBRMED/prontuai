"use client";

/**
 * As três abas do dashboard. Recebem a visão já calculada por `metricas.ts` —
 * aqui só tem layout. As medidas (tamanhos de fonte quebrados, alturas de
 * barra) vêm do protótipo aprovado e são intencionais.
 */
import { useState } from "react";

import type {
  BarraPercentual,
  CardPrevistos,
  CardProjecao,
  GraficoPrazo,
  Kpi,
  LinhaAdesao,
  LinhaPrevista,
  VisaoDashboard,
} from "./metricas";
import styles from "./dashboard.module.css";

const CARTAO = "rounded-[14px] border border-[#DFE0E2] bg-white";
const TITULO = "text-[16.5px] font-semibold text-[#193B4F]";
const SUB = "mt-[5px] text-[13px] text-[#767A7B]";
const CABECALHO_TABELA =
  "text-[11.5px] font-medium uppercase tracking-[0.06em] text-[#767A7B]";

/**
 * Ordenação e busca das tabelas de previsão. As duas (adesão e prioridade de
 * inclusão) ordenam por qualquer coluna, então a mecânica mora aqui uma vez só.
 *
 * `null` desce sempre para o fim, nas duas direções: adesão não medida não é
 * "pior que 0%" nem "melhor que 100%", é ausência de dado, e deixá-la flutuar
 * com o sinal da ordenação faria a primeira linha da tabela mentir.
 */
type Dir = "asc" | "desc";
interface Ordem {
  col: string;
  dir: Dir;
}

const semAcento = (v: string) =>
  v.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function ordenar<T>(linhas: T[], ordem: Ordem, valor: (l: T, col: string) => number | string | null) {
  const sinal = ordem.dir === "asc" ? 1 : -1;
  return [...linhas].sort((a, b) => {
    const x = valor(a, ordem.col);
    const y = valor(b, ordem.col);
    if (x === null || x === "") return y === null || y === "" ? 0 : 1;
    if (y === null || y === "") return -1;
    if (typeof x === "string" || typeof y === "string") {
      return sinal * String(x).localeCompare(String(y), "pt-BR");
    }
    return sinal * (x - y);
  });
}

/** Cabeçalho clicável. O padrão de cada coluna é o que menos surpreende: texto sobe, número desce. */
function Th({
  label,
  col,
  ordem,
  onOrdenar,
  numerica,
}: {
  label: string;
  col: string;
  ordem: Ordem;
  onOrdenar: (col: string, padrao: Dir) => void;
  numerica?: boolean;
}) {
  const ativa = ordem.col === col;
  return (
    <button
      type="button"
      onClick={() => onOrdenar(col, numerica ? "desc" : "asc")}
      aria-label={`Ordenar por ${label}`}
      className={`${CABECALHO_TABELA} flex items-center gap-1 text-left transition-colors hover:text-[#193B4F] ${
        ativa ? "text-[#193B4F]" : ""
      }`}
    >
      {label}
      <span aria-hidden="true" className={`text-[8px] leading-none ${ativa ? "opacity-70" : "opacity-0"}`}>
        {ativa && ordem.dir === "asc" ? "▲" : "▼"}
      </span>
    </button>
  );
}

function CampoBusca({
  valor,
  onChange,
  placeholder,
}: {
  valor: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <input
      type="search"
      value={valor}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="h-[34px] w-[210px] rounded-[9px] border border-[#DFE0E2] bg-white px-3 text-[13px] text-[#193B4F] outline-none placeholder:text-[#9AA3A8] focus:border-[#7EBFCC]"
    />
  );
}

/** Estado de ordenação com o toque de inverter ao reclicar a mesma coluna. */
function useOrdem(inicial: Ordem) {
  const [ordem, setOrdem] = useState<Ordem>(inicial);
  const ordenarPor = (col: string, padrao: Dir) =>
    setOrdem((o) => (o.col === col ? { col, dir: o.dir === "asc" ? "desc" : "asc" } : { col, dir: padrao }));
  return { ordem, ordenarPor };
}

const COLUNAS_ADESAO = "grid-cols-[1.9fr_1.1fr_0.85fr_0.95fr_1.15fr_1fr_1.05fr]";

/**
 * 1.3 — futuro e histórico lado a lado, sem se misturarem. Previstos vêm da
 * janela para frente; realizados e adesão, do filtro de período da tela. As
 * duas colunas convivem na linha mas nunca se dividem uma pela outra: a adesão
 * é realizado ÷ realizado.
 */
function TabelaAdesao({ linhas, janela, periodo }: { linhas: LinhaAdesao[]; janela: string; periodo: string }) {
  const { ordem, ordenarPor } = useOrdem({ col: "previstos", dir: "desc" });
  const [busca, setBusca] = useState("");

  const termo = semAcento(busca.trim());
  const filtradas = termo
    ? linhas.filter((l) => semAcento(l.clinica).includes(termo) || semAcento(l.local).includes(termo))
    : linhas;
  const visiveis = ordenar(filtradas, ordem, (l, col) =>
    col === "clinica" ? l.clinica
    : col === "local" ? l.local
    : col === "previstos" ? l.previstos
    : col === "realizados" ? l.realizados
    : col === "realizadosProntuai" ? l.realizadosProntuai
    : col === "adesao" ? l.adesao
    : l.proximaISO,
  );

  return (
    <div className={`${CARTAO} px-[22px] pt-5 pb-2`}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div>
          <div className={TITULO}>Adesão por clínica habilitada</div>
          <div className={SUB}>
            Previstos: {janela} · realizados e adesão: {periodo} · adesão = realizados via ProntuAI ÷ realizados
          </div>
        </div>
        <CampoBusca valor={busca} onChange={setBusca} placeholder="Buscar clínica ou cidade" />
      </div>

      <div className="mt-4 overflow-x-auto">
        <div className="min-w-[860px]">
          <div className={`grid ${COLUNAS_ADESAO} gap-x-[18px] border-b border-[#DFE0E2] px-1 pb-2.5`}>
            <Th label="Clínica" col="clinica" ordem={ordem} onOrdenar={ordenarPor} />
            <Th label="Cidade" col="local" ordem={ordem} onOrdenar={ordenarPor} />
            <Th label="Previstos" col="previstos" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Realizados" col="realizados" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Via ProntuAI" col="realizadosProntuai" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Adesão" col="adesao" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Próxima previsão" col="proximaISO" ordem={ordem} onOrdenar={ordenarPor} numerica />
          </div>

          {visiveis.map((l) => (
            <div
              key={l.clinica}
              className={`${styles.linhaTip} grid ${COLUNAS_ADESAO} items-center gap-x-[18px] border-b border-[#F3F3F3] px-1 py-3 text-[13.5px] text-[#193B4F]`}
            >
              <span className={`${styles.tip} ${styles.tipNome} min-w-0`} data-tip={l.tip}>
                <span className="block truncate">{l.clinica}</span>
              </span>
              <div className="min-w-0 truncate text-[#767A7B]">{l.local}</div>
              {/* Previsto é futuro: fica cinza para não se confundir com realizado.
                  Zero é zero em todas estas colunas — medimos e deu zero. O traço
                  é exclusivo da adesão, onde significa "não houve o que medir". */}
              <div className={l.previstos ? "tabular-nums text-[#5F6B72]" : "tabular-nums text-[#BFC3C6]"}>
                {l.previstos}
              </div>
              <div className="tabular-nums">{l.realizados}</div>
              <div className={l.realizadosProntuai ? "tabular-nums" : "tabular-nums text-[#BFC3C6]"}>
                {l.realizadosProntuai}
              </div>
              <div className="font-medium tabular-nums" style={{ color: l.adesaoColor }}>
                {l.adesaoLabel}
              </div>
              <div className="tabular-nums text-[#767A7B]">{l.proxima}</div>
            </div>
          ))}

          {!visiveis.length && (
            <div className="px-1 py-6 text-[13px] text-[#767A7B]">Nenhuma clínica para “{busca}”.</div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * 1.4 — projeção. `base` é a soma linha a linha de previstos × adesão da tabela
 * acima; a média ponderada é base ÷ previstos dessas mesmas linhas. Previsto e
 * realizado não se somam em lugar nenhum: o que atravessa é a adesão, que é
 * uma razão entre realizados.
 */
function CartaoProjecao({ card }: { card: CardProjecao }) {
  return (
    <div className={`${CARTAO} px-[22px] pt-5 pb-[22px]`}>
      <div className={TITULO}>Projeção dos previstos via ProntuAI</div>
      <div className={SUB}>
        {card.janela} · clínicas habilitadas · adesão medida sobre os realizados do período
      </div>

      <div className="mt-[18px] grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[
          {
            rotulo: "Previstos",
            valor: card.somaPrevistosLabel,
            sub: "soma das habilitadas",
            tip: "Pedidos com previsão de liberação na janela, nas clínicas com cadastro habilitado.",
          },
          {
            rotulo: "Base estimada",
            valor: card.baseLabel,
            sub: "Σ previstos × adesão, por clínica",
            tip: "Soma linha a linha da tabela de adesão: previstos da clínica multiplicados pela adesão dela.",
          },
          {
            rotulo: "Adesão média ponderada",
            valor: card.adesaoPonderadaLabel,
            sub: "base ÷ previstos com adesão medida",
            tip: "Média das adesões pesada pelos previstos de cada clínica. Clínicas sem adesão medida ficam fora dos dois lados da conta.",
          },
        ].map((x) => (
          <div key={x.rotulo} className={`${styles.tip} ${styles.tipBaixo} flex flex-col gap-1.5`} data-tip={x.tip}>
            <div className="text-[13px] text-[#767A7B]">{x.rotulo}</div>
            <div className="text-[26px] font-medium leading-none tracking-[-0.025em] text-[#193B4F] tabular-nums">
              {x.valor}
            </div>
            <div className="text-[12.5px] text-[#767A7B]">{x.sub}</div>
          </div>
        ))}
      </div>

      {/* A premissa aparece na tela, não só no código: é pendência declarada no
          backlog e quem lê o número precisa saber o que ficou de fora dele. */}
      <div className="mt-[18px] rounded-[10px] bg-[#F3F3F3] px-3.5 py-3 text-[12.5px] leading-[1.5] text-[#767A7B]">
        {card.clinicasSemAdesao ? (
          <>
            <span className="font-medium text-[#A05E1E]">Premissa a confirmar:</span>{" "}
            {card.clinicasSemAdesao} clínica{card.clinicasSemAdesao > 1 ? "s" : ""} sem realizados no período,
            somando {card.previstosSemAdesaoLabel} previstos, ficam fora da base e da média — a adesão delas é
            nula, não zero. Incluí-las como zero afirmaria algo que não foi medido.
          </>
        ) : (
          "Todas as clínicas habilitadas têm realizados no período; nenhuma ficou fora da base."
        )}
      </div>
    </div>
  );
}

const COLUNAS_SEM_PRONTUAI = "grid-cols-[1.9fr_1.1fr_0.85fr_1.05fr_1.05fr_1fr]";

/**
 * 2.2 — prioridade de inclusão. A ordem padrão é por impacto, que é o que a
 * lista existe para responder: qual clínica, se entrasse, mais moveria a base
 * da projeção.
 */
function TabelaPrioridade({ linhas, janela }: { linhas: LinhaPrevista[]; janela: string }) {
  const { ordem, ordenarPor } = useOrdem({ col: "impacto", dir: "desc" });
  const [busca, setBusca] = useState("");
  const [uf, setUf] = useState("");

  const ufs = [...new Set(linhas.map((l) => l.uf).filter((x): x is string => !!x))].sort();
  const termo = semAcento(busca.trim());
  const filtradas = linhas.filter(
    (l) =>
      (!uf || l.uf === uf) &&
      (!termo || semAcento(l.name).includes(termo) || semAcento(l.local).includes(termo)),
  );
  const visiveis = ordenar(filtradas, ordem, (l, col) =>
    col === "name" ? l.name
    : col === "local" ? l.local
    : col === "pedidos" ? l.pedidos
    : col === "participacao" ? l.participacao
    : col === "impacto" ? l.impacto
    : l.proximaISO,
  );
  const previstosVisiveis = visiveis.reduce((a, l) => a + l.pedidos, 0);

  return (
    <>
      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        <CampoBusca valor={busca} onChange={setBusca} placeholder="Buscar clínica ou cidade" />
        <select
          value={uf}
          onChange={(e) => setUf(e.target.value)}
          aria-label="Filtrar por UF"
          className="h-[34px] rounded-[9px] border border-[#DFE0E2] bg-white px-2.5 text-[13px] text-[#193B4F] outline-none focus:border-[#7EBFCC]"
        >
          <option value="">Todas as UFs</option>
          {ufs.map((x) => (
            <option key={x} value={x}>
              {x}
            </option>
          ))}
        </select>
        {(uf || termo) && (
          <div className="text-[12.5px] text-[#767A7B]">
            {visiveis.length} de {linhas.length} · {previstosVisiveis} previstos
          </div>
        )}
      </div>

      <div className="mt-3 max-h-[460px] overflow-auto">
        <div className="min-w-[820px]">
          <div
            className={`sticky top-0 z-10 grid ${COLUNAS_SEM_PRONTUAI} gap-x-[18px] border-b border-[#DFE0E2] bg-white px-1 pb-2.5`}
          >
            <Th label="Clínica" col="name" ordem={ordem} onOrdenar={ordenarPor} />
            <Th label="Cidade" col="local" ordem={ordem} onOrdenar={ordenarPor} />
            <Th label="Previstos" col="pedidos" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Próxima previsão" col="proximaISO" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Participação" col="participacao" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Impacto na base" col="impacto" ordem={ordem} onOrdenar={ordenarPor} numerica />
          </div>
          {visiveis.map((c) => (
            <LinhaClinica key={`${c.credenciado}`} c={c} />
          ))}
          {!visiveis.length && (
            <div className="px-1 py-6 text-[13px] text-[#767A7B]">Nenhuma clínica com esses filtros.</div>
          )}
        </div>
      </div>
      <div className="px-1 pb-3 pt-3 text-[12.5px] leading-[1.5] text-[#767A7B]">
        Impacto = previstos da clínica × adesão esperada ÷ base da projeção.{" "}
        <span className="text-[#A05E1E]">Premissa a confirmar:</span> a adesão esperada de quem ainda não usa é a
        média ponderada das clínicas habilitadas. Enquanto ela for a mesma para todas, a ordem por impacto e por
        previstos coincide. Janela: {janela}.
      </div>
    </>
  );
}

/**
 * Linha da lista de credenciados fora do ProntuAI, com as datas previstas num
 * painel que abre. A quebra por dia já esteve num balão de hover: com meia
 * dúzia de datas virava um parágrafo, ilegível. Aqui cada data é uma linha.
 */
function LinhaClinica({ c }: { c: LinhaPrevista }) {
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
        <div className="tabular-nums text-[#767A7B]">{c.proxima}</div>
        <div className="flex items-center gap-2.5">
          <div className="h-1.5 flex-1 overflow-hidden rounded-[3px] bg-[#F3F3F3]">
            <div className="h-full rounded-[3px] bg-[#CC851E]" style={{ width: `${c.participacao}%` }} />
          </div>
          <div className="w-[46px] text-right tabular-nums">{c.participacaoLabel}</div>
        </div>
        <div className="font-medium tabular-nums text-[#A05E1E]">{c.impactoLabel}</div>
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

/**
 * Pedidos com previsão de liberação na janela, separados pelo mesmo corte das
 * duas tabelas abaixo. É volume AINDA NÃO liberado: não se soma ao que a
 * "Cobertura das expedições" mede, que é realizado. Daí o card ficar aqui, junto
 * das tabelas de previsão, e não ao lado da cobertura.
 */
function CartaoPrevistos({ card }: { card: CardPrevistos }) {
  return (
    <div className={`${CARTAO} px-[22px] pt-5 pb-[22px]`}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <div className={TITULO}>Pedidos previstos</div>
          <div className={SUB}>
            {card.janela} · pedidos ainda não liberados no BRNET · não entram na cobertura
          </div>
        </div>
        <div className="text-right">
          <div className="text-[30px] font-medium leading-none tracking-[-0.025em] text-[#193B4F] tabular-nums">
            {card.totalLabel}
          </div>
          <div className="mt-1.5 text-[12.5px] text-[#767A7B]">no período selecionado</div>
        </div>
      </div>

      {card.total > 0 && (
        <div className="mt-[18px] flex h-[10px] w-full overflow-hidden rounded-[5px] bg-[#F3F3F3]">
          {card.partes.map((x) => (
            <div key={x.rotulo} style={{ width: `${x.pct}%`, background: x.cor }} />
          ))}
        </div>
      )}

      <div className="mt-[18px] grid grid-cols-1 gap-4 sm:grid-cols-2">
        {card.partes.map((x) => (
          <div key={x.rotulo} className={`${styles.tip} ${styles.tipBaixo} flex flex-col gap-1.5`} data-tip={x.tip}>
            <div className="flex items-center gap-2">
              <div className="size-2.5 flex-none rounded-[2px]" style={{ background: x.cor }} />
              <div className="text-[13px] text-[#767A7B]">{x.rotulo}</div>
            </div>
            <div className="text-[22px] font-medium leading-none text-[#193B4F] tabular-nums">{x.label}</div>
            <div className="text-[12.5px] text-[#767A7B]">{x.sub}</div>
          </div>
        ))}
      </div>

      {card.total === 0 && (
        <div className="mt-4 text-[13px] text-[#767A7B]">
          Nenhum pedido com previsão de liberação nesta janela.
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

      {/* Bloco de previsão, em ordem de dependência: o total (1.1) abre, a adesão
          por clínica (1.3) detalha o lado habilitado, a projeção (1.4) usa essa
          adesão e a prioridade de inclusão (2.2) se mede contra a base dela. */}
      {visao.previstos && <CartaoPrevistos card={visao.previstos} />}

      {visao.adesao && visao.previstos && (
        <TabelaAdesao linhas={visao.adesao} janela={visao.previstos.janela} periodo={visao.periodoLabel} />
      )}

      {visao.projecao && <CartaoProjecao card={visao.projecao} />}

      <div className={`${CARTAO} px-[22px] pt-5 pb-2`}>
        <div className={TITULO}>Prioridade de inclusão no ProntuAI</div>
        <div className={SUB}>
          {visao.semProntuai === null
            ? "Lista indisponível: não foi possível consultar o BRNET na última atualização"
            : `${visao.semProntuai.length} credenciadas sem cadastro habilitado · ${visao.pedidosSemProntuai} pedidos previstos ${visao.previstos?.janela ?? ""}`}
        </div>
        {visao.semProntuai && visao.semProntuai.length > 0 && (
          <TabelaPrioridade linhas={visao.semProntuai} janela={visao.previstos?.janela ?? ""} />
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
