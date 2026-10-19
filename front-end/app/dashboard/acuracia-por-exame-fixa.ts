/**
 * Acurácia por exame — VALOR FIXO, provisório.
 *
 * Calculado uma vez, à mão, sobre a cópia de produção de 18/10/2026, e
 * congelado aqui. Não acompanha o filtro de período nem o botão Atualizar. A
 * versão definitiva vem do parecer do revisor no modal de feedback (em produção
 * desde 19/10), que diz exame a exame se a IA acertou; quando ela existir, este
 * arquivo sai inteiro.
 *
 * Por que inferido e não lido: o dump é anterior ao modal, então não há parecer
 * por exame. A decisão do revisor é sobre o DOCUMENTO, e o exame herda dela:
 *   * falta indevida   — a IA marcou o exame como faltante e o revisor liberou o
 *                        documento sem registrar motivo externo;
 *   * presença indevida — a IA deu o exame como presente, aprovou o documento, e
 *                        o revisor rejeitou citando o exame no motivo;
 *   * o resto conta como acerto.
 * Mesmas regras de julgamento de `dashboard_indicadores.sql` (decisão da IA e do
 * revisor pelo audit_logs, reenvio do mesmo arquivo conta uma vez, falha técnica
 * fora). Nomes que só diferem no acento ("PARASITOLOGICO"/"PARASITOLÓGICO")
 * foram somados.
 *
 * Janela: 12/09 a 17/10/2026, desde a adoção do catálogo de exames — pedido do
 * produto. O motor passou a ler o vocabulário do catálogo em produção em 11/09,
 * 17h26 (PR #23 na `v1`); a janela começa no primeiro dia inteiro depois disso e
 * termina no último dia completo do dump.
 *
 * Cuidado: a janela atravessa a grande carga do catálogo de 06/10 (De_Para +
 * variações), e o que veio antes dela pesa na lista. TGO e TGP saem com 82% aqui
 * e com 98% contando só de 07/10 em diante; o total vai de 98,0% (12/09 a 05/10)
 * para 98,3% (07/10 a 17/10).
 */
import type { Kpi } from "./metricas";

export const ACURACIA_EXAME_FIXA = {
  janela: "12/09 a 17/10",
  fonte: "cópia de produção de 18/10",
  documentos: 3520,
  // Total inclui os exames que ficaram fora da lista por volume baixo.
  avaliacoes: 17816,
  faltaIndevida: 208,
  presencaIndevida: 128,
  /** Exames com menos avaliações que isto na janela entram no total, não na lista. */
  minimoAvaliacoes: 20,
};

/** [exame do BRNET, avaliações, falta indevida, presença indevida] */
const EXAMES: [string, number, number, number][] = [
  ["PESQUISA DE SANGUE OCULTO NAS FEZES", 56, 15, 1],
  ["TOXICOLÓGICO CAPILAR", 63, 15, 0],
  ["SUMÁRIO DE URINA (EAS)", 69, 13, 1],
  ["TRIAGEM TOXICOLÓGICO", 66, 12, 1],
  ["TGP (ALT)", 206, 36, 1],
  ["TGO (AST)", 207, 36, 1],
  ["ETANOL URINÁRIO", 36, 4, 0],
  ["TESTE ERGOMÉTRICO", 81, 0, 6],
  ["HDL", 43, 3, 0],
  ["LDL", 43, 3, 0],
  ["LIPIDOGRAMA (PERFIL LIPÍDICO)", 179, 8, 1],
  ["ANTI-HCV", 20, 0, 1],
  ["ÁCIDO ÚRICO", 63, 3, 0],
  ["PSA TOTAL", 107, 4, 1],
  ["TRIGLICERÍDEOS", 90, 4, 0],
  ["COLESTEROL TOTAL", 100, 4, 0],
  ["COPROCULTURA", 105, 2, 2],
  ["ACUIDADE VISUAL", 310, 4, 6],
  ["RADIOGRAFIA DE COLUNA LOMBO SACRA AP/PERFIL", 261, 3, 3],
  ["ÁCIDO TRANS-TRANSMUCÔNICO", 46, 0, 1],
  ["GGT (GAMA-GT)", 244, 3, 2],
  ["QUESTIONÁRIO PARA IDENTIFICAÇÃO DE INDIVÍDUOS COM EPILEPSIA - OMS", 104, 2, 0],
  ["BILIRRUBINA TOTAL E FRAÇÕES", 105, 1, 1],
  ["ANTI-HBS", 55, 0, 1],
  ["AVALIAÇÃO PSICOLÓGICA", 504, 0, 9],
  ["RADIOGRAFIA DE TÓRAX PA", 112, 1, 1],
  ["AVALIAÇÃO PSICOSSOCIAL", 337, 1, 5],
  ["ESPIROMETRIA", 626, 0, 11],
  ["RADIOGRAFIA DE TÓRAX - PADRÃO OIT", 481, 0, 8],
  ["AVALIAÇÃO ODONTOLÓGICA", 440, 1, 6],
  ["GLICEMIA DE JEJUM", 1014, 8, 6],
  ["CREATININA", 269, 3, 0],
  ["TIPAGEM SANGUÍNEA / FATOR RH", 182, 0, 2],
  ["TSH", 105, 1, 0],
  ["FOSFATASE ALCALINA", 105, 0, 1],
  ["HEMOGRAMA COMPLETO COM PLAQUETAS", 1520, 5, 7],
  ["ELETROCARDIOGRAMA", 910, 1, 6],
  ["AUDIOMETRIA TONAL", 1479, 2, 9],
  ["ELETROENCEFALOGRAMA", 615, 0, 4],
  ["GLICOSE", 161, 0, 1],
  ["PARASITOLÓGICO DE FEZES", 347, 1, 1],
  ["ACUIDADE VISUAL COM SENSO CROMÁTICO", 883, 0, 4],
  ["ROMBERG", 298, 0, 1],
  ["CLÍNICO OCUPACIONAL", 3497, 0, 3],
  ["VDRL", 205, 0, 0],
  ["HEMOGLOBINA GLICADA", 190, 0, 0],
  ["PSICOSSOCIAL", 131, 0, 0],
  ["RETICULÓCITOS", 94, 0, 0],
  ["URÉIA", 93, 0, 0],
  ["ÁCIDO METIL HIPÚRICO", 38, 0, 0],
  ["ÁCIDO MANDÉLICO", 33, 0, 0],
  ["ORTO-CRESOL", 29, 0, 0],
  ["2.5 HEXANODIONA", 28, 0, 0],
  ["ÁCIDO FENIL-GLIOXILICO", 25, 0, 0],
  ["ÁCIDO TRICLOROACETICO", 25, 0, 0],
  ["HBSAG", 23, 0, 0],
  ["HEMOGRAMA", 20, 0, 0],
];

