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
    titulo: "Acertou com ressalvas",
    descricao: "Aproveitável, mas algo precisou de correção.",
  },
  {
    valor: "IA_INCORRETA",
    titulo: "A IA errou",
    descricao: "O resultado não podia ser usado como veio.",
  },
];

export const CATEGORIAS_EXAME: Array<{
  valor: string;
  rotulo: string;
  ajuda: string;
  /**
   * Motivo cujo exame, por definição, não está na tabela de comparação — a IA
   * não o extraiu. Nestes o campo de digitar vem aberto e a lista some.
   */
  soDigitado?: boolean;
}> = [
  {
    valor: "FALTANTE_INCORRETO",
    rotulo: "Faltante que existia",
    ajuda: "A IA marcou como faltante, mas o exame estava no documento.",
  },
  {
    valor: "EXTRA_INCORRETO",
    rotulo: "Extra indevido",
    ajuda: "A IA marcou como extra um exame que era legítimo.",
  },
  {
    valor: "SINONIMO_NAO_RECONHECIDO",
    rotulo: "Sinônimo não reconhecido",
    ajuda: "O exame estava lá com outro nome e a IA não ligou os dois.",
  },
  {
    valor: "EXAME_NAO_RECONHECIDO",
    rotulo: "Exame não reconhecido",
    ajuda: "Estava no PDF e a IA não extraiu — por isso não aparece na lista.",
    soDigitado: true,
  },
  {
    valor: "VALIDADE_PERIODICIDADE",
    rotulo: "Validade / periodicidade",
    ajuda: "O exame existe, mas a validade ou a periodicidade saiu errada.",
  },
  {
    valor: "DADO_BRNET",
    rotulo: "Dado do BRNET",
    ajuda: "A exigência veio errada ou desatualizada do BRNET.",
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
 */
export const CATEGORIAS_DOCUMENTO: Array<{
  valor: string;
  rotulo: string;
  ajuda: string;
}> = [
  {
    valor: "OCR_NOME",
    rotulo: "Nome do paciente",
    ajuda: "O nome saiu errado ou corrompido na leitura.",
  },
  {
    valor: "OCR_CPF",
    rotulo: "CPF",
    ajuda: "O CPF saiu errado na leitura.",
  },
  {
    valor: "OCR_DATA",
    rotulo: "Data",
    ajuda: "A data do exame ou do ASO saiu errada.",
  },
  {
    valor: "DOC_ILEGIVEL",
    rotulo: "Documento ilegível",
    ajuda: "O documento não foi lido de forma aproveitável.",
  },
];

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

/** Rótulo curto do veredito da IA, ao lado de cada exame na lista. */
export const ROTULO_VEREDITO: Record<string, string> = {
  encontrado: "encontrado",
  faltante: "faltante",
  extra_no_ocr: "extra no OCR",
  parcialmente_encontrado: "parcial",
};
