/**
 * Parecer humano sobre o acerto da IA em um documento.
 *
 * Espelho de `back-end/app/models/feedback.py`: o back-end recusa categoria e
 * status fora destas listas, então mudar uma metade sem a outra deixa o revisor
 * marcando chip que a API rejeita. O teste
 * `back-end/tests/test_document_feedback.py::test_categorias_do_back_batem_com_as_do_front`
 * compara os dois arquivos e quebra quando eles divergem.
 *
 * Duas famílias de motivo: os de exame (lista de pares motivo↔exame) e os do
 * documento inteiro, que não têm exame a que amarrar.
 */

export type FeedbackStatus =
  | "IA_CORRETA"
  | "IA_CORRETA_COM_AJUSTES"
  | "IA_INCORRETA";

/** Status que exigem detalhamento — mesma regra do back-end. */
export const STATUS_COM_DETALHES: FeedbackStatus[] = [
  "IA_CORRETA_COM_AJUSTES",
  "IA_INCORRETA",
];

export const OPCOES_FEEDBACK: Array<{
  valor: FeedbackStatus;
  titulo: string;
  descricao: string;
}> = [
  {
    valor: "IA_CORRETA",
    titulo: "A IA acertou",
    descricao: "A leitura e a comparação bateram com o documento.",
  },
  {
    valor: "IA_CORRETA_COM_AJUSTES",
    titulo: "A IA acertou com ressalvas",
    descricao: "Aproveitável, mas algo precisou de correção.",
  },
  {
    valor: "IA_INCORRETA",
    titulo: "A IA errou",
    descricao: "O resultado não podia ser usado como veio.",
  },
];

/**
 * Frase que o modal escreve sozinho para um motivo, a partir dos exames
 * marcados. `exames` já vem pronto para leitura ("A, B e C"); `plural` diz se
 * é mais de um, para a concordância.
 *
 * Só nomes de exame e texto fixo entram aqui — nunca dado do paciente — então a
 * frase pode ir para `notes` sem risco de PII.
 */
export type Frase = (exames: string, plural: boolean) => string;

export const CATEGORIAS_EXAME: Array<{
  valor: string;
  rotulo: string;
  ajuda: string;
  /**
   * Ausente em "Outro" de propósito: ali não há o que dizer por conta própria,
   * e o revisor precisa contar o que houve.
   */
  frase?: Frase;
}> = [
  {
    valor: "FALTANTE_INCORRETO",
    rotulo: "Faltante que existia",
    ajuda: "A IA marcou como faltante, mas o exame estava no documento.",
    frase: (x, p) =>
      p
        ? `${x} estavam no documento, mas a IA apontou como faltantes.`
        : `${x} estava no documento, mas a IA apontou como faltante.`,
  },
  {
    valor: "EXTRA_INCORRETO",
    rotulo: "Extra que era legítimo",
    ajuda: "A IA marcou como extra um exame que era legítimo.",
    frase: (x, p) =>
      p
        ? `${x} foram apontados como extras, mas eram exames legítimos.`
        : `${x} foi apontado como extra, mas era um exame legítimo.`,
  },
  {
    valor: "SINONIMO_NAO_RECONHECIDO",
    rotulo: "Sinônimo não reconhecido",
    ajuda: "O exame estava no documento com outro nome e a IA não ligou os dois.",
    frase: (x, p) =>
      p
        ? `${x} estavam no documento com outros nomes, e a IA não reconheceu.`
        : `${x} estava no documento com outro nome, e a IA não reconheceu.`,
  },
  {
    valor: "EXAME_NAO_RECONHECIDO",
    rotulo: "Exame não reconhecido",
    ajuda: "Estava no PDF e a IA não extraiu, por isso caiu como faltante.",
    frase: (x, p) =>
      p
        ? `${x} estavam no PDF, mas a IA não extraiu.`
        : `${x} estava no PDF, mas a IA não extraiu.`,
  },
  {
    valor: "VALIDADE_PERIODICIDADE",
    rotulo: "Validade ou periodicidade",
    ajuda: "O exame existe, mas a validade ou a periodicidade saiu errada.",
    frase: (x, p) =>
      p
        ? `${x} estavam no documento, mas a validade ou a periodicidade saiu errada.`
        : `${x} estava no documento, mas a validade ou a periodicidade saiu errada.`,
  },
  {
    valor: "DADO_BRNET",
    rotulo: "Exigência do BRNET",
    ajuda: "A exigência veio errada ou desatualizada do BRNET.",
    frase: (x, p) =>
      p
        ? `As exigências de ${x} vieram erradas ou desatualizadas do BRNET.`
        : `A exigência de ${x} veio errada ou desatualizada do BRNET.`,
  },
  {
    valor: "OUTRO",
    rotulo: "Outro",
    ajuda: "Algum outro problema neste exame.",
  },
];

/**
 * Problemas do documento inteiro — não apontam exame. Ficam num bloco à parte
 * no modal e viajam em `document_issues`, não em `issue_items`.
 *
 * Duas famílias, nesta ordem na tela: o que a clínica enviou errado (ASO e
 * envio) vem primeiro, porque é o que mais aparece, e os erros de leitura da
 * IA vêm depois.
 *
 * A lista de conteúdo saiu do que os revisores escreveram no antigo campo
 * "Motivo da rejeição", removido do modal. Medido em 387 rejeições escritas à
 * mão no banco de dev: o ASO responde por 106 (27%), peça faltando no
 * prontuário por 34, exames em vários anexos por 25 e envio duplicado por 9.
 * As quatro categorias de leitura que existiam cobriam 7 das 387 — o resto não
 * tinha onde ser marcado.
 */