export interface LinhaAcuraciaExame {
  exame: string;
  avaliacoes: number;
  faltaIndevida: number;
  presencaIndevida: number;
  erros: number;
  acuracia: number;
  acuraciaLabel: string;
  /** Largura de cada segmento da barra de erro, em % da linha. */
  pctFalta: number;
  pctPresenca: number;
  tip: string;
}

const pctBr = (v: number) => `${v.toFixed(1).replace(".", ",")}%`;
const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

const total = ACURACIA_EXAME_FIXA;
const errosTotal = total.faltaIndevida + total.presencaIndevida;
export const ACURACIA_EXAME_TOTAL = {
  acuraciaLabel: pctBr(((total.avaliacoes - errosTotal) / total.avaliacoes) * 100),
  erros: errosTotal,
};

/**
 * O card que fica ao lado de "Acurácia", no mesmo formato dos outros KPIs. Sem
 * variação (não há período anterior para um valor fixo); a linha de apoio diz
 * de quando é o número, porque o card ao lado mede outra janela. O volume fica
 * no modal; o selo "EM BREVE" do cabeçalho avisa que a versão definitiva vem.
 */
export const KPI_ACURACIA_EXAME: Kpi = {
  label: "Acurácia por exame",
  value: ACURACIA_EXAME_TOTAL.acuraciaLabel,
  delta: "",
  deltaColor: "#767A7B",
  sub: `Desde a adoção do catálogo de exames: documentos enviados de ${total.janela}`,
  tip: `Valores fixos dos documentos enviados de ${total.janela}: não acompanham o filtro de período.`,
  ajuda: "acuraciaExame",
};

// A barra é da TAXA de erro, na escala do exame que mais erra: com a acurácia
// toda entre 84% e 100%, uma barra de acurácia sairia cheia em todas as linhas.
const maiorTaxa = Math.max(...EXAMES.map(([, n, f, p]) => (f + p) / n));

export const LINHAS_ACURACIA_EXAME: LinhaAcuraciaExame[] = EXAMES.map(([exame, avaliacoes, f, p]) => {
  const erros = f + p;
  const acuracia = ((avaliacoes - erros) / avaliacoes) * 100;
  return {
    exame,
    avaliacoes,
    faltaIndevida: f,
    presencaIndevida: p,
    erros,
    acuracia,
    acuraciaLabel: pctBr(acuracia),
    pctFalta: (f / avaliacoes / maiorTaxa) * 100,
    pctPresenca: (p / avaliacoes / maiorTaxa) * 100,
    tip: erros
      ? `${exame} — ${plural(avaliacoes, "avaliação", "avaliações")}: ` +
        `${plural(f, "falta apontada e liberada pelo revisor", "faltas apontadas e liberadas pelo revisor")}, ` +
        `${plural(p, "aprovação cobrada pelo revisor", "aprovações cobradas pelo revisor")}`
      : `${exame} — ${plural(avaliacoes, "avaliação", "avaliações")}, nenhuma divergência`,
  };
});
