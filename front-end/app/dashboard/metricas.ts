/**
 * Derivação dos indicadores do dashboard.
 *
 * Não toca em React nem em fetch: recebe `DadosDashboard` mais os filtros da
 * tela e devolve tudo já formatado em pt-BR, pronto para renderizar. Manter a
 * conta aqui é o que permite trocar a origem dos dados (JSON estático hoje,
 * consulta no back-end depois) sem mexer na tela.
 */
import type {
  ClinicaDados,
  CredenciadoPrevisto,
  DadosDashboard,
  PrevisaoDia,
  PontoAcuracia,
  PontoSerie,
  Prazos,
  SerieKey,
} from "./tipos";

// ── paleta ───────────────────────────────────────────────────────────────────
export const CORES = {
  tinta: "#193B4F",
  petroleo: "#007891",
  turquesa: "#00AFAA",
  agua: "#7EBFCC",
  positivo: "#2CAD6E",
  negativo: "#B4453A",
  alerta: "#CC851E",
  neutro: "#767A7B",
  borda: "#DFE0E2",
  fundo: "#F3F3F3",
} as const;

const POS = CORES.positivo;
const NEG = CORES.negativo;
const MUTED = CORES.neutro;
const CORES_RANK = ["#193B4F", "#007891", "#007891", "#00AFAA", "#00AFAA", "#7EBFCC"];

// ── filtros ──────────────────────────────────────────────────────────────────
export type FiltroPeriodo = "Semanal" | "Mensal" | "Trimestral" | "Tudo";
export type Aba = "utilizacao" | "acuracia";

/**
 * Cada filtro define DUAS coisas: o período dos indicadores (KPIs, ranking e
 * tabela) e a série de contexto mostrada nos gráficos de barra.
 *   periodo.serie / periodo.n -> quantos pontos entram nos números
 *   grafico.serie / grafico.n -> quantos pontos aparecem nas barras (0 = todos)
 */
const PERIODOS: Record<
  FiltroPeriodo,
  { label: string; periodo: { serie: SerieKey; n: number }; grafico: { serie: SerieKey; n: number } }
> = {
  Semanal: { label: "Semana", periodo: { serie: "semanal", n: 1 }, grafico: { serie: "semanal", n: 8 } },
  Mensal: { label: "Mês", periodo: { serie: "mensal", n: 1 }, grafico: { serie: "mensal", n: 6 } },
  Trimestral: { label: "3 meses", periodo: { serie: "mensal", n: 3 }, grafico: { serie: "mensal", n: 6 } },
  Tudo: { label: "Tudo", periodo: { serie: "mensal", n: 0 }, grafico: { serie: "mensal", n: 0 } },
};

/**
 * Janela do card "Pedidos previstos", em dias contados a partir de hoje.
 *
 * Os gráficos e KPIs olham para TRÁS; previsão de liberação olha para frente, e
 * as duas janelas não podem ser a mesma. O card reaproveita o filtro já
 * escolhido na tela — não há seletor nem período próprio — e a duração dele vira
 * o alcance para frente, com teto de um mês: previsão do BRNET a mais de 30 dias
 * é rara e instável (o prazo do credenciado é de 1 a 3 dias úteis após o
 * atendimento), então "3 meses" e "Tudo" mostrariam uma cauda sem uso
 * operacional. Por isso os dois caem no mesmo teto.
 */
const JANELA_PREVISTOS: Record<FiltroPeriodo, number> = {
  Semanal: 7,
  Mensal: 30,
  Trimestral: 30,
  Tudo: 30,
};

export const ORDEM_FILTROS: FiltroPeriodo[] = ["Semanal", "Mensal", "Trimestral", "Tudo"];

export const ROTULO_FILTRO = (f: FiltroPeriodo) => PERIODOS[f].label;

export const ABAS: { id: Aba; label: string }[] = [
  { id: "utilizacao", label: "Utilização" },
  { id: "acuracia", label: "Acurácia" },
];

// ── textos de apoio ──────────────────────────────────────────────────────────
const TIPS_KPI: Record<string, string> = {
  "Documentos enviados": "Prontuários recebidos pela plataforma no período.",
  "Documentos revisados": "Já com decisão humana: aprovados ou rejeitados por um revisor.",
  "Expedições via ProntuAI":
    "Pedidos atendidos nas credenciadas que tiveram o prontuário processado pelo ProntuAI, ligados pelo número do pedido no BRNET. Meta: 100%.",
};

const TIPS_ACC: Record<string, string> = {
  Acurácia:
    "Quantas vezes a IA e o revisor chegaram à mesma conclusão. Clique no ? para ver o cálculo.",
  "Concordância direta":
    "Só os casos em que IA e revisor concordaram de imediato, sem contar as decisões resolvidas por motivo externo.",
  "Aprovações derrubadas":
    "A IA liberou e o revisor barrou. É o erro com consequência: sem revisão, o documento teria passado.",
  "Falhas técnicas":
    "A IA não conseguiu ler o CPF/CNPJ ou achar o paciente. Não é julgamento, por isso fica fora da acurácia.",
};

export const AJUDA_ACURACIA = [
  {
    titulo: "Como a IA decide",
    texto:
      "A IA faz uma coisa só: confere se o prontuário tem todos os exames que a grade exige. A partir disso ela dá um de dois vereditos — aprova (libera o documento) ou rejeita (aponta o que falta e manda para a fila Pendentes, onde um checador decide).",
  },
  {
    titulo: "O que não entra na conta",
    texto:
      "Existe um terceiro desfecho que não é veredito: quando a IA não consegue nem ler o documento, porque não achou o CPF, o CNPJ veio errado ou o paciente não estava no BRNET. Isso é falha técnica de leitura, não julgamento. Fica fora da acurácia e é acompanhado à parte — seria como reprovar um revisor por causa de uma folha que chegou rasgada.",
  },
  {
    titulo: "O que é acurácia aqui",
    texto:
      "Acurácia é concordância direta: quantas vezes a IA e o revisor humano chegaram à mesma conclusão. Conta como acerto quando a IA aprovou e o humano confirmou, e quando a IA rejeitou e o humano confirmou a rejeição.",
  },
  {
    titulo: "A exceção: motivo externo",
    texto:
      "Nem toda divergência é erro da IA. Às vezes o revisor contraria a IA por uma razão que estava fora do documento — o exame chegou por outro canal, o paciente já tinha o resultado no sistema, a clínica confirmou por fora. Nesses casos a leitura da IA estava certa para o que ela tinha em mãos, e o caso conta como acerto.",
  },
  {
    titulo: "Onde mora o risco",
    texto:
      "O motivo externo aparece muito mais de um lado que do outro. Quando a IA rejeita e o humano libera, um terço das vezes é motivo externo. Mas quando a IA aprova e o humano derruba, quase nunca é — nesses casos a IA errou de verdade, e é aí que existe o risco de um documento incompleto passar batido.",
  },
];

// ── formatação e datas ───────────────────────────────────────────────────────
const MESES_ABBR = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];

const pad = (n: number) => String(n).padStart(2, "0");

const partes = (chave: string) => {
  const [y, m, d] = chave.split("-").map(Number);
  return { y, m, d };
};