export const CATEGORIAS_DOCUMENTO: Array<{
  valor: string;
  rotulo: string;
  ajuda: string;
  /** Frase fixa: o problema é do documento, não há exame para citar. */
  frase: string;
}> = [
  {
    valor: "ASO_INCOMPLETO",
    rotulo: "ASO cortado ou em duas páginas",
    ajuda: "Veio só parte do ASO, ou faltou a segunda página.",
    frase: "O ASO veio cortado ou com uma das páginas faltando.",
  },
  {
    valor: "ASO_SEM_APTIDAO",
    rotulo: "ASO sem marcação de aptidão",
    ajuda: "O ASO não tem a marcação de apto ou inapto.",
    frase: "O ASO veio sem a marcação de aptidão.",
  },
  {
    valor: "ASO_DADO_ERRADO",
    rotulo: "ASO com dado errado",
    ajuda: "Tipagem, data ou carimbo errados no ASO.",
    frase: "O ASO veio com dado errado.",
  },
  {
    valor: "PRONTUARIO_INCOMPLETO",
    rotulo: "Faltou peça do prontuário",
    ajuda: "Veio só o ASO, só os laboratoriais, ou faltou a ficha médica.",
    frase: "O prontuário veio incompleto: faltou uma das peças.",
  },
  {
    valor: "ANEXOS_SEPARADOS",
    rotulo: "Exames em vários anexos",
    ajuda: "Os exames do mesmo paciente vieram em envios separados.",
    frase: "Os exames do paciente vieram repartidos em mais de um anexo.",
  },
  {
    valor: "ENVIO_DUPLICADO",
    rotulo: "Documento duplicado",
    ajuda: "O mesmo documento foi enviado mais de uma vez.",
    frase: "O mesmo documento foi enviado mais de uma vez.",
  },
  {
    valor: "PACIENTE_TROCADO",
    rotulo: "Documento de outro paciente",
    ajuda: "O documento, ou parte dele, é de outro paciente.",
    frase: "O documento, ou parte dele, é de outro paciente.",
  },
  {
    valor: "OCR_NOME",
    rotulo: "Nome do paciente",
    ajuda: "O nome saiu errado ou corrompido na leitura.",
    frase: "O nome do paciente foi lido errado.",
  },
  {
    valor: "OCR_CPF",
    rotulo: "CPF",
    ajuda: "O CPF saiu errado na leitura.",
    frase: "O CPF foi lido errado.",
  },
  {
    valor: "OCR_DATA",
    rotulo: "Data",
    ajuda: "A data do exame ou do ASO saiu errada.",
    frase: "A data do exame ou do ASO foi lida errada.",
  },
  {
    valor: "DOC_ILEGIVEL",
    rotulo: "Documento ilegível",
    ajuda: "O documento não foi lido de forma aproveitável.",
    frase: "O documento não pôde ser lido de forma aproveitável.",
  },
];

/** "A", "A e B", "A, B e C". */
export function juntarNomes(nomes: string[]): string {
  if (nomes.length <= 1) return nomes[0] ?? "";
  return `${nomes.slice(0, -1).join(", ")} e ${nomes[nomes.length - 1]}`;
}

/**
 * Monta o "o que aconteceu" a partir do que foi marcado: uma frase por motivo
 * (juntando os exames dele) e uma por problema de documento, na ordem da tela.
 * "Outro" não gera frase — é o caso em que só o revisor sabe contar.
 *
 * Pura de propósito: roda na tela e também na reabertura de um parecer salvo,
 * para separar o texto automático do que o revisor escreveu à mão.
 */
export function comporResumo(
  exames: Array<{ categoria: string; nomes: string[] }>,
  problemasDoc: string[],
): string[] {
  const frases: string[] = [];
  for (const { categoria, nomes } of exames) {
    const frase = CATEGORIAS_EXAME.find((c) => c.valor === categoria)?.frase;
    if (frase && nomes.length > 0) frases.push(frase(juntarNomes(nomes), nomes.length > 1));
  }
  for (const valor of problemasDoc) {
    const frase = CATEGORIAS_DOCUMENTO.find((c) => c.valor === valor)?.frase;
    if (frase) frases.push(frase);
  }
  return frases;
}

/** Um par (motivo, exame) — o que a IA errou e onde. */
export type FeedbackIssueItem = {
  categoria: string;
  exame: string;
  /** Veredito da IA para esse exame na tabela de comparação. */
  veredito_ia: string | null;
  /** Exame digitado pelo revisor, fora da tabela de comparação. */
  fora_da_lista: boolean;
};

/** Parecer já salvo, como volta do GET. `null` quando nunca foi avaliado. */
export type DocumentFeedback = {
  id: string;
  document_id: string;
  status: FeedbackStatus;
  issue_categories: string[];
  issue_items: FeedbackIssueItem[];
  document_issues: string[];
  notes: string | null;
  reviewed_by_email: string | null;
  reviewed_by_id: string | null;
  created_at: string | null;
  updated_at: string | null;
};

/** Corpo do PUT. */
export type DocumentFeedbackInput = {
  status: FeedbackStatus;
  issue_items: FeedbackIssueItem[];
  document_issues: string[];
  notes: string | null;
};

