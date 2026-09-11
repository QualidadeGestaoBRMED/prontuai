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
  DadosDashboard,
  PontoAcuracia,
  PontoSerie,
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
    "Prontuários liberados na plataforma. Meta: 100% das expedições da empresa.",
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
  ptsLiberados: string;
  ptsPendencia: string;
  coberturaSeries: BarraPercentual[];
  expSeries: BarraExpedicao[];
  ranking: LinhaRanking[];
  totalClinicas: number;
  adocao: LinhaAdocao[];

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
  const maxExp = Math.max(1, ...grafico.map((p) => p.antecipada + p.em_dia + p.atrasada));
  const passo = grafico.length ? 600 / grafico.length : 600;

  // ---- expedições da empresa (denominador da cobertura) ---------------------
  const porDia = dados.expedicoes_dia || {};
  const dataDe = (iso?: string) => {
    if (!iso) return null;
    const q = partes(iso);
    return new Date(Date.UTC(q.y, q.m - 1, q.d));
  };
  const primeiroDoc = dataDe(dados.periodo?.doc_mais_antigo);
  const ultimoDoc = dataDe(dados.periodo?.doc_mais_recente);

  /** Intervalo de datas coberto por um conjunto de pontos da série. */
  const intervalo = (pontos: PontoSerie[]) => {
    if (!pontos.length) return null;
    const a = partes(pontos[0].chave);
    const z = partes(pontos[pontos.length - 1].chave);
    let ini = new Date(Date.UTC(a.y, a.m - 1, a.d));
    // não conta expedição de antes do primeiro documento processado
    if (primeiroDoc && ini < primeiroDoc) ini = primeiroDoc;
    const fim =
      cfg.periodo.serie === "semanal"
        ? new Date(Date.UTC(z.y, z.m - 1, z.d + 6))
        : new Date(Date.UTC(z.y, z.m, 0)); // último dia do mês
    return { ini, fim };
  };

  const faixaAtual = intervalo(atual);
  const faixaAnterior = intervalo(anterior);
  const expEmpresa = faixaAtual ? expedicoesEntre(porDia, faixaAtual.ini, faixaAtual.fim, ultimoDoc) : 0;
  const expEmpresaAnt = faixaAnterior
    ? expedicoesEntre(porDia, faixaAnterior.ini, faixaAnterior.fim, ultimoDoc)
    : 0;
  const cobertura = pct(liberados, expEmpresa);

  const kpiExpedicoes = (): Kpi => {
    if (!expEmpresa) {
      return kpi(
        "Expedições via ProntuAI",
        fmt(liberados),
        variacao("validados"),
        "up",
        "liberados na plataforma · total da empresa não informado no período",
      );
    }
    const antPct = comparavel && expEmpresaAnt ? pct(soma(anterior, "validados"), expEmpresaAnt) : null;
    return kpi(
      "Expedições via ProntuAI",
      num(cobertura),
      antPct === null ? "" : pp(cobertura, antPct),
      "up",
      `${fmt(liberados)} de ${fmt(expEmpresa)} expedições · meta 100%`,
    );
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

    // Linhas em bandas fixas: liberados na faixa superior, pendência na inferior.
    ptsLiberados: grafico
      .map((p, i) => `${((i + 0.5) * passo).toFixed(1)},${(100 - (pct(p.validados, p.docs) / 100) * 85).toFixed(1)}`)
      .join(" "),
    ptsPendencia: grafico
      .map((p, i) => `${((i + 0.5) * passo).toFixed(1)},${(258 - (pct(p.rejeitados, p.docs) / 100) * 83).toFixed(1)}`)
      .join(" "),

    // Cobertura do ProntuAI sobre as expedições da empresa, ponto a ponto.
    coberturaSeries: (() => {
      const pontos = grafico.map((p) => {
        const a = partes(p.chave);
        let ini = new Date(Date.UTC(a.y, a.m - 1, a.d));
        if (primeiroDoc && ini < primeiroDoc) ini = primeiroDoc;
        const fim =
          cfg.grafico.serie === "semanal"
            ? new Date(Date.UTC(a.y, a.m - 1, a.d + 6))
            : new Date(Date.UTC(a.y, a.m, 0));
        const emp = expedicoesEntre(porDia, ini, fim, ultimoDoc);
        const v = emp ? (p.validados / emp) * 100 : 0;
        return { mes: rotuloG(p.chave), v, emp, lib: p.validados };
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

    expSeries: grafico.map((p) => {
      const tot = p.antecipada + p.em_dia + p.atrasada;
      return {
        month: rotuloG(p.chave),
        total: tot ? fmt(tot) : "—",
        hAnt: bar(p.antecipada, maxExp, 190),
        hDia: bar(p.em_dia, maxExp, 190),
        hAtr: bar(p.atrasada, maxExp, 190),
        tip: tot
          ? `${rotuloG(p.chave)} — ${fmt(p.antecipada)} antecipadas, ${fmt(p.em_dia)} em dia, ${fmt(p.atrasada)} atrasadas`
          : `${rotuloG(p.chave)} — sem prazo registrado`,
      };
    }),

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