const rotuloSemana = (chave: string) => {
  const { m, d } = partes(chave);
  return `${pad(d)}/${pad(m)}`;
};

const rotuloMes = (chave: string) => {
  const { y, m } = partes(chave);
  return `${MESES_ABBR[m - 1]}/${String(y).slice(2)}`;
};

const fmt = (v: number) => v.toLocaleString("pt-BR");
const num = (v: number) => `${v.toFixed(1).replace(".", ",")}%`;
const pct = (a: number, b: number) => (b ? (a / b) * 100 : 0);

/** Variação em pontos percentuais entre duas taxas. */
const pp = (atualPct: number, antPct: number | null) =>
  antPct === null
    ? ""
    : `${atualPct >= antPct ? "+" : "-"}${Math.abs(atualPct - antPct).toFixed(1).replace(".", ",")} p.p.`;

/** Nome do período coberto por um conjunto de pontos. */
function nomePeriodo(serie: SerieKey, pontos: { chave: string }[]) {
  if (!pontos.length) return "sem dados";
  if (serie === "semanal") {
    return pontos.length === 1
      ? `semana de ${rotuloSemana(pontos[0].chave)}`
      : `${rotuloSemana(pontos[0].chave)} – ${rotuloSemana(pontos[pontos.length - 1].chave)}`;
  }
  const a = rotuloMes(pontos[0].chave);
  const b = rotuloMes(pontos[pontos.length - 1].chave);
  return a === b ? a : `${a} – ${b}`;
}

/**
 * Quantas expedições credenciadas houve entre duas datas, somando os dias.
 * `ultimoDia` é a data mais recente com dado do ProntuAI: nada além dela entra,
 * para que numerador e denominador cubram exatamente a mesma janela.
 */
