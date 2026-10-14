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
  LinhaForaProntuai,
  UsoSemanal,
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
function TabelaUsoSemana({ uso }: { uso: UsoSemanal }) {
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
          <div className={TITULO}>Quem está usando pouco</div>
          <div className={SUB}>
            Do que estava previsto para a semana, quanto passou pela plataforma · semana fechada
          </div>
        </div>

        {/* Navegação por semana. Para trás é o passado, e o passado acaba: os
            botões travam nas pontas em vez de rodarem em círculo. */}
        <div className="flex items-center gap-1.5 rounded-[10px] border border-[#DFE0E2] bg-white p-1">
          <button
            type="button"
            onClick={() => setI((v) => Math.min(v + 1, uso.semanas.length - 1))}
            disabled={i >= uso.semanas.length - 1}
            aria-label="Semana anterior"
            className="size-[26px] rounded-[7px] text-[13px] text-[#193B4F] transition-colors hover:bg-[#F3F3F3] disabled:text-[#C6CBCE] disabled:hover:bg-transparent"
          >
            ‹
          </button>
          <div className="min-w-[108px] text-center text-[13px] font-medium tabular-nums text-[#193B4F]">
            {semana.label}
          </div>
          <button
            type="button"
            onClick={() => setI((v) => Math.max(v - 1, 0))}
            disabled={i === 0}
            aria-label="Semana seguinte"
            className="size-[26px] rounded-[7px] text-[13px] text-[#193B4F] transition-colors hover:bg-[#F3F3F3] disabled:text-[#C6CBCE] disabled:hover:bg-transparent"
          >
            ›
          </button>
        </div>
      </div>

      {/* Total da semana: o mesmo desenho da linha, em escala maior. Quem
          entende a barra de cima já entende as 118 de baixo. */}
      <div className="mt-[18px] flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          {[
            { r: "Previstos na semana", v: semana.previstos, cor: "#193B4F" },
            { r: "Via ProntuAI", v: semana.viaProntuai, cor: "#007891" },
            { r: "Liberado por fora", v: semana.fora, cor: "#CC851E" },
            { r: "Não liberado", v: semana.naoLiberado, cor: "#767A7B" },
          ].map((x) => (
            <div key={x.r} className="flex flex-col gap-1">
              <div className={CABECALHO_TABELA}>{x.r}</div>
              <div className="text-[19px] font-medium leading-none tabular-nums" style={{ color: x.cor }}>
                {x.v.toLocaleString("pt-BR")}
              </div>
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
              {/* Mesma estrutura de "Adoção por clínica", e por um motivo de
                  CSS, não de estilo: `.tipNome` é `inline-block` para encolher
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
}: {
  linhas: LinhaForaProntuai[];
  selecionadas: Set<string>;
  /** Pedidos que passaram pela plataforma na última semana fechada. */
  viaProntuaiSemana: number;
  /** Adesão daquela mesma semana, em %. */
  adesao: number;
  semana: string;
  onAtalho: (quantas: number | "limpar") => void;
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
const COLUNAS_FORA = "grid-cols-[28px_1.7fr_1fr_2fr_1.05fr_1.05fr]";
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
 * média, a marca de PICO e o gráfico que abre na linha. Ranquear pelo futuro,
 * desconfiar, clicar, conferir no passado.
 *
 * Nenhuma métrica de adesão aqui. Adesão é sobre quem já está dentro, e mora no
 * indicador de cima.
 */
function TabelaForaProntuai({
  linhas,
  janelaMedia,
  simulador,
}: {
  linhas: LinhaForaProntuai[];
  /** Intervalo das 12 semanas que entram na média: "27/07 a 05/10". */
  janelaMedia: string;
  simulador: { viaProntuaiSemana: number; adesao: number; semana: string } | null;
}) {
  const { ordem, ordenarPor } = useOrdem({ col: "previstos", dir: "desc" });
  const [busca, setBusca] = useState("");
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());

  const termo = semAcento(busca.trim());
  const filtradas = linhas.filter(
    (l) => !termo || semAcento(l.name).includes(termo) || semAcento(l.local).includes(termo),
  );
  const visiveis = ordenar(filtradas, ordem, (l, col) =>
    col === "name" ? l.name
    : col === "local" ? l.local
    : col === "previstos" ? l.previstos
    : col === "regularidade" ? l.regularidade
    : l.media,
  );

  const aplicarAtalho = (quantas: number | "limpar") =>
    setMarcadas(
      quantas === "limpar"
        ? new Set()
        : new Set(visiveis.slice(0, quantas).map((l) => l.credenciado)),
    );
  const alternar = (credenciado: string) =>
    setMarcadas((atual) => {
      const proximo = new Set(atual);
      if (!proximo.delete(credenciado)) proximo.add(credenciado);
      return proximo;
    });

  return (
    <>
      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        <CampoBusca valor={busca} onChange={setBusca} placeholder="Buscar clínica ou cidade" />
        {termo && (
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
        />
      )}

      <div className="mt-3 max-h-[460px] overflow-auto">
        <div className="min-w-[920px]">
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
          </div>
          {visiveis.map((c) => (
            <LinhaFora
              key={c.credenciado}
              c={c}
              janelaMedia={janelaMedia}
              marcada={marcadas.has(c.credenciado)}
              onMarcar={alternar}
            />
          ))}
          {!visiveis.length && (
            <div className="px-1 py-6 text-[13px] text-[#767A7B]">Nenhuma clínica com esses filtros.</div>
          )}
        </div>
      </div>
    </>
  );
}

/**
 * Linha do ranking, com o histórico semanal no painel que abre.
 *
 * O gráfico é o argumento inteiro do indicador: a linha tracejada é a média, e
 * a coluna que sobe muito acima dela está marcada. É olhando para ele que se
 * decide se o volume da clínica é comportamento ou foi uma semana.
 */
function LinhaFora({
  c,
  janelaMedia,
  marcada,
  onMarcar,
}: {
  c: LinhaForaProntuai;
  janelaMedia: string;
  marcada: boolean;
  onMarcar: (credenciado: string) => void;
}) {
  const [aberta, setAberta] = useState(false);
  const maior = Math.max(1, ...c.serie.map((s) => s.liberacoes));
  return (
    <div className={`border-b border-[#F3F3F3] ${marcada ? "bg-[#E6EDF4]" : ""}`}>
      {/* A marcação do simulador fica fora do botão que abre o histórico:
          aninhar input em button é inválido, e o clique de um roubaria o do outro. */}
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
          onClick={() => setAberta((v) => !v)}
          aria-expanded={aberta}
          className={`col-span-5 grid ${COLUNAS_FORA_LINHA} items-center gap-x-[18px] rounded-[6px] py-3 text-left text-[13.5px] text-[#193B4F] transition-colors hover:bg-[#F7F9FA]`}
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
            {c.picoPrevisto && (
              <span className="rounded-[5px] bg-[#F7EDDC] px-1.5 py-0.5 text-[10px] font-medium tracking-[0.04em] text-[#A05E1E]">
                PICO
              </span>
            )}
          </div>
        </button>
      </div>

      {aberta && (
        <div className="mb-3 ml-[54px] mr-1 rounded-[10px] border border-[#DFE0E2] bg-[#FAFBFC] px-4 py-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <div className={CABECALHO_TABELA}>Liberações por semana · uma coluna = uma semana</div>
            <div className="text-[12.5px] text-[#767A7B]">
              média de {c.mediaLabel} por semana · {c.semanasAtivas} das 12 semanas de {janelaMedia} com
              liberação · {c.total} liberações nessas 12 semanas
            </div>
          </div>

          {c.serie.length > 0 ? (
            <>
              <div className="relative mt-3.5 flex h-[96px] items-end gap-[3px]">
                {/* A tracejada é a média. Fica por cima das colunas, não atrás:
                    o que se quer ver é quais delas a ultrapassam. */}
                <div
                  className="pointer-events-none absolute inset-x-0 z-10 border-t border-dashed border-[#B4453A]"
                  style={{ bottom: `${(c.media / maior) * 86}px` }}
                />
                {c.serie.map((s) => (
                  <div
                    key={s.label}
                    className={`${styles.tip} flex flex-1 flex-col items-center justify-end`}
                    data-tip={s.tip}
                  >
                    <div
                      className="w-full rounded-t-[3px]"
                      style={{ height: `${Math.max(s.h, s.liberacoes ? 2 : 0)}px`, background: s.pico ? "#CC851E" : "#7EBFCC" }}
                    />
                  </div>
                ))}
              </div>
              <div className="mt-1.5 flex gap-[3px]">
                {c.serie.map((s, i) => (
                  <div key={s.label} className="flex-1 text-center text-[9.5px] text-[#9AA3A8]">
                    {/* Com 30 semanas o rótulo em toda coluna vira um borrão:
                        um a cada quatro basta para situar o eixo. */}
                    {i % 4 === 0 ? s.label : ""}
                  </div>
                ))}
              </div>
              <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-[#767A7B]">
                <span className="flex items-center gap-1.5">
                  <span className="h-[3px] w-4 border-t border-dashed border-[#B4453A]" /> média
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="size-2.5 rounded-[2px] bg-[#CC851E]" /> semana fora do ritmo dela
                </span>
              </div>
            </>
          ) : (
            <div className="mt-2.5 text-[13px] text-[#767A7B]">
              Sem liberações no histórico do BRNET — só previsão futura.
            </div>
          )}

          {c.datas.length > 0 && (
            <div className="mt-3.5 border-t border-[#EDEFF0] pt-3">
              <div className={CABECALHO_TABELA}>Datas das previsões</div>
              <div className="mt-2 flex flex-col">
                {c.datas.map((d) => (
                  <div
                    key={d.label}
                    className="flex items-baseline justify-between gap-6 border-b border-[#EDEFF0] py-[6px] text-[13px] last:border-b-0"
                  >
                    <span className="text-[#5F6B72]">{d.label}</span>
                    <span className="font-medium tabular-nums text-[#193B4F]">{d.pedidos}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

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

      {/* Bloco de previsão. Duas perguntas, nesta ordem: quem já está dentro e
          usa pouco (adesão, semana fechada), e quem ainda está fora e vale a
          pena incluir. Nenhum número se repete entre os dois. */}
      {visao.usoSemanal && <TabelaUsoSemana uso={visao.usoSemanal} />}

      <div className={`${CARTAO} px-[22px] pt-5 pb-5`}>
        <div className={TITULO}>Quem vale a pena incluir</div>
        <div className={SUB}>
          {visao.foraProntuai === null
            ? "Lista indisponível: não foi possível consultar o BRNET na última atualização"
            : `${visao.foraProntuai.length} credenciadas sem cadastro habilitado · ranqueadas pelos pedidos previstos ${visao.janelaPrevistos} · PICO marca previsto muito acima do ritmo da clínica`}
        </div>
        {visao.foraProntuai && visao.foraProntuai.length > 0 && (
          <TabelaForaProntuai
            linhas={visao.foraProntuai}
            janelaMedia={visao.janelaMedia}
            simulador={visao.simulador}
          />
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
