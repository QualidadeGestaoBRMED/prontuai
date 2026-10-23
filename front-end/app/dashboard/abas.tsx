"use client";

/**
 * As três abas do dashboard. Recebem a visão já calculada por `metricas.ts` —
 * aqui só tem layout. As medidas (tamanhos de fonte quebrados, alturas de
 * barra) vêm do protótipo aprovado e são intencionais.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { usePermissions } from "@/hooks/usePermissions";

import type {
  AcuraciaExameVisao,
  BarraPercentual,
  BarraSemana,
  GraficoPrazo,
  IdIndicador,
  Kpi,
  LinhaAcuraciaExame,
  LinhaForaProntuai,
  UsoSemanal,
  VisaoDashboard,
} from "./metricas";
import {
  STATUS_ABORDAGEM,
  autorEData,
  infoStatus,
  ordemStatus,
  useAbordagens,
  type Abordagem,
  type StatusAbordagem,
} from "./abordagem";
import styles from "./dashboard.module.css";

const CARTAO ="rounded-[14px] border border-[#DFE0E2] bg-white";
const TITULO = "text-[16.5px] font-semibold text-[#193B4F]";
const SUB = "mt-[5px] text-[13px] text-[#767A7B]";
const CABECALHO_TABELA =
  "text-[11.5px] font-medium uppercase tracking-[0.06em] text-[#767A7B]";
// Botão de seta dos navegadores (semana no card, clínica no modal).
const BOTAO_NAV =
  "flex size-[34px] cursor-pointer items-center justify-center text-[#193B4F] transition-colors hover:bg-[#F3F6F8] disabled:cursor-default disabled:text-[#C6CBCE] disabled:hover:bg-transparent";

const CAMINHO_SETA = { esquerda: "M10 4L6 8l4 4", direita: "M6 4l4 4-4 4", baixo: "M4 6l4 4 4-4" };

/**
 * Seta desenhada, e não caractere: ‹ › e ▼ dependem da fonte de cada sistema e
 * saíam miúdos e desalinhados — o ▼ do seletor de semana quase sumia.
 */