function expedicoesEntre(
  porDia: Record<string, number>,
  ini: Date,
  fim: Date,
  ultimoDia: Date | null,
) {
  let total = 0;
  const d = new Date(ini.getTime());
  const limite = ultimoDia && fim > ultimoDia ? ultimoDia : fim;
  while (d <= limite) {
    const chave = `${pad(d.getUTCFullYear())}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
    total += porDia[chave] || 0;
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return Math.round(total);
}

/** Soma [antecipado, no dia, atrasado] dos dias entre `ini` e `fim`. */
function prazosEntre(porDia: Record<string, Prazos>, ini: Date, fim: Date): Prazos {
  const total: Prazos = [0, 0, 0];
  const d = new Date(ini.getTime());
  while (d <= fim) {
    const dia = porDia[`${pad(d.getUTCFullYear())}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`];
    if (dia) for (let i = 0; i < 3; i++) total[i] += dia[i] || 0;
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return total;
}

/**
 * Soma os pontos de uma clínica que caem no período. As chaves das séries por
 * clínica são as mesmas da série geral, então o casamento é exato.
 */
function acumular(clinica: ClinicaDados, pontos: PontoSerie[], serieKey: SerieKey) {
  const serie = clinica.series?.[serieKey] || {};
  return pontos.reduce(
    (acc, p) => {
      const x = serie[p.chave];
      if (x) {
        acc.docs += x.docs;
        acc.revisados += x.revisados;
        acc.validados += x.validados;
      }
      return acc;
    },
    { docs: 0, revisados: 0, validados: 0 },
  );
}

// ── shape da visão ───────────────────────────────────────────────────────────
export interface Kpi {
  label: string;
  value: string;
  sub: string;
  tip: string;
  delta: string;
  deltaColor: string;
  /** Só o card de Acurácia abre o modal de cálculo. */
  temAjuda?: boolean;
}

export interface BarraDocs {
  month: string;
  value: number;
  h: number;
  tip: string;
}

export interface BarraPercentual {
  month: string;
  label: string;
  h: number;
  tip: string;
}

export interface BarraExpedicao {
  month: string;
  total: string;
  hAnt: number;
  hDia: number;
  hAtr: number;
  tip: string;
}

/** Um dos dois gráficos de prazo — clínica ou técnico de credenciados. */
export interface GraficoPrazo {
  barras: BarraExpedicao[];
  /** "93% antecipados ou no dia", na janela do gráfico. */
  resumo: string;
}

export interface LinhaRanking {
  name: string;
  docs: number;
  pct: number;
  color: string;
  delta: string;
  deltaColor: string;
  tip: string;
}

export interface LinhaAdocao {
  name: string;
  users: number;
  docs: number;
  reviewed: number;
  exped: number;
  pct: number;
  pctLabel: string;
  statusColor: string;
  tip: string;
}

/**
 * Uma linha da tabela de adesão (1.3). Mede coisa diferente de `LinhaAdocao`:
 * "Adoção por clínica" olha documentos DENTRO do ProntuAI; aqui o denominador é
 * o realizado do BRNET, e a pergunta é quanto do que a clínica fez passou pela
 * plataforma. Futuro (previstos) e histórico (realizados) convivem na mesma
 * linha mas nunca se dividem um pelo outro.
 */
export interface LinhaAdesao {
  clinica: string;
  local: string;
  uf: string | null;
  /** Previstos na janela para frente. */
  previstos: number;
  /** Realizados no filtro de período da tela. */
  realizados: number;
  realizadosProntuai: number;
  /** null quando não houve realizados no filtro — nunca 0. */
  adesao: number | null;
  adesaoLabel: string;
  adesaoColor: string;
  proxima: string;
  /** ISO da próxima previsão, "" quando não há. Usado só para ordenar. */
  proximaISO: string;
  tip: string;
}

/** Uma linha da abertura por UF da comparação dentro × fora (2.1). */
export interface LinhaUf {
  uf: string;
  dentro: number;
  fora: number;
  total: number;
  /** Fatia desta UF no total previsto do país, em %. */
  pctTotal: number;
  /** Quanto dos previstos da própria UF está dentro do ProntuAI, em %. */
  pctDentro: number;
  tip: string;
}

/**
 * Comparação dentro × fora (2.1). Só previstos — nada de realizado entra aqui.
 * `cobertura` é a única ponte permitida: base da 1.4 ÷ total de previstos.
 */
export interface ComparacaoPrevistos {
  janela: string;
  dentro: number;
  fora: number;
  total: number;
  pctDentro: number;
  pctFora: number;
  dentroLabel: string;
  foraLabel: string;
  totalLabel: string;
  /** base (1.4) ÷ total de previstos. null quando não há base medível. */
  cobertura: number | null;
  coberturaLabel: string;
  porUf: LinhaUf[];
}

/**
 * Uma linha de oportunidade (2.4): quanto dos previstos de uma clínica
 * habilitada ainda não deve passar pelo ProntuAI.
 */
export interface LinhaOportunidade {
  clinica: string;
  local: string;
  previstos: number;
  adesao: number | null;
  adesaoLabel: string;
  /**
   * previstos × (1 − adesão), **sem arredondar**. Adesão nula conta como 0 —
   * ver `oportunidades`. O valor exato é o que faz a soma fechar com
   * "previstos das habilitadas − base"; arredondar linha a linha e só depois
   * somar erra por alguns pedidos, e o critério de aceite é uma igualdade.
   */
  oportunidade: number;
  oportunidadeLabel: string;
  /** Largura da barra, em % da maior oportunidade. */
  pct: number;
  /** Sem realizados no período: a oportunidade é um teto, não uma medida. */
  semMedida: boolean;
  tip: string;
}

/**
 * Projeção (1.4): quanto dos previstos das habilitadas deve passar pelo
 * ProntuAI. `base` é a soma linha a linha de previstos × adesão da tabela 1.3.
 */
export interface CardProjecao {
  janela: string;
  somaPrevistos: number;
  somaPrevistosLabel: string;
  base: number;
  baseLabel: string;
  /** base ÷ previstos das linhas com adesão medível. null se não houver nenhuma. */
  adesaoPonderada: number | null;
  adesaoPonderadaLabel: string;
  previstosSemAdesaoLabel: string;
  /**
   * Premissa em aberto no backlog: clínica com adesão nula fica FORA da base e
   * do denominador da média. Estes são os previstos que ela carrega, mostrados
   * à parte para a premissa ficar visível em vez de embutida no número.
   */
  previstosSemAdesao: number;
  clinicasSemAdesao: number;
}

/** Uma das duas parcelas do card de previstos. */
export interface ParcelaPrevistos {
  rotulo: string;
  valor: number;
  label: string;
  /** Largura da fatia na barra empilhada, em % do total. */
  pct: number;
  cor: string;
  sub: string;
  tip: string;
}

/**
 * Card "Pedidos previstos": pedidos do BRNET ainda NÃO liberados com previsão
 * dentro da janela, separados pelo mesmo corte das duas tabelas. null quando o
 * BRNET não pôde ser consultado.
 */
export interface CardPrevistos {
  /** "de hoje a 29/10 · 30 dias". */
  janela: string;
  total: number;
  totalLabel: string;
  partes: ParcelaPrevistos[];
}

/** Uma linha do painel "Datas das previsões". */
export interface DataPrevista {
  label: string;
  pedidos: string;
}

export interface LinhaPrevista {
  /** Rótulo completo do BRNET, mostrado ao expandir. */
  credenciado: string;
  name: string;
  local: string;
  uf: string | null;
  pedidos: number;
  /** Primeira data prevista; a quebra por dia fica no painel expansível. */
  proxima: string;
  /** ISO da próxima previsão, para ordenar por data e não por texto. */
  proximaISO: string;
  datas: DataPrevista[];
  /** Vencidos e documentos, no rodapé do painel. */
  resumo: string;
  /** Fatia desta clínica nos previstos fora do ProntuAI, em %. */
  participacao: number;
  participacaoLabel: string;
  /**
   * Quanto a base da projeção cresceria se esta clínica entrasse:
   * previstos × adesão esperada ÷ base. null quando não há base para comparar.
   */
  impacto: number | null;
  impactoLabel: string;
}

export interface LinhaMatriz {
  name: string;
  vol: string;
  acc: string;
  classificacao: string;
  classificacaoColor: string;
  peso: number;
  cor: string;
}

export interface FatorPenteFino {
  name: string;
  count: number;
  color: string;
  pct: number;
  tip: string;
}

export interface VisaoDashboard {
  rangeLabel: string;
  compareLabel: string;
  chipPeriodo: string;
  graficoLegenda: string;

  kpiPrimary: Kpi[];
  docsSeries: BarraDocs[];
  coberturaSeries: BarraPercentual[];
  prazoClinica: GraficoPrazo;
  prazoTecnico: GraficoPrazo;
  ranking: LinhaRanking[];
  totalClinicas: number;
  adocao: LinhaAdocao[];
  /** null quando o BRNET não pôde ser consultado. */
  semProntuai: LinhaPrevista[] | null;
  pedidosSemProntuai: number;
  /** Os três dependem do BRNET e vêm null juntos. */
  previstos: CardPrevistos | null;
  adesao: LinhaAdesao[] | null;
  projecao: CardProjecao | null;
  comparacao: ComparacaoPrevistos | null;
  oportunidades: LinhaOportunidade[] | null;
  /**
   * Insumos do simulador (2.3). O simulador não recalcula nada do painel: ele
   * parte destes números e aplica a adesão escolhida sobre a seleção.
   */
  simulador: { base: number; totalPrevistos: number; adesaoHistorica: number | null } | null;
  /** Rótulo do filtro de período, para a tabela 1.3 dizer de onde vem cada coluna. */
  periodoLabel: string;

  kpisAcuracia: Kpi[];
  acuraciaSeries: BarraPercentual[];
  fatorPrincipal: string;
  penteFino: FatorPenteFino[];
  notaSemJustificativa: string;
  porTipo: LinhaMatriz[];
}

export interface OpcoesVisao {
  dados: DadosDashboard;
  filtro: FiltroPeriodo;
  comparar: boolean;
  verTodasClinicas: boolean;
}

/** Escala do gráfico de acurácia: a métrica vive na faixa alta e 0–100 achataria. */
const PISO_ACC = 70;

const DIAS_ABBR = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

export function calcularVisao({ dados, filtro, comparar, verTodasClinicas }: OpcoesVisao): VisaoDashboard {
  const cfg = PERIODOS[filtro] ?? PERIODOS.Mensal;

  // ---- período dos indicadores ---------------------------------------------
  const serieP = dados.series?.[cfg.periodo.serie] ?? [];
  const np = cfg.periodo.n;
  const atual = np ? serieP.slice(-np) : serieP.slice();
  const anterior = np
    ? serieP.slice(Math.max(0, serieP.length - 2 * np), Math.max(0, serieP.length - np))
    : [];
  // Só compara blocos de mesmo tamanho — período anterior parcial distorceria.
  const comparavel = np > 0 && atual.length === np && anterior.length === np;

  // ---- série de contexto dos gráficos --------------------------------------
  const serieG = dados.series?.[cfg.grafico.serie] ?? [];
  const grafico = cfg.grafico.n ? serieG.slice(-cfg.grafico.n) : serieG.slice();
  const rotuloG = cfg.grafico.serie === "semanal" ? rotuloSemana : rotuloMes;

  const soma = <T,>(arr: T[], campo: keyof T) =>
    arr.reduce((acc, p) => acc + (Number(p[campo]) || 0), 0);

  const delta = (v: string, dir: "up" | "down") => {
    const good = dir !== "down";
    if (!v) return { delta: "", deltaColor: MUTED };
    if (!comparar) return { delta: "—", deltaColor: MUTED };
    const neg = v.startsWith("-");
    return {
      delta: `${neg ? "▾" : "▴"} ${v.replace("-", "")}`,
      deltaColor: neg === !good ? POS : NEG,
    };
  };

  const kpi = (label: string, value: string, d: string, dir: "up" | "down", sub?: string): Kpi => ({
    label,
    value,
    sub: sub || "",
    tip: TIPS_KPI[label] || "",
    ...delta(d, dir),
  });

  const kpiAcc = (label: string, value: string, d: string, dir: "up" | "down", sub?: string): Kpi => ({
    ...kpi(label, value, d, dir, sub),
    tip: TIPS_ACC[label] || "",
    temAjuda: label === "Acurácia",
  });

  const variacao = (campo: keyof PontoSerie) => {
    if (!comparavel) return "";
    const a = soma(atual, campo);
    const b = soma(anterior, campo);
    if (!b) return a ? "novo" : "";
    return `${a >= b ? "+" : "-"}${Math.abs(((a - b) / b) * 100).toFixed(0)}%`;
  };

  const enviados = soma(atual, "docs");
  const revisados = soma(atual, "revisados");
  const liberados = soma(atual, "validados");

  const bar = (v: number, max: number, h: number) => (v <= 0 ? 0 : Math.max(3, Math.round((v / max) * h)));
  const maxDocs = Math.max(1, ...grafico.map((p) => p.docs));

  /** Primeiro e último dia de um ponto do gráfico (semana ou mês). */
  const faixaDoPonto = (chave: string) => {
    const a = partes(chave);
    const ini = new Date(Date.UTC(a.y, a.m - 1, a.d));
    const fim =
      cfg.grafico.serie === "semanal"
        ? new Date(Date.UTC(a.y, a.m - 1, a.d + 6))
        : new Date(Date.UTC(a.y, a.m, 0));
    return { ini, fim };
  };

  const graficoPrazo = (porDia: Record<string, Prazos>, noun: [string, string]): GraficoPrazo => {
    const [sing, plur] = noun;
    const pontos = grafico.map((p) => {
      const { ini, fim } = faixaDoPonto(p.chave);
      return { chave: p.chave, v: prazosEntre(porDia, ini, fim) };
    });
    const maxP = Math.max(1, ...pontos.map(({ v }) => v[0] + v[1] + v[2]));
    const soma: Prazos = [0, 0, 0];
    pontos.forEach(({ v }) => v.forEach((n, i) => (soma[i] += n)));
    const tot = soma[0] + soma[1] + soma[2];
    const q = (n: number) => `${fmt(n)} ${n === 1 ? sing : plur}`;
    return {
      resumo: tot ? `${num(pct(soma[0] + soma[1], tot))} antecipados ou no dia · ${q(tot)}` : "",
      barras: pontos.map(({ chave, v: [ant, dia, atr] }) => {
        const t = ant + dia + atr;
        return {
          month: rotuloG(chave),
          total: t ? fmt(t) : "—",
          hAnt: bar(ant, maxP, 190),
          hDia: bar(dia, maxP, 190),
          hAtr: bar(atr, maxP, 190),
          tip: t
            ? `${rotuloG(chave)} — ${fmt(ant)} antecipados, ${fmt(dia)} no dia, ${fmt(atr)} atrasados (${num(pct(atr, t))} atrasados)`
            : `${rotuloG(chave)} — sem ${plur} com previsão`,
        };
      }),
    };
  };

  // ---- cobertura: pedidos do BRNET com documento liberado no ProntuAI --------
  // Numerador e denominador contam pedidos, pelo dia de LIBERAÇÃO — realizado
  // é pedido expedido, não atendido (definição da 1.2).
  const porDia = dados.expedicoes_dia || {};
  const viaPorDia = dados.expedicoes_prontuai_dia || {};
  const dataDe = (iso?: string) => {
    if (!iso) return null;
    const q = partes(iso);
    return new Date(Date.UTC(q.y, q.m - 1, q.d));
  };
  const primeiroDoc = dataDe(dados.periodo?.doc_mais_antigo);
  const ultimoDoc = dataDe(dados.periodo?.doc_mais_recente);
  // A ligação documento↔pedido só existe a partir de `expedicoes_desde` (jun/26).
  // Sem ela não há cobertura medível: o denominador vira 0 e o KPI cai no absoluto.
  const desde = dataDe(dados.expedicoes_desde ?? undefined);
  const inicioCobertura = desde && (!primeiroDoc || desde > primeiroDoc) ? desde : primeiroDoc;
  const expedicoesEmpresa = (ini: Date, fim: Date) =>
    desde ? expedicoesEntre(porDia, ini, fim, ultimoDoc) : 0;

  /** Intervalo de datas coberto por um conjunto de pontos da série. */
  const intervalo = (pontos: PontoSerie[]) => {
    if (!pontos.length) return null;
    const a = partes(pontos[0].chave);
    const z = partes(pontos[pontos.length - 1].chave);
    let ini = new Date(Date.UTC(a.y, a.m - 1, a.d));
    // não conta expedição de antes da ligação por pedido
    if (inicioCobertura && ini < inicioCobertura) ini = inicioCobertura;
    const fim =
      cfg.periodo.serie === "semanal"
        ? new Date(Date.UTC(z.y, z.m - 1, z.d + 6))
        : new Date(Date.UTC(z.y, z.m, 0)); // último dia do mês
    return { ini, fim };
  };

  const faixaAtual = intervalo(atual);
  const faixaAnterior = intervalo(anterior);
  const expEmpresa = faixaAtual ? expedicoesEmpresa(faixaAtual.ini, faixaAtual.fim) : 0;
  const expEmpresaAnt = faixaAnterior ? expedicoesEmpresa(faixaAnterior.ini, faixaAnterior.fim) : 0;
  const viaProntuai = faixaAtual ? expedicoesEntre(viaPorDia, faixaAtual.ini, faixaAtual.fim, ultimoDoc) : 0;
  const viaProntuaiAnt = faixaAnterior
    ? expedicoesEntre(viaPorDia, faixaAnterior.ini, faixaAnterior.fim, ultimoDoc)
    : 0;
  const cobertura = pct(viaProntuai, expEmpresa);
  // Período que começa antes da ligação é medido só a partir dela: o rótulo diz.
  const cortadoNaLigacao = !!dados.expedicoes_desde && !!atual.length && atual[0].chave < dados.expedicoes_desde;

  const kpiExpedicoes = (): Kpi => {
    if (!expEmpresa) {
      return kpi(
        "Expedições via ProntuAI",
        fmt(liberados),
        variacao("validados"),
        "up",
        dados.expedicoes_desde
          ? `liberados na plataforma · cobertura medida a partir de ${rotuloMes(dados.expedicoes_desde)}`
          : "liberados na plataforma · total da empresa não informado no período",
      );
    }
    const antPct = comparavel && expEmpresaAnt ? pct(viaProntuaiAnt, expEmpresaAnt) : null;
    return kpi(
      "Expedições via ProntuAI",
      num(cobertura),
      antPct === null ? "" : pp(cobertura, antPct),
      "up",
      `${fmt(viaProntuai)} de ${fmt(expEmpresa)} expedições${cortadoNaLigacao ? ` desde ${rotuloMes(dados.expedicoes_desde!)}` : ""} · meta 100%`,
    );
  };

  // ---- credenciados sem ProntuAI: datas previstas ---------------------------
  // "hoje" vem do back-end (quando a consulta rodou), não do relógio do browser:
  // o painel é recalculado uma vez por dia e o fuso do servidor é quem manda.
  const hojeISO = (dados.gerado_em ?? "").slice(0, 10);
  const amanhaISO = (() => {
    if (!hojeISO) return "";
    const q = partes(hojeISO);
    const d = new Date(Date.UTC(q.y, q.m - 1, q.d + 1));
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  })();
  // Janela para frente do card de previstos: de hoje até hoje + (dias - 1), com
  // o dia de hoje incluído. Sem `gerado_em` não há "hoje" confiável — o relógio
  // do browser não serve, porque o painel é calculado uma vez por dia no fuso do
  // servidor —, então o recorte é desligado em vez de sair errado.
  const diasJanela = JANELA_PREVISTOS[filtro] ?? JANELA_PREVISTOS.Mensal;
  const fimJanelaISO = (() => {
    if (!hojeISO) return "";
    const q = partes(hojeISO);
    const d = new Date(Date.UTC(q.y, q.m - 1, q.d + diasJanela - 1));
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  })();
  const temJanela = !!hojeISO;

  const dataCurta = (iso: string) => {
    const q = partes(iso);
    return `${pad(q.d)}/${pad(q.m)}`;
  };

  // No painel expandido o dia da semana importa: é o que responde "isso é pra
  // semana que vem?" sem a pessoa ter que consultar o calendário.
  const rotuloPrevisao = (iso: string) => {
    const q = partes(iso);
    const data = `${pad(q.d)}/${pad(q.m)}`;
    if (iso === hojeISO) return `hoje, ${data}`;
    if (iso === amanhaISO) return `amanhã, ${data}`;
    return `${DIAS_ABBR[new Date(Date.UTC(q.y, q.m - 1, q.d)).getUTCDay()]}, ${data}`;
  };

  // ---- clínicas, no mesmo período dos indicadores --------------------------
  const serieKey = cfg.periodo.serie;
  const todas = (dados.clinicas || [])
    .map((c) => {
      const a = acumular(c, atual, serieKey);
      const b = acumular(c, anterior, serieKey);
      return { nome: c.nome, usuarios: c.usuarios, ...a, docsAnterior: b.docs };
    })
    .filter((c) => c.docs > 0)
    .sort((x, y) => y.docs - x.docs);

  const clinicas = verTodasClinicas ? todas : todas.slice(0, 6);
  const maxClin = Math.max(1, ...clinicas.map((c) => c.docs));

  // ---- previstos, adesão e projeção ----------------------------------------
  const comProntuai = dados.clinicas_com_prontuai ?? [];
  const semProntuaiBruto = dados.clinicas_sem_prontuai ?? [];
  // Os dois vêm null juntos do back-end. Checar os dois mesmo assim: um back-end
  // anterior a `clinicas_com_prontuai` devolveria só a lista antiga, e aí a
  // tabela de adesão sairia vazia com a projeção dizendo base zero — pior que
  // não mostrar nada.
  const temBrnet = dados.clinicas_sem_prontuai !== null && dados.clinicas_com_prontuai !== null;

  /** Previsões de um credenciado que caem na janela para frente. */
  // Sem `gerado_em` não há "hoje" confiável, e sem ele o teto de um mês que a
  // issue exige não pode ser aplicado. Antes esta função deixava passar TODA
  // previsão nesse caso — o oposto do critério. Agora não passa nenhuma: não
  // mostrar previsto é seguro, mostrar previsto sem recorte não é.
  const diasNaJanela = (c: CredenciadoPrevisto) =>
    temJanela ? c.previsoes.filter((x) => x.data >= hojeISO && x.data <= fimJanelaISO) : [];
  const somaDias = (dias: PrevisaoDia[]) => dias.reduce((a, x) => a + x.pedidos, 0);

  // Realizados entram pela MESMA janela retroativa dos KPIs, com o mesmo corte
  // em `expedicoes_desde`: a adesão por clínica é o recorte por clínica do KPI
  // "Expedições via ProntuAI", e janelas diferentes fariam os dois números da
  // tela discordarem sem motivo.
  const realizadosDe = (porDia: Record<string, number> | undefined) =>
    faixaAtual && porDia ? expedicoesEntre(porDia, faixaAtual.ini, faixaAtual.fim, ultimoDoc) : 0;

  // ---- 1.2 + 1.3: adesão por clínica com cadastro habilitado ---------------
  const linhasAdesao: LinhaAdesao[] = comProntuai.map((c) => {
    const clinica = c.clinica ?? c.nome;
    const dias = diasNaJanela(c);
    const previstos = somaDias(dias);
    const realizados = realizadosDe(c.realizados_dia);
    const realizadosProntuai = realizadosDe(c.realizados_prontuai_dia);
    // Sem realizados no filtro a adesão é NULA, nunca zero: zero afirmaria que a
    // clínica não usou a plataforma, e o que houve foi ausência de medida.
    const adesao = realizados ? (realizadosProntuai / realizados) * 100 : null;
    return {
      clinica,
      local: c.cidade && c.uf ? `${c.cidade}/${c.uf}` : "—",
      uf: c.uf,
      previstos,
      realizados,
      realizadosProntuai,
      adesao,
      adesaoLabel: adesao === null ? "—" : num(adesao),
      adesaoColor: adesao === null ? MUTED : adesao >= 90 ? POS : adesao >= 75 ? CORES.alerta : NEG,
      proxima: dias.length ? dataCurta(dias[0].data) : "—",
      proximaISO: dias.length ? dias[0].data : "",
      tip:
        adesao === null
          ? `${clinica} — sem realizados no período selecionado, adesão não medível`
          : `${clinica} — ${fmt(realizadosProntuai)} de ${fmt(realizados)} realizados passaram pelo ProntuAI`,
    };
  });

  // ---- 1.4: projeção sobre os previstos das habilitadas --------------------
  // Premissa assumida (pendência aberta no backlog): adesão nula fica FORA da
  // base e do denominador da média ponderada. Incluí-la como zero puxaria a
  // média para baixo afirmando algo que não foi medido; deixá-la no denominador
  // sem contribuir para a base faria o mesmo. Os previstos que ela carrega
  // aparecem à parte, para a premissa ficar visível na tela.
  const comAdesao = linhasAdesao.filter((l) => l.adesao !== null);
  const somaPrevistos = linhasAdesao.reduce((a, l) => a + l.previstos, 0);
  const base = comAdesao.reduce((a, l) => a + (l.previstos * (l.adesao as number)) / 100, 0);
  const previstosComAdesao = comAdesao.reduce((a, l) => a + l.previstos, 0);
  const adesaoPonderada = previstosComAdesao ? (base / previstosComAdesao) * 100 : null;

  // ---- 2.2: prioridade de inclusão ----------------------------------------
  const linhasSemProntuai = semProntuaiBruto
    .map((c) => ({ c, dias: diasNaJanela(c) }))
    // Credenciado sem previsão dentro da janela sai da tabela: a lista é de
    // prioridade de inclusão, e quem não tem nada previsto não é prioridade.
    .filter(({ dias }) => somaDias(dias) > 0);

  // ---- 2.4: oportunidade nas clínicas já habilitadas ----------------------
  // Pendência do backlog resolvida pelo próprio critério de aceite: "soma das
  // oportunidades = previstos das habilitadas − base". Como a base (1.4) deixa
  // a clínica sem adesão de fora, a única forma de a identidade fechar é a
  // oportunidade dela ser os previstos INTEIROS, ou seja, adesão tratada como 0.
  // Excluí-la da lista faria a soma não bater. `semMedida` marca esses casos na
  // tela: ali a oportunidade é um teto, não uma medida.
  const linhasOportunidade: LinhaOportunidade[] = linhasAdesao
    .map((l) => ({ l, oportunidade: l.previstos * (1 - (l.adesao ?? 0) / 100) }))
    .filter(({ oportunidade }) => oportunidade > 0)
    .sort((a, b) => b.oportunidade - a.oportunidade)
    .map(({ l, oportunidade }, _i, todas) => ({
      clinica: l.clinica,
      local: l.local,
      previstos: l.previstos,
      adesao: l.adesao,
      adesaoLabel: l.adesaoLabel,
      oportunidade,
      oportunidadeLabel: fmt(Math.round(oportunidade)),
      pct: Math.round(pct(oportunidade, todas[0].oportunidade)),
      semMedida: l.adesao === null,
      tip:
        l.adesao === null
          ? `${l.clinica} — sem realizados no período: os ${fmt(l.previstos)} previstos contam inteiros, é um teto`
          : `${l.clinica} — ${fmt(l.previstos)} previstos a ${l.adesaoLabel} de adesão deixam ${fmt(Math.round(oportunidade))} pedidos fora`,
    }));

  const previstosHabilitados = somaPrevistos;
  const previstosFora = linhasSemProntuai.reduce((a, { dias }) => a + somaDias(dias), 0);
  // Premissa assumida (pendência aberta): a adesão esperada de quem ainda não
  // usa é a média ponderada das que já usam. É o melhor estimador disponível
  // sem uma meta definida pelo time — e fica num ponto só para ser trocado.
  const adesaoEsperada = adesaoPonderada;

  // ---- 2.1: comparação dentro × fora, aberta por UF -----------------------
  // Só previstos. A cobertura prevista é a única ponte com o realizado, e ela
  // vem da base da 1.4 — que já é previsto × adesão, não uma soma de grandezas.
  const ufDia = dados.previstos_uf_dia;
  // Mesma regra de `diasNaJanela`: sem data de referência não há janela, e sem
  // janela não se conta previsto.
  const somaUf = (porDia: Record<string, number>) =>
    temJanela
      ? Object.entries(porDia).reduce(
          (a, [data, n]) => a + (data >= hojeISO && data <= fimJanelaISO ? n : 0),
          0,
        )
      : 0;
  const linhasUf: LinhaUf[] = (() => {
    if (!ufDia) return [];
    const ufs = [...new Set([...Object.keys(ufDia.dentro), ...Object.keys(ufDia.fora)])];
    const totalGeral = previstosHabilitados + previstosFora;
    return ufs
      .map((uf) => {
        const dentro = somaUf(ufDia.dentro[uf] ?? {});
        const fora = somaUf(ufDia.fora[uf] ?? {});
        const total = dentro + fora;
        return {
          uf,
          dentro,
          fora,
          total,
          pctTotal: pct(total, totalGeral),
          pctDentro: pct(dentro, total),
          tip: `${uf} — ${fmt(dentro)} previstos em clínicas habilitadas, ${fmt(fora)} fora (${num(pct(dentro, total))} dentro)`,
        };
      })
      .filter((l) => l.total > 0)
      .sort((a, b) => b.total - a.total);
  })();

  // ---- acurácia: mesma janela de período e de gráfico da utilização --------
  const accP = dados.acuracia?.[cfg.periodo.serie] ?? [];
  const accAtual = np ? accP.slice(-np) : accP.slice();
  const accAnterior = np
    ? accP.slice(Math.max(0, accP.length - 2 * np), Math.max(0, accP.length - np))
    : [];
  const accG = dados.acuracia?.[cfg.grafico.serie] ?? [];
  const accGrafico = cfg.grafico.n ? accG.slice(-cfg.grafico.n) : accG.slice();

  // acerto = concordância direta + divergência resolvida por motivo externo
  const acertosDe = (arr: PontoAcuracia[]) =>
    soma(arr, "ok_aprovou") +
    soma(arr, "ok_rejeitou") +
    soma(arr, "div_aprovou_jeitinho") +
    soma(arr, "div_rejeitou_jeitinho");
  const baseDe = (arr: PontoAcuracia[]) =>
    soma(arr, "ok_aprovou") + soma(arr, "ok_rejeitou") + soma(arr, "div_aprovou") + soma(arr, "div_rejeitou");

  const acertos = acertosDe(accAtual);
  const baseAcc = baseDe(accAtual);
  const acuracia = pct(acertos, baseAcc);
  const acuraciaAnt = baseDe(accAnterior) ? pct(acertosDe(accAnterior), baseDe(accAnterior)) : null;

  const concordanciaDireta = soma(accAtual, "ok_aprovou") + soma(accAtual, "ok_rejeitou");
  const jeitinhoTotal = soma(accAtual, "div_aprovou_jeitinho") + soma(accAtual, "div_rejeitou_jeitinho");
  // Contas por janela: o valor do card e o delta dele precisam medir a MESMA
  // grandeza. Antes o delta comparava só uma parcela (div_aprovou bruto,
  // falha_aprovou) e divergia do número exibido.
  const riscoRealDe = (arr: PontoAcuracia[]) =>
    soma(arr, "div_aprovou") - soma(arr, "div_aprovou_jeitinho");
  const falhasDe = (arr: PontoAcuracia[]) =>
    soma(arr, "falha_rejeitou") + soma(arr, "falha_aprovou");
  const riscoReal = riscoRealDe(accAtual);
  const divRejeitou = soma(accAtual, "div_rejeitou") - soma(accAtual, "div_rejeitou_jeitinho");
  const falhasTecnicas = falhasDe(accAtual);

  const varAcc = (conta: (arr: PontoAcuracia[]) => number) => {
    if (!comparavel) return "";
    const a = conta(accAtual);
    const b = conta(accAnterior);
    if (!b) return a ? "novo" : "";
    return `${a >= b ? "+" : "-"}${Math.abs(((a - b) / b) * 100).toFixed(0)}%`;
  };

  const alturaAcc = (v: number) => Math.max(3, Math.round(((v - PISO_ACC) / (100 - PISO_ACC)) * 200));

  const situacoes: [string, number, boolean, string][] = [
    ["IA aprovou → humano aprovou", soma(accAtual, "ok_aprovou"), true, CORES.positivo],
    ["IA rejeitou → humano rejeitou", soma(accAtual, "ok_rejeitou"), true, CORES.petroleo],
    ["Divergência resolvida por motivo externo", jeitinhoTotal, true, CORES.agua],
    ["IA rejeitou → humano aprovou", divRejeitou, false, CORES.alerta],
    ["IA aprovou → humano rejeitou", riscoReal, false, CORES.negativo],
  ];

  // ---- por que a acurácia não está maior -----------------------------------
  const fatores: [string, number, string][] = (
    [
      ["Exame faltante que a IA não detectou", soma(accAtual, "mot_exame_nao_detectado"), CORES.negativo],
      ["IA não reconheceu exame que estava no PDF", soma(accAtual, "mot_matching_ia"), CORES.alerta],
      ["Regra formal que a IA ainda não verifica", soma(accAtual, "mot_regra_formal"), CORES.agua],
      ["Revisor não registrou o motivo", soma(accAtual, "mot_sem_justificativa"), "#9AA9B3"],
      ["Outros motivos", soma(accAtual, "mot_outro"), "#BFC3C6"],
    ] as [string, number, string][]
  )
    .filter((f) => f[1] > 0)
    .sort((a, b) => b[1] - a[1]);

  const totalFatores = fatores.reduce((a, f) => a + f[1], 0);
  const maiorFator = fatores.length ? fatores[0] : null;
  const semJustDiv = soma(accAtual, "sem_just_divergencia");
  // A classificação por motivo só existe se a extração trouxe os campos mot_*.
  const temMotivos = accAtual.some((p) => p.mot_exame_nao_detectado !== undefined);

  return {
    rangeLabel: nomePeriodo(cfg.periodo.serie, atual),
    compareLabel: comparar
      ? comparavel
        ? nomePeriodo(cfg.periodo.serie, anterior)
        : np === 0
          ? "toda a base"
          : "sem período anterior completo"
      : "nenhum período",

    chipPeriodo:
      cfg.grafico.serie === "semanal"
        ? `Últimas ${grafico.length} semanas`
        : cfg.grafico.n
          ? `Últimos ${grafico.length} meses`
          : "Toda a base",

    // Gráficos usam a série de contexto (mais pontos que o período dos KPIs).
    graficoLegenda:
      cfg.grafico.serie === "semanal"
        ? `Últimas ${grafico.length} semanas`
        : cfg.grafico.n
          ? `Últimos ${grafico.length} meses`
          : "Toda a base, por mês",

    kpiPrimary: [
      kpi("Documentos enviados", fmt(enviados), variacao("docs"), "up", nomePeriodo(cfg.periodo.serie, atual)),
      kpi(
        "Documentos revisados",
        fmt(revisados),
        variacao("revisados"),
        "up",
        `${num(pct(revisados, enviados))} do que foi enviado`,
      ),
      kpiExpedicoes(),
    ],

    docsSeries: grafico.map((p) => ({
      month: rotuloG(p.chave),
      value: p.docs,
      h: bar(p.docs, maxDocs, 236),
      tip: p.docs
        ? `${rotuloG(p.chave)} — ${fmt(p.docs)} enviados, ${fmt(p.validados)} liberados, ${fmt(p.rejeitados)} com pendência`
        : `${rotuloG(p.chave)} — sem documentos`,
    })),

    // Cobertura do ProntuAI sobre as expedições da empresa, ponto a ponto.
    coberturaSeries: (() => {
      const pontos = grafico.map((p) => {
        const a = partes(p.chave);
        let ini = new Date(Date.UTC(a.y, a.m - 1, a.d));
        if (inicioCobertura && ini < inicioCobertura) ini = inicioCobertura;
        const fim =
          cfg.grafico.serie === "semanal"
            ? new Date(Date.UTC(a.y, a.m - 1, a.d + 6))
            : new Date(Date.UTC(a.y, a.m, 0));
        const emp = expedicoesEmpresa(ini, fim);
        const lib = expedicoesEntre(viaPorDia, ini, fim, ultimoDoc);
        const v = emp ? (lib / emp) * 100 : 0;
        return { mes: rotuloG(p.chave), v, emp, lib };
      });
      const maxV = Math.max(10, ...pontos.map((p) => p.v));
      return pontos.map((p) => ({
        month: p.mes,
        label: p.emp ? num(p.v) : "—",
        h: p.emp ? Math.max(3, Math.round((p.v / maxV) * 190)) : 0,
        tip: p.emp
          ? `${p.mes} — ${fmt(p.lib)} de ${fmt(p.emp)} expedições (${num(p.v)})`
          : `${p.mes} — sem expedições registradas`,
      }));
    })(),

    prazoClinica: graficoPrazo(dados.prazo_clinica_dia || {}, ["envio", "envios"]),
    prazoTecnico: graficoPrazo(dados.prazo_tecnico_dia || {}, ["liberação", "liberações"]),

    ranking: clinicas.map((c, i) => {
      const v = !comparavel
        ? ""
        : c.docsAnterior
          ? `${c.docs >= c.docsAnterior ? "+" : "-"}${Math.abs(((c.docs - c.docsAnterior) / c.docsAnterior) * 100).toFixed(0)}%`
          : c.docs
            ? "novo"
            : "";
      const comp = !comparavel ? "" : ` (antes: ${fmt(c.docsAnterior)})`;
      return {
        name: c.nome,
        docs: c.docs,
        pct: Math.round(pct(c.docs, maxClin)),
        color: CORES_RANK[i] || CORES.agua,
        delta: comparar ? v : "",
        deltaColor: v.startsWith("-") ? NEG : POS,
        tip: `${c.nome} — ${fmt(c.docs)} enviados${comp}, ${fmt(c.revisados)} revisados, ${fmt(c.validados)} liberados`,
      };
    }),

    totalClinicas: todas.length,

    adocao: clinicas.map((c) => {
      const p = Math.round(pct(c.validados, c.docs));
      return {
        name: c.nome,
        users: c.usuarios,
        docs: c.docs,
        reviewed: c.revisados,
        exped: c.validados,
        pct: p,
        pctLabel: `${p}%`,
        statusColor: p >= 90 ? POS : p >= 75 ? CORES.alerta : NEG,
        tip: `${c.nome} — ${fmt(c.docs - c.revisados)} aguardando revisão de ${fmt(c.docs)} enviados`,
      };
    }),

    semProntuai: temBrnet
      ? linhasSemProntuai.map(({ c, dias }) => {
          const pedidos = somaDias(dias);
          const docs = c.documentos
            ? `${c.documentos} documento${c.documentos > 1 ? "s" : ""} no ProntuAI`
            : "nenhum documento no ProntuAI";
          const foraDaJanela = c.pedidos_previstos - pedidos;
          // Impacto: quanto a base da projeção (1.4) cresceria se esta clínica
          // entrasse. Proporcional aos previstos, já que a adesão esperada é a
          // mesma para todas — o ranking por impacto e por previstos coincide
          // enquanto essa premissa valer, e deixa de coincidir no dia em que a
          // adesão esperada virar por clínica.
          const impacto =
            adesaoEsperada !== null && base ? (pedidos * (adesaoEsperada / 100) * 100) / base : null;
          return {
            credenciado: c.credenciado,
            name: c.nome,
            local: c.cidade && c.uf ? `${c.cidade}/${c.uf}` : "—",
            uf: c.uf,
            pedidos,
            proxima: dataCurta(dias[0].data),
            proximaISO: dias[0].data,
            datas: dias.map((p) => ({ label: rotuloPrevisao(p.data), pedidos: fmt(p.pedidos) })),
            resumo:
              (c.vencidos ? `${fmt(c.vencidos)} com previsão vencida · ` : "") +
              (foraDaJanela ? `${fmt(foraDaJanela)} previstos depois da janela · ` : "") +
              docs,
            participacao: pct(pedidos, previstosFora),
            participacaoLabel: num(pct(pedidos, previstosFora)),
            impacto,
            impactoLabel: impacto === null ? "—" : `+${num(impacto).replace("%", "")}%`,
          };
        })
      : null,
    pedidosSemProntuai: previstosFora,

    adesao: temBrnet ? linhasAdesao : null,

    projecao: temBrnet
      ? {
          janela: temJanela
            ? `de hoje a ${dataCurta(fimJanelaISO)} · ${diasJanela} dias`
            : "sem data de referência do back-end — previstos indisponíveis",
          somaPrevistos,
          somaPrevistosLabel: fmt(somaPrevistos),
          base,
          // A base é uma contagem de pedidos: arredondar aqui evita "37,4 pedidos"
          // na tela sem mexer no número que o critério de aceite confere.
          baseLabel: adesaoPonderada === null ? "—" : fmt(Math.round(base)),
          adesaoPonderada,
          adesaoPonderadaLabel: adesaoPonderada === null ? "—" : num(adesaoPonderada),
          previstosSemAdesao: somaPrevistos - previstosComAdesao,
          previstosSemAdesaoLabel: fmt(somaPrevistos - previstosComAdesao),
          clinicasSemAdesao: linhasAdesao.length - comAdesao.length,
        }
      : null,

    periodoLabel: nomePeriodo(cfg.periodo.serie, atual),

    comparacao: temBrnet
      ? (() => {
          const total = previstosHabilitados + previstosFora;
          return {
            janela: temJanela
              ? `de hoje a ${dataCurta(fimJanelaISO)} · ${diasJanela} dias`
              : "sem data de referência do back-end — previstos indisponíveis",
            dentro: previstosHabilitados,
            fora: previstosFora,
            total,
            pctDentro: pct(previstosHabilitados, total),
            pctFora: pct(previstosFora, total),
            dentroLabel: fmt(previstosHabilitados),
            foraLabel: fmt(previstosFora),
            totalLabel: fmt(total),
            // Cobertura prevista da 2.1 = base da 1.4 ÷ TODOS os previstos,
            // dentro e fora. Não é a adesão ponderada, que divide só pelos
            // previstos das habilitadas com adesão medida.
            cobertura: total && adesaoPonderada !== null ? pct(base, total) : null,
            coberturaLabel:
              total && adesaoPonderada !== null ? num(pct(base, total)) : "—",
            porUf: linhasUf,
          };
        })()
      : null,

    oportunidades: temBrnet ? linhasOportunidade : null,

    simulador: temBrnet
      ? {
          base,
          totalPrevistos: previstosHabilitados + previstosFora,
          adesaoHistorica: adesaoPonderada,
        }
      : null,

    previstos: temBrnet
      ? (() => {
          const total = previstosHabilitados + previstosFora;
          const parte = (rotulo: string, valor: number, cor: string, sub: string, tip: string) => ({
            rotulo,
            valor,
            label: fmt(valor),
            pct: total ? (valor / total) * 100 : 0,
            cor,
            sub: total ? `${sub} · ${num(pct(valor, total))} do previsto` : sub,
            tip,
          });
          return {
            janela: temJanela
              ? `de hoje a ${dataCurta(fimJanelaISO)} · ${diasJanela} dias`
              : "sem data de referência do back-end — previstos indisponíveis",
            total,
            totalLabel: fmt(total),
            partes: [
              parte(
                "Clínicas com cadastro no ProntuAI",
                previstosHabilitados,
                CORES.petroleo,
                "detalhe na tabela de adesão",
                "Pedidos com previsão de liberação na janela, em clínicas com cadastro habilitado no ProntuAI.",
              ),
              parte(
                "Clínicas fora do ProntuAI",
                previstosFora,
                CORES.alerta,
                "detalhe em prioridade de inclusão",
                "Pedidos com previsão de liberação na janela, em credenciados sem cadastro habilitado no ProntuAI. É o volume que ainda chega por fora.",
              ),
            ],
          };
        })()
      : null,

    kpisAcuracia: [
      kpiAcc(
        "Acurácia",
        baseAcc ? num(acuracia) : "—",
        comparavel ? pp(acuracia, acuraciaAnt) : "",
        "up",
        `${fmt(acertos)} de ${fmt(baseAcc)} documentos revisados`,
      ),
      kpiAcc(
        "Concordância direta",
        baseAcc ? num(pct(concordanciaDireta, baseAcc)) : "—",
        comparavel && baseDe(accAnterior)
          ? pp(
              pct(concordanciaDireta, baseAcc),
              pct(soma(accAnterior, "ok_aprovou") + soma(accAnterior, "ok_rejeitou"), baseDe(accAnterior)),
            )
          : "",
        "up",
        `${fmt(concordanciaDireta)} sem necessidade de ressalva`,
      ),
      kpiAcc(
        "Aprovações derrubadas",
        fmt(riscoReal),
        varAcc(riscoRealDe),
        "down",
        "IA liberou e o revisor barrou — é o risco real",
      ),
      kpiAcc(
        "Falhas técnicas",
        fmt(falhasTecnicas),
        varAcc(falhasDe),
        "down",
        "não leu CPF/CNPJ · fora da conta de acurácia",
      ),
    ],

    acuraciaSeries: accGrafico.map((p) => {
      const ac = p.ok_aprovou + p.ok_rejeitou + p.div_aprovou_jeitinho + p.div_rejeitou_jeitinho;
      const bs = p.ok_aprovou + p.ok_rejeitou + p.div_aprovou + p.div_rejeitou;
      const v = bs ? (ac / bs) * 100 : 0;
      return {
        month: rotuloG(p.chave),
        label: bs ? num(v) : "—",
        h: bs ? alturaAcc(v) : 0,
        tip: bs
          ? `${rotuloG(p.chave)} — ${fmt(ac)} acertos de ${fmt(bs)} revisados`
          : `${rotuloG(p.chave)} — sem revisões no período`,
      };
    }),

    fatorPrincipal: !temMotivos
      ? "Classificação de motivos indisponível nesta extração."
      : maiorFator
        ? `${maiorFator[0]} — ${fmt(maiorFator[1])} de ${fmt(totalFatores)} divergências (${Math.round(pct(maiorFator[1], totalFatores))}%)`
        : "Nenhuma divergência no período.",

    penteFino: fatores.map(([name, count, color]) => ({
      name,
      count,
      color,
      pct: Math.round(pct(count, maiorFator ? maiorFator[1] : 1)),
      tip: `${name} — ${fmt(count)} casos, ${Math.round(pct(count, totalFatores))}% das divergências`,
    })),

    notaSemJustificativa: !temMotivos
      ? "Rode a versão atualizada da consulta para trazer a classificação dos motivos e a contagem de decisões sem justificativa."
      : semJustDiv
        ? `Em ${fmt(semJustDiv)} decisões o revisor contrariou a IA sem registrar o motivo — nesses casos não dá para saber se houve erro da IA ou razão externa. O campo passou a ser obrigatório recentemente, então a cobertura melhora daqui em diante.`
        : "Todas as decisões contrárias à IA no período têm justificativa registrada.",

    porTipo: situacoes.map(([name, count, acerto, cor]) => ({
      name,
      vol: fmt(count),
      acc: baseAcc ? num(pct(count, baseAcc)) : "—",
      classificacao: acerto ? "Acerto" : "Divergência",
      classificacaoColor: acerto ? POS : NEG,
      peso: Math.round(pct(count, Math.max(1, ...situacoes.map((s) => s[1])))),
      cor,
    })),
  };
}