function Seta({ para, className = "size-4" }: { para: keyof typeof CAMINHO_SETA; className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className={className}>
      <path
        d={CAMINHO_SETA[para]}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

type AbrirAjuda = (id: IdIndicador) => void;

/** O "?" que abre o processo por trás do número (`COMO_CALCULAMOS`). */
function BotaoAjuda({ rotulo, onClick }: { rotulo: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Como "${rotulo}" é calculado`}
      title="Como é calculado"
      className="size-[17px] flex-none rounded-full border border-[#7EBFCC] bg-[#E8F2F4] text-[11px] font-semibold leading-[15px] text-[#007891] transition-colors hover:bg-[#D3E9EE]"
    >
      ?
    </button>
  );
}

/**
 * Título de card com o "?" colado nele. `children` entra depois do "?" — é onde
 * mora um selo como "A CONFIRMAR", que fala do card e não do título.
 */
function TituloCartao({
  texto,
  ajuda,
  onAjuda,
  children,
}: {
  texto: string;
  ajuda: IdIndicador;
  onAjuda: AbrirAjuda;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <div className={TITULO}>{texto}</div>
      <BotaoAjuda rotulo={texto} onClick={() => onAjuda(ajuda)} />
      {children}
    </div>
  );
}

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
  sub,
  col,
  ordem,
  onOrdenar,
  numerica,
}: {
  label: string;
  /**
   * Segunda linha do cabeçalho, para a coluna dizer a unidade e a janela do
   * próprio número. Sem isso, "16,3" com uma barra ao lado não informa se é por
   * semana ou por mês, nem de quantas semanas — e o rodapé, que explicava,
   * estava longe demais de quem lê a linha.
   */
  sub?: string;
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
      className={`flex flex-col gap-[3px] text-left transition-colors hover:text-[#193B4F] ${
        ativa ? "text-[#193B4F]" : ""
      }`}
    >
      <span className={`${CABECALHO_TABELA} flex items-center gap-1 ${ativa ? "text-[#193B4F]" : ""}`}>
        {label}
        <span aria-hidden="true" className={`text-[8px] leading-none ${ativa ? "opacity-70" : "opacity-0"}`}>
          {ativa && ordem.dir === "asc" ? "▲" : "▼"}
        </span>
      </span>
      {sub && (
        <span className="text-[10px] font-normal normal-case tracking-normal text-[#9AA3A8]">{sub}</span>
      )}
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

// Os três desfechos, na ordem em que entram na barra. Fora da função porque a
// legenda, a barra do topo e a barra de cada linha precisam pintar a mesma
// coisa da mesma cor — foi assim que os cards antigos acabaram com duas
// verdades sobre o mesmo número.
const DESFECHOS = [
  { chave: "viaProntuai", rotulo: "Via ProntuAI", cor: "#007891" },
  { chave: "fora", rotulo: "Liberado por fora", cor: "#CC851E" },
  { chave: "naoLiberado", rotulo: "Não liberado", cor: "#C6CBCE" },
] as const;

const COLUNAS_USO = "grid-cols-[1.75fr_1.15fr_0.8fr_2.4fr_0.85fr]";

/**
 * "Quem está usando pouco": de tudo o que estava previsto para uma semana
 * fechada, quanto saiu por onde.
 *
 * A barra existe porque a leitura é de proporção, não de valor: o olho tem que
 * achar a clínica com muito laranja antes de ler número nenhum. Os três
 * segmentos somam os previstos da semana, então a barra ocupa a linha inteira
 * sempre — largura igual, composição diferente.
 *
 * Ordem padrão pela ADESÃO, da menor para a maior: a lista existe para apontar
 * quem está usando pouco, e é assim que ela abre já apontando. A coluna "Por
 * fora" fica clicável para quem quiser o outro olhar — o do volume absoluto que
 * escapou, onde 15% de 400 pesa mais que 30% de 10.
 */
function TabelaUsoSemana({ uso, onAjuda }: { uso: UsoSemanal; onAjuda: AbrirAjuda }) {
  // A semana vive aqui, não no filtro de período da tela: o filtro governa os
  // indicadores retroativos, e este indicador anda sozinho, semana a semana.
  const [i, setI] = useState(0);
  const [busca, setBusca] = useState("");
  const { ordem, ordenarPor } = useOrdem({ col: "adesao", dir: "asc" });
  const semana = uso.semanas[Math.min(i, uso.semanas.length - 1)];

  const termo = semAcento(busca.trim());
  const filtradas = semana.linhas.filter(
    (l) => !termo || semAcento(l.clinica).includes(termo) || semAcento(l.local).includes(termo),
  );
  const visiveis = ordenar(filtradas, ordem, (l, col) =>
    col === "clinica" ? l.clinica
    : col === "local" ? l.local
    : col === "previstos" ? l.previstos
    : col === "adesao" ? l.adesao
    : l.fora,
  );

  return (
    <div className={`${CARTAO} px-[22px] pt-5 pb-5`}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div>
          <TituloCartao texto="Quem está usando pouco" ajuda="usandoPouco" onAjuda={onAjuda} />
          <div className={SUB}>
            Do que estava previsto para a semana, quanto passou pela plataforma · semana fechada
          </div>
        </div>

        {/* Navegação por semana. Para trás é o passado, e o passado acaba: os
            botões travam nas pontas em vez de rodarem em círculo. */}
        <div className="flex items-center overflow-hidden rounded-[9px] border border-[#DFE0E2] bg-white">
          <button
            type="button"
            onClick={() => setI((v) => Math.min(v + 1, uso.semanas.length - 1))}
            disabled={i >= uso.semanas.length - 1}
            aria-label="Semana anterior"
            title="Semana anterior"
            className={BOTAO_NAV}
          >
            <Seta para="esquerda" />
          </button>
          {/* As setas andam uma semana; a lista pula direto para qualquer
              semana fechada — para comparar com uma semana de três meses
              atrás, eram doze cliques. */}
          <div className="relative border-x border-[#DFE0E2]">
            <select
              id="uso-semana"
              value={Math.min(i, uso.semanas.length - 1)}
              onChange={(e) => setI(Number(e.target.value))}
              aria-label="Escolher a semana"
              className="h-[34px] min-w-[136px] cursor-pointer appearance-none bg-transparent pr-8 pl-3 text-[13px] font-medium tabular-nums text-[#193B4F] outline-none transition-colors hover:bg-[#F3F6F8] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#7EBFCC]"
            >
              {uso.semanas.map((s, k) => (
                <option key={s.iso} value={k}>
                  {s.label}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-[#193B4F]">
              <Seta para="baixo" className="size-3.5" />
            </span>
          </div>
          <button
            type="button"
            onClick={() => setI((v) => Math.max(v - 1, 0))}
            disabled={i === 0}
            aria-label="Semana seguinte"
            title="Semana seguinte"
            className={BOTAO_NAV}
          >
            <Seta para="direita" />
          </button>
        </div>
      </div>

      {/* Total da semana: o mesmo desenho da linha, em escala maior. Quem
          entende a barra de cima já entende as 118 de baixo. */}
      <div className="mt-[18px] flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          {/* O recorte vai colado no total, e não só no subtítulo do card: é
              o número que vai para a reunião, e "previstos" sozinho se lê como
              tudo o que o BRNET previu, inclusive de quem ainda não tem login. */}
          {[
            { r: "Previstos na semana", v: semana.previstos, cor: "#193B4F", sub: "só clínicas com login no ProntuAI" },
            { r: "Via ProntuAI", v: semana.viaProntuai, cor: "#007891" },
            { r: "Liberado por fora", v: semana.fora, cor: "#CC851E" },
            { r: "Não liberado", v: semana.naoLiberado, cor: "#767A7B" },
          ].map((x) => (
            <div key={x.r} className="flex flex-col gap-1">
              <div className={CABECALHO_TABELA}>{x.r}</div>
              <div className="text-[19px] font-medium leading-none tabular-nums" style={{ color: x.cor }}>
                {x.v.toLocaleString("pt-BR")}
              </div>
              {x.sub && <div className="text-[11px] text-[#9AA3A8]">{x.sub}</div>}
            </div>
          ))}
        </div>
        <div className="text-right">
          <div
            className="text-[30px] font-medium leading-none tracking-[-0.025em] tabular-nums"
            style={{ color: semana.adesao >= 90 ? "#2CAD6E" : semana.adesao >= 75 ? "#CC851E" : "#B4453A" }}
          >
            {semana.adesaoLabel}
          </div>
          <div className="mt-1.5 text-[12.5px] text-[#767A7B]">adesão da semana</div>
        </div>
      </div>

      {semana.previstos > 0 && (
        <div className="mt-3 flex h-[10px] w-full overflow-hidden rounded-[5px] bg-[#F3F3F3]">
          {DESFECHOS.map((d) => (
            <div
              key={d.chave}
              style={{ width: `${(semana[d.chave] / semana.previstos) * 100}%`, background: d.cor }}
            />
          ))}
        </div>
      )}

      <div className="mt-3.5 flex flex-wrap items-center gap-x-5 gap-y-2">
        {DESFECHOS.map((d) => (
          <div key={d.chave} className="flex items-center gap-1.5 text-[12.5px] text-[#767A7B]">
            <div className="size-2.5 flex-none rounded-[2px]" style={{ background: d.cor }} />
            {d.rotulo}
          </div>
        ))}
        <div className="ml-auto">
          <CampoBusca valor={busca} onChange={setBusca} placeholder="Buscar clínica ou cidade" />
        </div>
      </div>

      <div className="mt-3 max-h-[460px] overflow-auto">
        <div className="min-w-[780px]">
          <div
            className={`sticky top-0 z-10 grid ${COLUNAS_USO} gap-x-[18px] border-b border-[#DFE0E2] bg-white px-1 pb-2.5`}
          >
            <Th label="Clínica" col="clinica" ordem={ordem} onOrdenar={ordenarPor} />
            <Th label="Cidade" col="local" ordem={ordem} onOrdenar={ordenarPor} />
            <Th label="Previstos" col="previstos" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Por fora" col="fora" ordem={ordem} onOrdenar={ordenarPor} numerica />
            <Th label="Adesão" col="adesao" ordem={ordem} onOrdenar={ordenarPor} numerica />
          </div>
          {visiveis.map((l) => (
            <div
              key={l.clinica}
              className={`${styles.linhaTip} grid ${COLUNAS_USO} items-center gap-x-[18px] border-b border-[#F3F3F3] px-1 py-3 text-[13.5px] text-[#193B4F]`}
            >
              {/* O nome vem dentro de um invólucro por um motivo de CSS, não
                  de estilo: `.tipNome` é `inline-block` para encolher
                  até o tamanho do texto e a seta do balão apontar para o nome.
                  Como filho direto do grid ele é blocado, estica pela coluna
                  inteira e a seta passa a apontar para a coluna seguinte — que é
                  exatamente o que o comentário do CSS manda evitar. O nome
                  precisa ser um `span` dentro de um invólucro. */}
              <div className="flex min-w-0 items-center gap-2.5">
                <div
                  className="size-2 flex-shrink-0 rounded-full"
                  style={{ background: l.adesaoColor }}
                  aria-hidden="true"
                />
                <span className={`${styles.tip} ${styles.tipNome} min-w-0`} data-tip={l.tip}>
                  <span className="block truncate">{l.clinica}</span>
                </span>
              </div>
              <div className="min-w-0 truncate text-[#767A7B]">{l.local}</div>
              <div className="tabular-nums">{l.previstos}</div>
              {/* A barra é a coluna "por fora": o laranja é o que se procura, e
                  o número ao lado dele é o volume absoluto que decide a visita. */}
              <div className="flex items-center gap-2.5">
                <div className="flex h-[9px] flex-1 overflow-hidden rounded-[4px] bg-[#F3F3F3]">
                  <div className="h-full" style={{ width: `${l.pctVia}%`, background: "#007891" }} />
                  <div className="h-full" style={{ width: `${l.pctFora}%`, background: "#CC851E" }} />
                  <div className="h-full" style={{ width: `${l.pctNao}%`, background: "#C6CBCE" }} />
                </div>
                <div className="w-[34px] text-right font-medium tabular-nums text-[#A05E1E]">{l.fora}</div>
              </div>
              <div className="font-medium tabular-nums" style={{ color: l.adesaoColor }}>
                {l.adesaoLabel}
              </div>
            </div>
          ))}
          {!visiveis.length && (
            <div className="px-1 py-6 text-[13px] text-[#767A7B]">
              {termo ? "Nenhuma clínica com esse termo." : "Nenhuma clínica tinha previsão nesta semana."}
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

/**
 * Simulador de inclusão. Fala em pedidos POR SEMANA, não em previstos da
 * janela: incluir uma clínica não é capturar um pico, é capturar o ritmo dela.
 *
 * A premissa é a adesão medida no indicador de cima — nada é estimado aqui. Ela
 * vem rotulada com a semana de origem, para ninguém usar o número sem saber de
 * quando ele é.
 */
function Simulador({
  linhas,
  selecionadas,
  viaProntuaiSemana,
  adesao,
  semana,
  onAtalho,
  recusadas,
  incluirRecusadas,
  onIncluirRecusadas,
}: {
  linhas: LinhaForaProntuai[];
  selecionadas: Set<string>;
  /** Pedidos que passaram pela plataforma na última semana fechada. */
  viaProntuaiSemana: number;
  /** Adesão daquela mesma semana, em %. */
  adesao: number;
  semana: string;
  onAtalho: (quantas: number | "limpar") => void;
  /** Quantas da lista estão marcadas como Recusou. */
  recusadas: number;
  /** Recusadas ficam fora do Top 5/10/20, a menos que alguém peça. */
  incluirRecusadas: boolean;
  onIncluirRecusadas: (incluir: boolean) => void;
}) {
  const mediaSel = linhas
    .filter((l) => selecionadas.has(l.credenciado))
    .reduce((a, l) => a + l.media, 0);
  const ganho = (mediaSel * adesao) / 100;
  const aumento = viaProntuaiSemana ? (ganho / viaProntuaiSemana) * 100 : null;
  const p1 = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const n0 = (v: number) => Math.round(v).toLocaleString("pt-BR");

  return (
    <div className="mt-4 rounded-[12px] border border-[#DFE0E2] bg-[#FAFBFC] px-[18px] py-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="mr-auto text-[14px] font-semibold text-[#193B4F]">Simular inclusão</div>
        {recusadas > 0 && (
          <label className="mr-1 flex cursor-pointer items-center gap-1.5 text-[12.5px] text-[#767A7B]">
            <input
              type="checkbox"
              checked={incluirRecusadas}
              onChange={(e) => onIncluirRecusadas(e.target.checked)}
              className="size-3.5 cursor-pointer accent-[#00AFAA]"
            />
            incluir as {recusadas} recusada{recusadas > 1 ? "s" : ""} no Top
          </label>
        )}
        {([["Top 5", 5], ["Top 10", 10], ["Top 20", 20]] as [string, number][]).map(([r, q]) => (
          <button key={r} type="button" onClick={() => onAtalho(q)}
                  className="rounded-[8px] border border-[#DFE0E2] bg-white px-3 py-1.5 text-[12.5px] text-[#193B4F] hover:border-[#7EBFCC]">
            {r}
          </button>
        ))}
        <button type="button" onClick={() => onAtalho("limpar")}
                className="rounded-[8px] border border-[#DFE0E2] bg-white px-3 py-1.5 text-[12.5px] text-[#767A7B] hover:border-[#7EBFCC]">
          Limpar
        </button>
      </div>

      {/* Cada número diz de que semana ele é. "Hoje, por semana" não dizia, e
          "hoje" num painel que fala de semana fechada se lê como o dia de hoje —
          que é justamente o que o número não é. */}
      <div className="mt-4 grid grid-cols-2 gap-x-5 gap-y-3.5 lg:grid-cols-4">
        {[
          {
            r: "Passam hoje pela plataforma",
            v: n0(viaProntuaiSemana),
            sub: `pedidos na semana de ${semana}`,
          },
          {
            r: "Somando as marcadas",
            v: n0(viaProntuaiSemana + ganho),
            sub: "pedidos por semana, estimados",
          },
          {
            r: "Aumento no volume semanal",
            v: aumento === null ? "—" : `+${p1(aumento)}%`,
            sub: "sobre o que passa hoje",
            destaque: true,
          },
          {
            r: "Média somada das marcadas",
            v: `${n0(mediaSel)}/sem`,
            sub: "liberações, antes da adesão",
          },
        ].map((x) => (
          <div key={x.r} className="flex flex-col gap-1">
            <div className={CABECALHO_TABELA}>{x.r}</div>
            <div className={`tabular-nums leading-none ${x.destaque ? "text-[24px] font-medium text-[#00AFAA]" : "text-[17px] text-[#193B4F]"}`}>
              {x.v}
            </div>
            <div className="text-[11px] text-[#9AA3A8]">{x.sub}</div>
          </div>
        ))}
      </div>

      <div className="mt-3.5 text-[12.5px] leading-[1.5] text-[#767A7B]">
        {selecionadas.size === 0
          ? `Marque clínicas na lista para simular. A premissa é a adesão de ${p1(adesao)}% medida em ${semana}. Nada é gravado.`
          : `${selecionadas.size} clínica${selecionadas.size > 1 ? "s" : ""} marcada${selecionadas.size > 1 ? "s" : ""} · ${n0(mediaSel)} liberações/semana × ${p1(adesao)}% de adesão = +${n0(ganho)} pedidos por semana na plataforma. Simulação: nada é gravado.`}
      </div>
    </div>
  );
}

// As duas precisam ser literais: o Tailwind compila só as classes que encontra
// no código-fonte. Montar a segunda com `.replace()` sobre a primeira gerava uma
// classe em runtime que nunca foi compilada, e a linha inteira perdia o grid.
const COLUNAS_FORA = "grid-cols-[28px_1.7fr_1fr_2fr_1.05fr_1.05fr_178px]";
const COLUNAS_FORA_LINHA = "grid-cols-[1.7fr_1fr_2fr_1.05fr_1.05fr]";

/**
 * "Quem vale a pena incluir": credenciados fora do ProntuAI, ranqueados pelos
 * pedidos PREVISTOS na janela.
 *
 * Este é o indicador do futuro, e o de cima é o do passado — a divisão é do
 * pedido, não uma escolha de implementação. Por isso a ordem é pelo previsto: a
 * pergunta que abre a lista é "quais têm previsão de liberação maior".
 *
 * A média semanal não ordena, ela confere. O previsto é a foto de um instante e
 * pode ser um pico; quem diz se aquele volume é o ritmo da clínica é a coluna da
 * média, a marca de PICO e o gráfico que abre no modal. Ranquear pelo futuro,
 * desconfiar, clicar, conferir no passado.
 *
 * Nenhuma métrica de adesão aqui. Adesão é sobre quem já está dentro, e mora no
 * indicador de cima.
 */
function TabelaForaProntuai({
  linhas,
  janelaMedia,
  janelaPrevistos,
  simulador,
}: {
  linhas: LinhaForaProntuai[];
  /** Intervalo das 12 semanas que entram na média: "27/07 a 05/10". */
  janelaMedia: string;
  /** Janela dos previstos: "de hoje a 12/11 · 30 dias". */
  janelaPrevistos: string;
  simulador: { viaProntuaiSemana: number; adesao: number; semana: string } | null;
}) {
  const { ordem, ordenarPor } = useOrdem({ col: "previstos", dir: "desc" });
  const [busca, setBusca] = useState("");
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  // Status de abordagem: lido na hora, fora do cache diário dos indicadores.
  // Só a gestão altera; quem vê o dashboard enxerga o status, o autor e a data.
  const { isManagement: podeEditar } = usePermissions();
  const { porCredenciado, erro: erroCarga, salvar } = useAbordagens();
  const statusDe = (credenciado: string): StatusAbordagem =>
    porCredenciado.get(credenciado)?.status ?? "NAO_ABORDADA";
  const [filtroStatus, setFiltroStatus] = useState<StatusAbordagem | "todos">("todos");
  const [incluirRecusadas, setIncluirRecusadas] = useState(false);
  const [erroSalvar, setErroSalvar] = useState<string | null>(null);
  // Escolher "Recusou" na lista abre o detalhe: a recusa pede motivo, e o
  // motivo não cabe na célula da tabela.
  const [recusarEm, setRecusarEm] = useState<string | null>(null);
  // Quem está aberto e se o modal está aberto são estados separados: ao
  // fechar, a clínica continua montada durante a animação de saída, em vez de
  // o conteúdo sumir antes do modal.
  const [aberta, setAberta] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const abrir = (credenciado: string) => {
    setAberta(credenciado);
    setModalAberto(true);
  };

  const termo = semAcento(busca.trim());
  const filtradas = linhas.filter(
    (l) =>
      (!termo || semAcento(l.name).includes(termo) || semAcento(l.local).includes(termo)) &&
      (filtroStatus === "todos" || statusDe(l.credenciado) === filtroStatus),
  );
  const porStatus = new Map<StatusAbordagem, number>();
  for (const l of linhas) porStatus.set(statusDe(l.credenciado), (porStatus.get(statusDe(l.credenciado)) ?? 0) + 1);
  const visiveis = ordenar(filtradas, ordem, (l, col) =>
    col === "name" ? l.name
    : col === "local" ? l.local
    : col === "previstos" ? l.previstos
    : col === "regularidade" ? l.regularidade
    : col === "abordagem" ? ordemStatus(statusDe(l.credenciado))
    : l.media,
  );

  const aplicarAtalho = (quantas: number | "limpar") =>
    setMarcadas(
      quantas === "limpar"
        ? new Set()
        : new Set(
            visiveis
              .filter((l) => incluirRecusadas || statusDe(l.credenciado) !== "RECUSOU")
              .slice(0, quantas)
              .map((l) => l.credenciado),
          ),
    );
  const alternar = (credenciado: string) =>
    setMarcadas((atual) => {
      const proximo = new Set(atual);
      if (!proximo.delete(credenciado)) proximo.add(credenciado);
      return proximo;
    });

  const mudarStatus = (credenciado: string, status: StatusAbordagem) => {
    setErroSalvar(null);
    if (status === "RECUSOU") {
      setRecusarEm(credenciado);
      abrir(credenciado);
      return;
    }
    salvar(credenciado, status).catch((e: unknown) =>
      setErroSalvar(`Não foi possível salvar o status: ${e instanceof Error ? e.message : String(e)}`),
    );
  };

  return (
    <>
      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        <CampoBusca valor={busca} onChange={setBusca} placeholder="Buscar clínica ou cidade" />
        <select
          value={filtroStatus}
          onChange={(e) => setFiltroStatus(e.target.value as StatusAbordagem | "todos")}
          aria-label="Filtrar por status de abordagem"
          className="h-[34px] cursor-pointer rounded-[9px] border border-[#DFE0E2] bg-white px-2.5 text-[13px] text-[#193B4F] outline-none focus:border-[#7EBFCC]"
        >
          <option value="todos">Todos os status ({linhas.length})</option>
          {STATUS_ABORDAGEM.map((s) => (
            <option key={s.valor} value={s.valor}>
              {s.rotulo} ({porStatus.get(s.valor) ?? 0})
            </option>
          ))}
        </select>
        {(termo || filtroStatus !== "todos") && (
          <div className="text-[12.5px] text-[#767A7B]">
            {visiveis.length} de {linhas.length} credenciadas
          </div>
        )}
      </div>

      {simulador && (
        <Simulador
          linhas={linhas}
          selecionadas={marcadas}
          viaProntuaiSemana={simulador.viaProntuaiSemana}
          adesao={simulador.adesao}
          semana={simulador.semana}
          onAtalho={aplicarAtalho}
          recusadas={porStatus.get("RECUSOU") ?? 0}
          incluirRecusadas={incluirRecusadas}
          onIncluirRecusadas={setIncluirRecusadas}
        />
      )}

      {(erroCarga || erroSalvar) && (
        <div className="mt-3 rounded-[9px] border border-[#F2D3CF] bg-[#FBECEA] px-3 py-2 text-[12.5px] text-[#B4453A]">
          {erroSalvar ?? `Não foi possível carregar os status de abordagem: ${erroCarga}`}
        </div>
      )}

      <div className="mt-3 max-h-[460px] overflow-auto">
        <div className="min-w-[1100px]">
          <div
            className={`sticky top-0 z-10 grid ${COLUNAS_FORA} items-end gap-x-[18px] border-b border-[#DFE0E2] bg-white px-1 pb-2.5`}
          >
            <span aria-hidden="true" />
            <Th label="Clínica" col="name" ordem={ordem} onOrdenar={ordenarPor} />
            <Th label="Cidade" col="local" ordem={ordem} onOrdenar={ordenarPor} />
            <Th
              label="Média por semana"
              sub={`liberações · ${janelaMedia}`}
              col="media"
              ordem={ordem}
              onOrdenar={ordenarPor}
              numerica
            />
            <Th
              label="Semanas com liberação"
              sub="das 12 semanas"
              col="regularidade"
              ordem={ordem}
              onOrdenar={ordenarPor}
              numerica
            />
            <Th
              label="Previstos"
              sub="a liberar na janela"
              col="previstos"
              ordem={ordem}
              onOrdenar={ordenarPor}
              numerica
            />
            <Th label="Abordagem" sub="quem marcou e quando" col="abordagem" ordem={ordem} onOrdenar={ordenarPor} />
          </div>
          {visiveis.map((c) => (
            <LinhaFora
              key={c.credenciado}
              c={c}
              marcada={marcadas.has(c.credenciado)}
              onMarcar={alternar}
              onAbrir={abrir}
              abordagem={porCredenciado.get(c.credenciado)}
              podeEditar={podeEditar}
              onStatus={mudarStatus}
            />
          ))}
          {!visiveis.length && (
            <div className="px-1 py-6 text-[13px] text-[#767A7B]">Nenhuma clínica com esses filtros.</div>
          )}
        </div>
      </div>

      <ModalHistoricoFora
        linhas={visiveis}
        credenciado={aberta}
        aberto={modalAberto}
        onFechar={() => {
          setModalAberto(false);
          setRecusarEm(null);
        }}
        onIr={setAberta}
        janelaMedia={janelaMedia}
        janelaPrevistos={janelaPrevistos}
        marcadas={marcadas}
        onMarcar={alternar}
        abordagem={aberta ? porCredenciado.get(aberta) : undefined}
        podeEditar={podeEditar}
        recusarAoAbrir={recusarEm !== null && recusarEm === aberta}
        onSalvarAbordagem={async (credenciado, status, motivo) => {
          await salvar(credenciado, status, motivo);
          setRecusarEm(null);
        }}
      />
    </>
  );
}

/**
 * Linha do ranking. Clicar abre o histórico da clínica no modal; a marcação do
 * simulador fica fora do botão — aninhar input em button é inválido, e o
 * clique de um roubaria o do outro.
 */
function LinhaFora({
  c,
  marcada,
  onMarcar,
  onAbrir,
  abordagem,
  podeEditar,
  onStatus,
}: {
  c: LinhaForaProntuai;
  marcada: boolean;
  onMarcar: (credenciado: string) => void;
  onAbrir: (credenciado: string) => void;
  abordagem: Abordagem | undefined;
  podeEditar: boolean;
  onStatus: (credenciado: string, status: StatusAbordagem) => void;
}) {
  return (
    <div className={`border-b border-[#F3F3F3] ${marcada ? "bg-[#E6EDF4]" : ""}`}>
      <div className={`grid ${COLUNAS_FORA} items-center gap-x-[18px] px-1`}>
        <label className="flex cursor-pointer items-center justify-center py-3">
          <input
            type="checkbox"
            checked={marcada}
            onChange={() => onMarcar(c.credenciado)}
            aria-label={`Incluir ${c.name} na simulação`}
            className="size-4 cursor-pointer accent-[#00AFAA]"
          />
        </label>
        <button
          type="button"
          onClick={() => onAbrir(c.credenciado)}
          aria-haspopup="dialog"
          className={`group col-span-5 grid ${COLUNAS_FORA_LINHA} cursor-pointer items-center gap-x-[18px] rounded-[6px] py-3 text-left text-[13.5px] text-[#193B4F] transition-colors hover:bg-[#F7F9FA]`}
        >
          {/* O nome tem cara de link porque é o que abre o modal — a linha
              inteira abre, para o alvo ser grande, mas é no nome que o olho
              procura. A seta que vinha antes dele é o símbolo de "expandir aqui
              embaixo", que era o comportamento antigo: com o modal, prometia
              outra coisa. */}
          <span className="min-w-0 truncate text-[#007891] decoration-[#7EBFCC] underline-offset-[3px] group-hover:underline">
            {c.name}
          </span>
          <div className="min-w-0 truncate text-[#767A7B]">{c.local}</div>
          <div className="flex items-center gap-2.5">
            <div className="h-1.5 flex-1 overflow-hidden rounded-[3px] bg-[#F3F3F3]">
              <div className="h-full rounded-[3px] bg-[#007891]" style={{ width: `${c.pct}%` }} />
            </div>
            <div className="flex w-[74px] items-baseline justify-end gap-1">
              <span className="font-medium tabular-nums">{c.mediaLabel}</span>
              <span className="text-[11px] text-[#9AA3A8]">/sem</span>
            </div>
          </div>
          <div className="tabular-nums text-[#767A7B]">{c.regularidadeLabel}</div>
          <div className="flex items-center gap-1.5">
            <span className="tabular-nums">{c.previstos}</span>
            {/* O aviso de pico mora na coluna de previstos porque é dela que o
                engano nasce: o número grande da janela que não se repete. */}
            {c.picoPrevisto && <MarcaPico />}
          </div>
        </button>
        <CelulaAbordagem c={c} abordagem={abordagem} podeEditar={podeEditar} onStatus={onStatus} />
      </div>
    </div>
  );
}

/**
 * Status de abordagem na linha do ranking. Para a gestão é um seletor que grava
 * na hora; para os demais, só o selo. O autor e a data ficam embaixo, porque a
 * pergunta seguinte de quem vê "Em contato" é "com quem, e desde quando".
 */
function CelulaAbordagem({
  c,
  abordagem,
  podeEditar,
  onStatus,
}: {
  c: LinhaForaProntuai;
  abordagem: Abordagem | undefined;
  podeEditar: boolean;
  onStatus: (credenciado: string, status: StatusAbordagem) => void;
}) {
  const info = infoStatus(abordagem?.status ?? "NAO_ABORDADA");
  const autor = autorEData(abordagem);
  return (
    <div
      className="flex min-w-0 flex-col gap-1 py-2"
      title={abordagem?.motivo ? `Motivo da recusa: ${abordagem.motivo}` : undefined}
    >
      {podeEditar ? (
        <select
          value={info.valor}
          onChange={(e) => onStatus(c.credenciado, e.target.value as StatusAbordagem)}
          aria-label={`Status de abordagem de ${c.name}`}
          className="h-[28px] w-full cursor-pointer rounded-[7px] border px-1.5 text-[12.5px] font-medium outline-none focus:border-[#7EBFCC]"
          style={{ color: info.cor, background: info.fundo, borderColor: info.fundo }}
        >
          {STATUS_ABORDAGEM.map((s) => (
            <option key={s.valor} value={s.valor} style={{ color: "#193B4F", background: "#FFFFFF" }}>
              {s.rotulo}
            </option>
          ))}
        </select>
      ) : (
        <span
          className="w-fit rounded-[7px] px-2 py-1 text-[12.5px] font-medium"
          style={{ color: info.cor, background: info.fundo }}
        >
          {info.rotulo}
        </span>
      )}
      {autor && <span className="truncate text-[10.5px] leading-tight text-[#9AA3A8]">{autor}</span>}
    </div>
  );
}

/**
 * O status no detalhe da clínica. É aqui que a recusa ganha o motivo: escolher
 * "Recusou" na lista abre este modal com a recusa já selecionada.
 *
 * O formulário nasce do que está gravado; quem o chama troca a `key` quando a
 * clínica ou a gravação mudam, e o estado recomeça do banco.
 */
function EditorAbordagem({
  abordagem,
  podeEditar,
  recusarAoAbrir,
  onSalvar,
}: {
  abordagem: Abordagem | undefined;
  podeEditar: boolean;
  recusarAoAbrir: boolean;
  onSalvar: (status: StatusAbordagem, motivo: string | null) => Promise<void>;
}) {
  const atual = abordagem?.status ?? "NAO_ABORDADA";
  const [status, setStatus] = useState<StatusAbordagem>(recusarAoAbrir ? "RECUSOU" : atual);
  const [motivo, setMotivo] = useState(abordagem?.motivo ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const recusa = status === "RECUSOU";
  const mudou = status !== atual || (recusa && motivo.trim() !== (abordagem?.motivo ?? ""));
  const podeSalvar = mudou && !salvando && (!recusa || motivo.trim().length > 0);
  const info = infoStatus(atual);
  const autor = autorEData(abordagem);

  const gravar = async () => {
    setSalvando(true);
    setErro(null);
    try {
      await onSalvar(status, recusa ? motivo.trim() : null);
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : String(e));
      setSalvando(false);
    }
  };

  return (
    <div>
      <div className={CABECALHO_TABELA}>Abordagem</div>
      {podeEditar ? (
        <div className="mt-3 flex flex-col gap-2.5">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusAbordagem)}
            aria-label="Status de abordagem"
            className="h-[34px] cursor-pointer rounded-[9px] border border-[#DFE0E2] bg-white px-2.5 text-[13px] text-[#193B4F] outline-none focus:border-[#7EBFCC]"
          >
            {STATUS_ABORDAGEM.map((s) => (
              <option key={s.valor} value={s.valor}>
                {s.rotulo}
              </option>
            ))}
          </select>
          {recusa && (
            <textarea
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              maxLength={500}
              rows={3}
              autoFocus={recusarAoAbrir}
              placeholder="Motivo da recusa (obrigatório)"
              aria-label="Motivo da recusa"
              className="resize-none rounded-[9px] border border-[#DFE0E2] bg-white px-3 py-2 text-[13px] leading-snug text-[#193B4F] outline-none placeholder:text-[#9AA3A8] focus:border-[#7EBFCC]"
            />
          )}
          <button
            type="button"
            disabled={!podeSalvar}
            onClick={gravar}
            className="h-[34px] cursor-pointer rounded-[9px] bg-[#193B4F] px-3 text-[13px] font-medium text-white transition-opacity disabled:cursor-default disabled:opacity-35"
          >
            {salvando ? "Salvando…" : "Salvar status"}
          </button>
          {erro && <div className="text-[12px] leading-snug text-[#B4453A]">{erro}</div>}
        </div>
      ) : (
        <div className="mt-3">
          <span
            className="inline-block rounded-[7px] px-2 py-1 text-[12.5px] font-medium"
            style={{ color: info.cor, background: info.fundo }}
          >
            {info.rotulo}
          </span>
          {abordagem?.motivo && (
            <p className="mt-2 text-[13px] leading-snug text-[#5F6B72]">Motivo: {abordagem.motivo}</p>
          )}
        </div>
      )}
      <div className="mt-2.5 text-[11.5px] leading-snug text-[#9AA3A8]">
        {autor ? `Última alteração ${autor}` : "Ninguém marcou esta clínica ainda."}
      </div>
    </div>
  );
}

function MarcaPico() {
  return (
    <span className="rounded-[5px] bg-[#F7EDDC] px-1.5 py-0.5 text-[10px] font-medium tracking-[0.04em] text-[#A05E1E]">
      PICO
    </span>
  );
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/**
 * Topo e passo "redondos" para o eixo Y — 0, 20, 40, 60, e não 0, 15, 30, 45.
 * A folga de 12% acima da maior coluna é o espaço do número que vai em cima
 * dela; sem isso a coluna mais alta encostava no teto e o rótulo sumia.
 */
function escalaY(maximo: number) {
  const alvo = Math.max(1, maximo * 1.12);
  if (alvo <= 4) return { topo: 4, passo: 1 };
  const bruto = alvo / 4;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 5, 10].map((m) => m * potencia).find((p) => p >= bruto) ?? 10 * potencia;
  return { topo: passo * Math.ceil(alvo / passo), passo };
}

/**
 * Listra da semana corrente: ainda está acontecendo, e o número só pode subir.
 * Uma por cor, porque a semana corrente também pode já ter estourado o ritmo —
 * e aí as duas coisas precisam aparecer.
 */
const LISTRA_PARCIAL = "repeating-linear-gradient(135deg, #7EBFCC 0 4px, #C9E5EB 4px 8px)";
const LISTRA_PARCIAL_PICO = "repeating-linear-gradient(135deg, #CC851E 0 4px, #EBC48C 4px 8px)";

function ItemLegenda({ amostra, rotulo }: { amostra: ReactNode; rotulo: string }) {
  return (
    <span className="flex items-center gap-1.5 whitespace-nowrap">
      {amostra}
      {rotulo}
    </span>
  );
}

/**
 * Colunas por semana com a média tracejada — o pedido literal: "pra eu entender
 * se aquilo é um outlier, uma anomalia".
 *
 * As colunas não têm espaçamento entre si (o respiro é padding de cada uma):
 * assim cada coluna ocupa exatamente 1/n da largura, e a faixa das 12 semanas
 * da média, posicionada por porcentagem, cai alinhada com elas.
 */
function GraficoSemanas({
  serie,
  media,
  mediaLabel,
}: {
  serie: BarraSemana[];
  media: number;
  mediaLabel: string;
}) {
  const maior = serie.reduce((m, s) => Math.max(m, s.liberacoes), 0);
  const { topo, passo } = escalaY(Math.max(maior, media));
  const ticks = Array.from({ length: Math.round(topo / passo) + 1 }, (_, k) => k * passo);
  const altura = (v: number) => `${(v / topo) * 100}%`;
  const n = serie.length;
  const inicioMedia = serie.findIndex((s) => s.naMedia);
  const semanasMedia = serie.filter((s) => s.naMedia).length;

  const mes = (iso: string, primeiro: boolean) => {
    const m = Number(iso.slice(5, 7));
    // O ano só onde ele muda a leitura: no começo do eixo e na virada.
    return primeiro || m === 1 ? `${MESES[m - 1]}/${iso.slice(2, 4)}` : MESES[m - 1];
  };

  if (!maior) {
    return (
      <div className="flex h-full min-h-[240px] flex-col items-center justify-center rounded-[12px] border border-dashed border-[#DFE0E2] px-6 text-center">
        <div className="text-[14px] font-medium text-[#193B4F]">Nenhuma liberação no histórico do BRNET</div>
        <div className="mt-1.5 max-w-[420px] text-[13px] text-[#767A7B]">
          {n ? `De ${serie[0].label} até hoje esta clínica não liberou nenhum pedido` : "Sem histórico buscado"} — o
          que ela tem é só previsão futura, sem passado que a confirme.
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[300px] flex-col">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div>
          <div className="text-[14px] font-semibold text-[#193B4F]">Liberações por semana</div>
          <div className="mt-0.5 text-[12px] text-[#9AA3A8]">
            uma coluna = uma semana · passe o mouse numa coluna para ver as datas
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px] text-[#767A7B]">
          <ItemLegenda amostra={<span className="h-0 w-4 border-t-[1.5px] border-dashed border-[#B4453A]" />} rotulo="média das 12 semanas" />
          <ItemLegenda amostra={<span className="h-2.5 w-3 rounded-[2px] bg-[#E3F1F4]" />} rotulo="semanas da média" />
          <ItemLegenda amostra={<span className="size-2.5 rounded-[2px] bg-[#CC851E]" />} rotulo="pico" />
          <ItemLegenda amostra={<span className="size-2.5 rounded-[2px]" style={{ background: LISTRA_PARCIAL }} />} rotulo="semana em andamento" />
        </div>
      </div>

      <div className="mt-9 flex min-h-0 flex-1">
        <div className="relative w-9 flex-none" aria-hidden="true">
          {ticks.map((t) => (
            <div
              key={t}
              className="absolute right-2.5 translate-y-1/2 text-[10.5px] tabular-nums text-[#9AA3A8]"
              style={{ bottom: altura(t) }}
            >
              {t}
            </div>
          ))}
        </div>

        <div className="relative flex-1">
          {ticks.map((t) => (
            <div
              key={t}
              className={`absolute inset-x-0 border-t ${t === 0 ? "border-[#C6CBCE]" : "border-[#F0F1F2]"}`}
              style={{ bottom: altura(t) }}
            />
          ))}

          {semanasMedia > 0 && (
            <div
              className="absolute inset-y-0 rounded-[6px] bg-[#E3F1F4]/70"
              style={{ left: `${(inicioMedia / n) * 100}%`, width: `${(semanasMedia / n) * 100}%` }}
            >
              <div className="absolute inset-x-0 -top-6 truncate text-center text-[10.5px] font-medium text-[#4F8A99]">
                12 semanas da média
              </div>
            </div>
          )}

          <div className="absolute inset-0 flex">
            {serie.map((s, i) => {
              // Nas bordas, o balão centralizado vazaria para fora do modal e
              // seria cortado; ali ele se alinha pela borda da coluna.
              const borda = i / n < 0.15 ? styles.tipInicio : i / n > 0.85 ? styles.tipFim : "";
              return (
                <div
                  key={s.iso}
                  className={`${styles.tip} ${borda} group relative flex h-full flex-1 flex-col justify-end px-[1.5px]`}
                  data-tip={s.tip}
                >
                  <div className="pointer-events-none absolute inset-0 rounded-[3px] transition-colors group-hover:bg-[#193B4F]/[0.05]" />
                  {/* A semana corrente aparece mesmo zerada: sem o fundo, uma
                      coluna vazia no fim do eixo se lia como "parou de liberar". */}
                  {s.parcial && (
                    <div
                      className="pointer-events-none absolute inset-0 rounded-[3px]"
                      style={{ background: "repeating-linear-gradient(135deg, #193B4F0D 0 4px, transparent 4px 8px)" }}
                    />
                  )}
                  {s.liberacoes > 0 && (
                    <div
                      className={`relative mb-1 hidden text-center text-[10px] leading-none tabular-nums lg:block ${
                        s.pico ? "font-semibold text-[#A05E1E]" : "text-[#5F6B72]"
                      }`}
                    >
                      {s.liberacoes}
                    </div>
                  )}
                  <div
                    className="relative w-full rounded-t-[3px] transition-[height] duration-300 ease-out"
                    style={{
                      height: altura(s.liberacoes),
                      minHeight: s.liberacoes ? 2 : 0,
                      background: s.parcial
                        ? s.pico
                          ? LISTRA_PARCIAL_PICO
                          : LISTRA_PARCIAL
                        : s.pico
                          ? "#CC851E"
                          : "#7EBFCC",
                    }}
                  />
                </div>
              );
            })}
          </div>

          {/* A tracejada é a média. Fica por cima das colunas, não atrás: o que
              se quer ver é quais delas a ultrapassam. */}
          <div
            className="pointer-events-none absolute inset-x-0 z-10 border-t-[1.5px] border-dashed border-[#B4453A] transition-[bottom] duration-300 ease-out"
            style={{ bottom: altura(media) }}
          />
        </div>

        <div className="relative w-[78px] flex-none" aria-hidden="true">
          <div
            className="absolute left-2 translate-y-1/2 whitespace-nowrap text-[11px] font-medium text-[#B4453A] transition-[bottom] duration-300 ease-out"
            style={{ bottom: altura(media) }}
          >
            média {mediaLabel}
          </div>
        </div>
      </div>

      <div className="ml-9 mr-[78px] mt-2 flex" aria-hidden="true">
        {serie.map((s, i) => {
          const novoMes = i === 0 || serie[i - 1].iso.slice(5, 7) !== s.iso.slice(5, 7);
          return (
            <div key={s.iso} className="relative h-4 flex-1">
              {novoMes && (
                <span className="absolute left-[1.5px] whitespace-nowrap border-l border-[#DFE0E2] pl-1 text-[11px] leading-4 text-[#767A7B]">
                  {mes(s.iso, i === 0)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NumeroModal({
  rotulo,
  valor,
  unidade,
  sub,
  destaque,
  extra,
}: {
  rotulo: string;
  valor: string;
  unidade?: string;
  sub: string;
  destaque?: boolean;
  extra?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className={CABECALHO_TABELA}>{rotulo}</div>
      <div className="flex items-baseline gap-1.5">
        <span
          className={`leading-none tabular-nums ${
            destaque ? "text-[28px] font-medium text-[#007891]" : "text-[22px] text-[#193B4F]"
          }`}
        >
          {valor}
        </span>
        {unidade && <span className="text-[12px] text-[#9AA3A8]">{unidade}</span>}
        {extra}
      </div>
      <div className="text-[11.5px] leading-snug text-[#9AA3A8]">{sub}</div>
    </div>
  );
}

/**
 * O histórico de uma clínica de "Quem vale a pena incluir", em tela quase cheia.
 *
 * É aqui que o fluxo do indicador se completa — ranquear pelo futuro, desconfiar,
 * abrir, conferir no passado. Por isso o modal anda pela lista (setas da tela ou
 * do teclado) na ordem em que ela está: numa reunião, quem apresenta passa de uma
 * clínica para a seguinte sem fechar e reabrir. E dá para marcar a clínica para o
 * simulador daqui mesmo, que é onde a decisão é tomada.
 */
function ModalHistoricoFora({
  linhas,
  credenciado,
  aberto,
  onFechar,
  onIr,
  janelaMedia,
  janelaPrevistos,
  marcadas,
  onMarcar,
  abordagem,
  podeEditar,
  recusarAoAbrir,
  onSalvarAbordagem,
}: {
  /** A lista como está na tela: mesma busca e mesma ordem. */
  linhas: LinhaForaProntuai[];
  credenciado: string | null;
  aberto: boolean;
  onFechar: () => void;
  onIr: (credenciado: string) => void;
  janelaMedia: string;
  janelaPrevistos: string;
  marcadas: Set<string>;
  onMarcar: (credenciado: string) => void;
  abordagem: Abordagem | undefined;
  podeEditar: boolean;
  recusarAoAbrir: boolean;
  onSalvarAbordagem: (credenciado: string, status: StatusAbordagem, motivo: string | null) => Promise<void>;
}) {
  const i = credenciado === null ? -1 : linhas.findIndex((l) => l.credenciado === credenciado);
  const c = i >= 0 ? linhas[i] : null;
  // A série é montada só aqui, para a clínica aberta (ver `LinhaForaProntuai.serie`).
  const serie = useMemo(() => (c ? c.serie() : []), [c]);
  const anterior = i > 0 ? linhas[i - 1].credenciado : null;
  const proxima = i >= 0 && i < linhas.length - 1 ? linhas[i + 1].credenciado : null;

  // No window, e não no onKeyDown do conteúdo: o foco pode estar em qualquer
  // lugar — inclusive ainda na linha que abriu o modal —, e a seta tem de andar
  // do mesmo jeito.
  useEffect(() => {
    if (!aberto) return;
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      // Quem está escrevendo o motivo ou trocando o status usa as setas para
      // isso, não para pular de clínica.
      if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select")) return;
      const alvo = e.key === "ArrowLeft" ? anterior : e.key === "ArrowRight" ? proxima : null;
      if (!alvo) return;
      e.preventDefault();
      onIr(alvo);
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [aberto, anterior, proxima, onIr]);

  const picosHistorico = serie.filter((s) => s.pico).length;
  const ultimaLiberacao = [...serie].reverse().find((s) => s.liberacoes > 0);
  const marcada = c ? marcadas.has(c.credenciado) : false;

  // A leitura do que o gráfico mostra, em uma frase, só quando há algo a
  // conferir. Previsto ABAIXO da média não é aviso: a janela só conta o que já
  // está agendado, e a agenda vai enchendo até o dia chegar.
  const leitura = !c
    ? null
    : c.previstos > 0 && c.media === 0
      ? `Nenhuma liberação nas 12 semanas da média: ${
          c.previstos === 1
            ? "o pedido previsto não tem histórico recente que o confirme"
            : `os ${c.previstos} previstos não têm histórico recente que os confirme`
        }. ` +
        (ultimaLiberacao
          ? `A última liberação foi na semana de ${ultimaLiberacao.label}.`
          : "Não há liberação em todo o histórico buscado.")
      : c.picoPrevisto
        ? `Mesmo contando só o que já está agendado, os ${c.previstos} previstos passam do dobro do que a média dela ` +
          `faria esperar na janela (${c.esperadoLabel}). ` +
          (picosHistorico
            ? `No histórico, ${picosHistorico} semana${picosHistorico > 1 ? "s foram" : " foi"} pico, em laranja no gráfico.`
            : "Nenhuma semana do histórico foi pico: um volume assim não tem precedente.")
        : null;

  return (
    <Dialog open={aberto && !!c} onOpenChange={(v) => !v && onFechar()}>
      {c && (
        <DialogContent className="flex h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-[1600px] flex-col gap-0 overflow-hidden rounded-[16px] border-[#DFE0E2] bg-white p-0 sm:h-[calc(100dvh-3rem)] sm:w-[calc(100vw-3rem)] sm:max-w-[1600px]">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-[#EDEFF0] py-4 pr-14 pl-6">
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-2.5">
                <DialogTitle className="truncate text-[20px] leading-tight font-semibold text-[#193B4F]">
                  {c.name}
                </DialogTitle>
                {c.picoPrevisto && <MarcaPico />}
              </div>
              <DialogDescription className="mt-1 text-[13px] text-[#767A7B]">
                {c.local} · sem cadastro no ProntuAI
              </DialogDescription>
            </div>

            <div className="flex items-center gap-2.5">
              <label
                className={`flex h-[34px] cursor-pointer items-center gap-2 rounded-[9px] border px-3 text-[13px] transition-colors ${
                  marcada
                    ? "border-[#7EBFCC] bg-[#E6F4F4] text-[#007891]"
                    : "border-[#DFE0E2] text-[#193B4F] hover:border-[#7EBFCC]"
                }`}
              >
                <input
                  type="checkbox"
                  checked={marcada}
                  onChange={() => onMarcar(c.credenciado)}
                  className="size-4 cursor-pointer accent-[#00AFAA]"
                />
                Incluir na simulação
              </label>

              <div className="flex items-center overflow-hidden rounded-[9px] border border-[#DFE0E2]">
                <button
                  type="button"
                  disabled={!anterior}
                  onClick={() => anterior && onIr(anterior)}
                  aria-label="Clínica anterior"
                  title="Clínica anterior (←)"
                  className={BOTAO_NAV}
                >
                  <Seta para="esquerda" />
                </button>
                <span className="min-w-[78px] border-x border-[#DFE0E2] px-2 text-center text-[12.5px] leading-[34px] tabular-nums text-[#767A7B]">
                  {i + 1} de {linhas.length}
                </span>
                <button
                  type="button"
                  disabled={!proxima}
                  onClick={() => proxima && onIr(proxima)}
                  aria-label="Próxima clínica"
                  title="Próxima clínica (→)"
                  className={BOTAO_NAV}
                >
                  <Seta para="direita" />
                </button>
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:overflow-hidden">
            <div className="flex min-h-0 flex-col px-6 pt-5 pb-6">
              <div className="grid grid-cols-2 gap-x-6 gap-y-4 lg:grid-cols-4">
                <NumeroModal
                  rotulo="Média por semana"
                  valor={c.mediaLabel}
                  unidade="/sem"
                  sub={`liberações · ${janelaMedia}`}
                  destaque
                />
                <NumeroModal rotulo="Semanas com liberação" valor={c.regularidadeLabel} sub="das 12 semanas da média" />
                <NumeroModal
                  rotulo="Liberações nas 12 semanas"
                  valor={c.total.toLocaleString("pt-BR")}
                  sub="soma da janela da média"
                />
                <NumeroModal
                  rotulo="Previstos"
                  valor={c.previstos.toLocaleString("pt-BR")}
                  sub={`a liberar ${janelaPrevistos}`}
                  extra={c.picoPrevisto ? <MarcaPico /> : undefined}
                />
              </div>

              {leitura && (
                <div className="mt-4 rounded-[10px] border border-[#F0DDBF] bg-[#FBF5EA] px-4 py-2.5 text-[13px] leading-[1.5] text-[#7A4A17]">
                  {leitura}
                </div>
              )}

              <div className="mt-6 min-h-0 flex-1">
                <GraficoSemanas serie={serie} media={c.media} mediaLabel={c.mediaLabel} />
              </div>
            </div>

            <aside className="flex flex-col gap-6 border-t border-[#EDEFF0] bg-[#FAFBFC] px-6 py-5 lg:overflow-y-auto lg:border-t-0 lg:border-l">
              <EditorAbordagem
                key={`${c.credenciado}|${abordagem?.atualizado_em ?? ""}|${recusarAoAbrir ? "recusar" : ""}`}
                abordagem={abordagem}
                podeEditar={podeEditar}
                recusarAoAbrir={recusarAoAbrir}
                onSalvar={(status, motivo) => onSalvarAbordagem(c.credenciado, status, motivo)}
              />

              <div className="border-t border-[#EDEFF0] pt-5">
                <div className={CABECALHO_TABELA}>Previstos por dia</div>
                <div className="mt-1 text-[11.5px] text-[#9AA3A8]">{janelaPrevistos}</div>
                {c.datas.length > 0 ? (
                  <div className="mt-3.5 flex flex-col gap-2.5">
                    {c.datas.map((d) => (
                      <div key={d.label} className="grid grid-cols-[96px_1fr_34px] items-center gap-3 text-[13px]">
                        <span className="truncate text-[#5F6B72]">{d.label}</span>
                        <div className="h-1.5 overflow-hidden rounded-[3px] bg-[#EDEFF0]">
                          <div
                            className="h-full rounded-[3px] bg-[#007891]"
                            style={{ width: `${(d.n / Math.max(1, ...c.datas.map((x) => x.n))) * 100}%` }}
                          />
                        </div>
                        <span className="text-right font-medium tabular-nums text-[#193B4F]">{d.pedidos}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3.5 text-[13px] text-[#767A7B]">Nenhum pedido com previsão na janela.</div>
                )}
              </div>

              <div className="border-t border-[#EDEFF0] pt-5">
                <div className={CABECALHO_TABELA}>Fora da janela</div>
                <dl className="mt-3 flex flex-col gap-2.5 text-[13px]">
                  {[
                    ["Com a previsão já vencida", c.vencidos],
                    ["Previstos depois da janela", c.depoisDaJanela],
                    ["Documentos já enviados ao ProntuAI", c.documentos],
                  ].map(([rotulo, valor]) => (
                    <div key={rotulo} className="flex items-baseline justify-between gap-4">
                      <dt className="text-[#5F6B72]">{rotulo}</dt>
                      <dd className="font-medium tabular-nums text-[#193B4F]">{Number(valor).toLocaleString("pt-BR")}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              <div className="mt-auto border-t border-[#EDEFF0] pt-4 text-[11.5px] leading-snug text-[#9AA3A8]">
                <div>No BRNET: {c.credenciado}</div>
                <div className="mt-2">← → passam para a clínica anterior ou a seguinte · Esc fecha</div>
              </div>
            </aside>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}

function CartaoKpi({
  kpi,
  onAjuda,
  onValor,
}: {
  kpi: Kpi;
  onAjuda: AbrirAjuda;
  /** Torna o número clicável — abre o detalhe por trás dele. */
  onValor?: () => void;
}) {
  const ajuda = kpi.ajuda;
  const valor = (
    <div
      className={`whitespace-nowrap text-[36px] font-medium leading-none tracking-[-0.025em] text-[#193B4F] tabular-nums ${
        onValor ? "transition-colors group-hover:text-[#007891]" : ""
      }`}
    >
      {kpi.value}
    </div>
  );
  return (
    <div
      className={`${styles.tip} ${styles.tipBaixo} flex flex-col gap-4 rounded-xl border border-[#DFE0E2] bg-white px-[22px] pt-5 pb-[22px]`}
      data-tip={kpi.tip}
    >
      <div className="flex items-center gap-2">
        <div className="text-[13px] text-[#767A7B]">{kpi.label}</div>
        {ajuda && <BotaoAjuda rotulo={kpi.label} onClick={() => onAjuda(ajuda)} />}
      </div>
      <div className="flex flex-col items-start gap-2">
        {onValor ? (
          <button
            type="button"
            onClick={onValor}
            aria-haspopup="dialog"
            aria-label={`Ver ${kpi.label.toLowerCase()}`}
            title="Ver por exame"
            className="group cursor-pointer rounded-[6px] text-left"
          >
            {valor}
          </button>
        ) : (
          valor
        )}
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
function CartaoPrazo({
  titulo,
  sub,
  grafico,
  ajuda,
  onAjuda,
}: {
  titulo: string;
  sub: string;
  grafico: GraficoPrazo;
  ajuda: IdIndicador;
  onAjuda: AbrirAjuda;
}) {
  return (
    <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <TituloCartao texto={titulo} ajuda={ajuda} onAjuda={onAjuda} />
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
  onAjuda,
}: {
  visao: VisaoDashboard;
  verTodas: boolean;
  onVerTodas: () => void;
  onAjuda: AbrirAjuda;
}) {
  return (
    <div className="flex flex-col gap-5 px-[34px] pt-[26px] pb-10">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {visao.kpiPrimary.map((k) => (
          <CartaoKpi key={k.label} kpi={k} onAjuda={onAjuda} />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        {/* Envios realizados: volume por período, em barra */}
        <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
          <TituloCartao texto="Envios realizados" ajuda="enviados" onAjuda={onAjuda} />
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
          <TituloCartao texto="Ranking de clínicas" ajuda="ranking" onAjuda={onAjuda} />
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
          ajuda="prazoClinica"
          onAjuda={onAjuda}
        />
        <CartaoPrazo
          titulo="Liberação do técnico de credenciados × prazo da BR MED"
          sub={`${visao.graficoLegenda} · prazo da BR MED = 1 dia útil após o da clínica · só aprovações do técnico`}
          grafico={visao.prazoTecnico}
          ajuda="prazoTecnico"
          onAjuda={onAjuda}
        />
      </div>

      <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
        {/* Cobertura do ProntuAI sobre as expedições, ponto a ponto. O card de
            expedições saiu da fileira de cima; a conta continua só aqui. */}
        <TituloCartao texto="Cobertura das expedições" ajuda="expedicoes" onAjuda={onAjuda} />
        <div className={SUB}>
          % dos pedidos atendidos nas credenciadas que passaram pelo ProntuAI · meta 100%
        </div>
        <BarrasPercentuais series={visao.coberturaSeries} cor="#00AFAA" />
      </div>

      {/* Bloco de previsão. Duas perguntas, nesta ordem: quem já está dentro e
          usa pouco (adesão, semana fechada), e quem ainda está fora e vale a
          pena incluir. Nenhum número se repete entre os dois. */}
      {visao.usoSemanal && <TabelaUsoSemana uso={visao.usoSemanal} onAjuda={onAjuda} />}

      <div className={`${CARTAO} px-[22px] pt-5 pb-5`}>
        <TituloCartao texto="Quem vale a pena incluir" ajuda="valeIncluir" onAjuda={onAjuda} />
        <div className={SUB}>
          {visao.foraProntuai === null
            ? "Lista indisponível: não foi possível consultar o BRNET na última atualização"
            : `${visao.foraProntuai.length} credenciadas sem cadastro habilitado · ranqueadas pelos pedidos previstos ${visao.janelaPrevistos} · PICO marca previsto muito acima do ritmo da clínica`}
        </div>
        {visao.foraProntuai && visao.foraProntuai.length > 0 && (
          <TabelaForaProntuai
            linhas={visao.foraProntuai}
            janelaMedia={visao.janelaMedia}
            janelaPrevistos={visao.janelaPrevistos}
            simulador={visao.simulador}
          />
        )}
      </div>
    </div>
  );
}

/**
 * Lugar reservado para "Acurácia por exame" quando o back-end não manda o
 * indicador (versão anterior a ele, ou a consulta dos pareceres falhou). Mesmo
 * tamanho dos KPIs, ao lado de "Acurácia".
 */
function CartaoEmBreve({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-[#DFE0E2] bg-white px-[22px] pt-5 pb-[22px]">
      <div className="text-[13px] text-[#767A7B]">{label}</div>
      <div className="text-[30px] font-medium leading-none tracking-[-0.02em] text-[#9AA3A8]">Em breve</div>
    </div>
  );
}

// Literal pelo mesmo motivo de COLUNAS_FORA: o Tailwind só compila a classe que
// encontra escrita no código.
const COLUNAS_EXAME = "grid-cols-[2.6fr_0.8fr_1.6fr_0.7fr]";

/**
 * O que abre ao clicar no exame: os motivos, com as palavras do modal de
 * feedback e o que a IA tinha dito, e os documentos em que o erro aconteceu.
 * "Abrir" leva ao documento no Histórico (`?viewId=`) em outra aba, para
 * conferir o PDF sem perder a lista.
 */
function DetalheErrosExame({ linha }: { linha: LinhaAcuraciaExame }) {
  return (
    <div className="mb-3 ml-[26px] grid grid-cols-1 gap-x-10 gap-y-4 rounded-[10px] bg-[#F7F9FA] px-4 py-3.5 text-[12.5px] md:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)]">
      <div>
        <div className={CABECALHO_TABELA}>Motivos</div>
        <ul className="mt-2 flex flex-col gap-1.5">
          {linha.motivos.map((m) => (
            <li key={m.rotulo} className="flex items-baseline gap-2.5 text-[#193B4F]">
              <span className="w-5 flex-none text-right font-medium tabular-nums">{m.casos}</span>
              <span>
                {m.rotulo}
                {m.contexto && <span className="text-[#9AA3A8]"> · {m.contexto}</span>}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <div className={CABECALHO_TABELA}>Documentos com erro</div>
        {linha.casos.length ? (
          <ul className="mt-2 flex flex-col gap-1.5">
            {linha.casos.map((c, i) => (
              <li
                key={`${c.documento}-${i}`}
                className="grid grid-cols-[2.75rem_minmax(0,1fr)_auto_auto] items-baseline gap-3 text-[#193B4F]"
              >
                <span className="tabular-nums text-[#767A7B]">{c.enviadoLabel}</span>
                <span className="truncate" title={c.clinica}>
                  {c.clinica}
                </span>
                <span className="text-[#767A7B]">{c.motivo}</span>
                <a
                  href={`/historico?viewId=${encodeURIComponent(c.documento)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-[#007891] hover:underline"
                >
                  Abrir
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-2 text-[#9AA3A8]">O back-end desta versão ainda não manda os documentos.</div>
        )}
      </div>
    </div>
  );
}

/**
 * Uma linha da lista. Só o exame com erro abre: o detalhe de um exame sem erro
 * seria vazio. Em "Poucos casos" não há barra nem percentual — só a contagem.
 */
function LinhaExame({
  linha,
  aberta,
  onAlternar,
  semPercentual = false,
}: {
  linha: LinhaAcuraciaExame;
  aberta: boolean;
  onAlternar: () => void;
  semPercentual?: boolean;
}) {
  const n = (v: number) => v.toLocaleString("pt-BR");
  // Mesmo invólucro de "Quem está usando pouco": a seta do balão aponta para o
  // nome só se ele encolher até o texto.
  const nome = (
    <span className={`${styles.tip} ${styles.tipNome} min-w-0`} data-tip={linha.tip}>
      <span className="block truncate">{linha.exame}</span>
    </span>
  );
  return (
    <div className="border-b border-[#F3F3F3]">
      <div
        className={`${styles.linhaTip} grid ${COLUNAS_EXAME} items-center gap-x-[18px] px-1 py-3 text-[13.5px] text-[#193B4F]`}
      >
        <div className="min-w-0">
          {linha.erros ? (
            <button
              type="button"
              onClick={onAlternar}
              aria-expanded={aberta}
              className="flex w-full min-w-0 items-center gap-2 text-left hover:text-[#007891]"
            >
              <ChevronRight
                className={`size-4 flex-none text-[#9AA3A8] transition-transform ${aberta ? "rotate-90" : ""}`}
              />
              {nome}
            </button>
          ) : (
            <div className="flex min-w-0 pl-6">{nome}</div>
          )}
        </div>
        <div className="tabular-nums text-[#767A7B]">{n(linha.documentos)}</div>
        {semPercentual ? (
          <div className="font-medium tabular-nums">{linha.erros}</div>
        ) : (
          <div className="flex items-center gap-2.5">
            <div className="h-[9px] flex-1 overflow-hidden rounded-[4px] bg-[#F3F3F3]">
              <div className="h-full bg-[#B4453A]" style={{ width: `${linha.pctErro}%` }} />
            </div>
            <div className="w-[26px] text-right font-medium tabular-nums">{linha.erros || "—"}</div>
          </div>
        )}
        {semPercentual ? (
          <div className="text-[#C6CBCE]">—</div>
        ) : (
          <div className="font-medium tabular-nums">{linha.acuraciaLabel}</div>
        )}
      </div>
      {aberta && <DetalheErrosExame linha={linha} />}
    </div>
  );
}

/**
 * A lista de "Acurácia por exame", aberta pelo número do card. Vem do parecer
 * do revisor no modal de feedback e segue o filtro de período da tela.
 *
 * A adesão fica no cabeçalho, junto do número: a acurácia só enxerga os
 * documentos com parecer, e com poucos pareceres ela pesa pouco.
 *
 * A pergunta é "em quais exames o processo tem mais dificuldade, e por quê" —
 * quem lê é o time de desenvolvimento. A tabela fica no essencial, da menor
 * acurácia para a maior; o porquê abre no clique, com os documentos para
 * conferir.
 */
function ModalAcuraciaExame({
  dados,
  aberto,
  onFechar,
}: {
  dados: AcuraciaExameVisao;
  aberto: boolean;
  onFechar: () => void;
}) {
  const { ordem, ordenarPor } = useOrdem({ col: "acuracia", dir: "asc" });
  const visiveis = ordenar(dados.linhas, ordem, (l, col) =>
    col === "exame" ? l.exame
    : col === "documentos" ? l.documentos
    : col === "erros" ? l.erros
    : l.acuracia,
  );
  const [abertos, setAbertos] = useState<Set<string>>(() => new Set());
  const alternar = (exame: string) =>
    setAbertos((atual) => {
      const novo = new Set(atual);
      if (!novo.delete(exame)) novo.add(exame);
      return novo;
    });
  const n = (v: number) => v.toLocaleString("pt-BR");

  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && onFechar()}>
      <DialogContent className="flex max-h-[calc(100dvh-3rem)] flex-col gap-0 overflow-hidden rounded-[16px] border-[#DFE0E2] bg-white p-0 sm:max-w-[980px]">
        {/* Título e descrição ocupam a largura toda, e os números descem para
            uma fileira própria: com o total à direita da descrição, os dois
            disputavam a mesma linha e o número ficava espremido contra o X. */}
        <div className="border-b border-[#EDEFF0] py-4 pr-14 pl-6">
          <DialogTitle className="text-[20px] leading-tight font-semibold text-[#193B4F]">
            Acurácia por exame
          </DialogTitle>
          <DialogDescription className="mt-1 text-[13px] leading-[1.5] text-[#767A7B]">
            Pelo parecer do revisor no modal de feedback · documentos enviados em {dados.periodoLabel}.
            <span className="block">
              {dados.adesaoLabel
                ? `${n(dados.pareceres)} pareceres em ${n(dados.decisoes)} decisões do time BR MED (adesão de ${dados.adesaoLabel}).`
                : "Nenhuma decisão do time BR MED com parecer neste período."}
            </span>
          </DialogDescription>

          <div className="mt-4 flex flex-wrap items-start gap-x-8 gap-y-3">
            {[
              { r: "Acurácia", v: dados.acuraciaLabel, cor: "#007891" },
              { r: "Exames nos pareceres", v: n(dados.avaliacoes) },
              { r: "Erros", v: n(dados.erros) },
              { r: "Pareceres", v: n(dados.pareceres) },
            ].map((x: { r: string; v: string; cor?: string }) => (
              <div key={x.r} className="flex flex-col gap-1">
                <div className={CABECALHO_TABELA}>{x.r}</div>
                <div
                  className="text-[19px] font-medium leading-none tabular-nums"
                  style={{ color: x.cor ?? "#193B4F" }}
                >
                  {x.v}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-6">
          {visiveis.length || dados.poucosCasos.length ? (
            <div className="min-w-[720px]">
              <div
                className={`sticky top-0 z-10 grid ${COLUNAS_EXAME} items-end gap-x-[18px] border-b border-[#DFE0E2] bg-white px-1 pt-3.5 pb-2.5`}
              >
                <div className="pl-6">
                  <Th label="Exame" col="exame" ordem={ordem} onOrdenar={ordenarPor} />
                </div>
                <Th label="Exames" col="documentos" ordem={ordem} onOrdenar={ordenarPor} numerica />
                <Th label="Erros" sub="barra = taxa · número = casos" col="erros" ordem={ordem} onOrdenar={ordenarPor} numerica />
                <Th label="Acurácia" col="acuracia" ordem={ordem} onOrdenar={ordenarPor} numerica />
              </div>
              {visiveis.map((l) => (
                <LinhaExame key={l.exame} linha={l} aberta={abertos.has(l.exame)} onAlternar={() => alternar(l.exame)} />
              ))}

              {/* Abaixo do mínimo, só a contagem: com 1 erro em 2, o percentual
                  poria o exame no topo da lista sem que isso diga muito. Mas o
                  erro aconteceu, e quem corrige o motor precisa vê-lo. */}
              {dados.poucosCasos.length > 0 && (
                <>
                  <div className="px-1 pt-6 pb-2">
                    <div className={CABECALHO_TABELA}>Poucos casos</div>
                    <div className="mt-1 text-[12px] text-[#9AA3A8]">
                      Menos de {dados.minimo} exames no período, com erro. Sem percentual: um erro sozinho o derrubaria.
                    </div>
                  </div>
                  {dados.poucosCasos.map((l) => (
                    <LinhaExame
                      key={l.exame}
                      linha={l}
                      aberta={abertos.has(l.exame)}
                      onAlternar={() => alternar(l.exame)}
                      semPercentual
                    />
                  ))}
                </>
              )}
            </div>
          ) : (
            <div className="py-10 text-center text-[13px] text-[#767A7B]">
              {dados.avaliacoes
                ? `Nenhum exame chegou a ${dados.minimo} avaliações neste período, e nenhum teve erro.`
                : "Nenhum parecer neste período."}
            </div>
          )}
        </div>

        <div className="border-t border-[#EDEFF0] px-6 py-3 text-[12px] text-[#9AA3A8]">
          Clique no exame para ver os motivos e os documentos com erro. Da menor acurácia para a maior; no empate,
          o que tem mais erros primeiro. Exames com menos de {dados.minimo} avaliações e sem erro entram no total,
          mas não na lista{dados.abaixoDoMinimo ? ` (${n(dados.abaixoDoMinimo)} neste período)` : ""}.
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AbaAcuracia({ visao, onAjuda }: { visao: VisaoDashboard; onAjuda: AbrirAjuda }) {
  const [examesAberto, setExamesAberto] = useState(false);
  // "Acurácia por exame" entra logo depois de "Acurácia": é o mesmo número
  // aberto por exame, e quem lê um procura o outro do lado.
  const [acuracia, ...demais] = visao.kpisAcuracia;
  const porExame = visao.acuraciaExame;

  return (
    <div className="flex flex-col gap-5 px-[34px] pt-[26px] pb-10">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <CartaoKpi kpi={acuracia} onAjuda={onAjuda} />
        {/* Sem o bloco no back-end (versão anterior ao indicador, ou a consulta
            falhou), o lugar fica reservado em vez de mostrar um zero falso. */}
        {porExame ? (
          <CartaoKpi
            kpi={porExame.kpi}
            onAjuda={onAjuda}
            onValor={porExame.avaliacoes ? () => setExamesAberto(true) : undefined}
          />
        ) : (
          <CartaoEmBreve label="Acurácia por exame" />
        )}
        {demais.map((k) => (
          <CartaoKpi key={k.label} kpi={k} onAjuda={onAjuda} />
        ))}
      </div>
      {porExame && (
        <ModalAcuraciaExame dados={porExame} aberto={examesAberto} onFechar={() => setExamesAberto(false)} />
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
          <TituloCartao texto="Acurácia por período" ajuda="acuracia" onAjuda={onAjuda} />
          <div className={SUB}>
            {visao.graficoLegenda} · concordância entre IA e revisor · escala a partir de 70%
          </div>
          <BarrasPercentuais series={visao.acuraciaSeries} cor="#007891" />
        </div>

        <div className={`${CARTAO} px-[22px] pt-5 pb-[18px]`}>
          <TituloCartao texto="Por que a acurácia não está maior" ajuda="motivos" onAjuda={onAjuda}>
            <div className="rounded-[5px] bg-[#F7EDDC] px-2 py-1 text-[10.5px] font-medium tracking-[0.08em] text-[#A05E1E]">
              A CONFIRMAR
            </div>
          </TituloCartao>
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
          {/* Não derrubam a acurácia — contam como acerto —, mas explicam por
              que o revisor contrariou a IA. Pelo código do parecer do modal. */}
          {visao.motivosExternos.length > 0 && (
            <div className="mt-[18px] border-t border-[#EDEFF0] pt-3.5">
              <div className="text-[12.5px] text-[#767A7B]">
                Resolvidas por motivo externo · {visao.motivosExternosTotal.toLocaleString("pt-BR")} divergências que
                contam como acerto
              </div>
              <ul className="mt-2 flex flex-col gap-1">
                {visao.motivosExternos.map((m) => (
                  <li key={m.name} className="flex items-baseline justify-between gap-2.5 text-[13px] text-[#193B4F]">
                    <span>{m.name}</span>
                    <span className="font-medium tabular-nums text-[#767A7B]">{m.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-[18px] rounded-[10px] bg-[#F3F3F3] px-3.5 py-3 text-[12.5px] leading-[1.5] text-[#767A7B]">
            {visao.notaSemJustificativa}
          </div>
        </div>
      </div>

      <div className={`${CARTAO} px-[22px] pt-5 pb-2`}>
        <TituloCartao texto="Matriz de decisão" ajuda="matriz" onAjuda={onAjuda} />
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
