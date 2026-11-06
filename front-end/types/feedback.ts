/**
 * Parecer humano sobre o acerto da IA, e o motivo de rejeição que sai dele.
 *
 * Espelho de `back-end/app/models/feedback.py` (categorias do parecer) e de
 * `back-end/app/models/document.py` (códigos de rejeição): o back-end recusa o
 * que não estiver nas listas dele, então mudar uma metade sem a outra deixa o
 * revisor marcando opção que a API rejeita. Dois testes comparam os arquivos:
 * `test_categorias_do_back_batem_com_as_do_front` e
 * `test_codigos_de_rejeicao_batem_com_os_do_front`.
 */

export type FeedbackStatus =
  | "IA_CORRETA"
  | "IA_CORRETA_COM_AJUSTES"
  | "IA_INCORRETA";

/**
 * O que a IA disse sobre um exame, como vem da comparação (`tabela_comparacao`).
 * `null` quando não há veredito: o exame foi digitado pelo revisor, ou a IA
 * nem chegou a comparar.
 */
export type Veredito =
  | "faltante"
  | "encontrado"
  | "parcialmente_encontrado"
  | "extra_no_ocr";

/** "A", "A e B", "A, B e C". */
export function juntarNomes(nomes: string[]): string {
  if (nomes.length <= 1) return nomes[0] ?? "";
  return `${nomes.slice(0, -1).join(", ")} e ${nomes[nomes.length - 1]}`;
}

/**
 * Motivos que apontam para um exame. `frase` é o que o modal escreve sozinho em
 * `notes` — só nome de exame e texto fixo, nunca dado do paciente.
 *
 * As que o modal não oferece mais (extra, validade, "Outro" de exame) ficam na
 * lista porque há pareceres gravados com elas, e reabrir um deles precisa saber
 * o rótulo.
 */
export const CATEGORIAS_EXAME: Array<{
  valor: string;
  rotulo: string;
  frase: (exame: string) => string;
}> = [
  {
    valor: "FALTANTE_INCORRETO",
    rotulo: "Estava no documento",
    frase: (x) => `${x} estava no documento, mas a IA apontou como faltante.`,
  },
  {
    valor: "SINONIMO_NAO_RECONHECIDO",
    rotulo: "Com outro nome",
    frase: (x) => `${x} estava no documento com outro nome, e a IA não reconheceu.`,
  },
  {
    valor: "DADO_BRNET",
    rotulo: "Exigência errada no BRNET",
    frase: (x) => `A exigência de ${x} veio errada do BRNET.`,
  },
  {
    valor: "ENCONTRADO_INCORRETO",
    rotulo: "Não estava",
    frase: (x) => `${x} foi dado como encontrado, mas não estava no documento.`,
  },
  {
    valor: "EXAME_OUTRA_DATA",
    rotulo: "De outra data",
    frase: (x) => `${x} foi aceito, mas era de outra data.`,
  },
  {
    valor: "EXAME_ILEGIVEL",
    rotulo: "Ilegível ou incompleto",
    frase: (x) => `${x} foi aceito, mas estava ilegível ou incompleto.`,
  },
  {
    valor: "EXAME_SEM_ASSINATURA",
    rotulo: "Sem carimbo",
    frase: (x) => `${x} foi aceito, mas estava sem carimbo ou assinatura.`,
  },
  {
    // O laudo do exame é de outro colaborador (nome/CPF de outra pessoa). Por
    // exame, e não do documento: o caso real é UM laudo trocado no prontuário.
    valor: "EXAME_OUTRA_PESSOA",
    rotulo: "De outra pessoa",
    frase: (x) => `${x} foi aceito, mas era de outra pessoa.`,
  },
  {
    valor: "EXAME_NAO_RECONHECIDO",
    rotulo: "Estava, mas não foi lido",
    frase: (x) => `${x} estava no documento, mas a IA não extraiu.`,
  },
  {
    valor: "EXTRA_INCORRETO",
    rotulo: "Era legítimo",
    frase: (x) => `${x} foi apontado como extra, mas era legítimo.`,
  },
  {
    valor: "VALIDADE_PERIODICIDADE",
    rotulo: "Validade ou periodicidade",
    frase: (x) => `A validade ou a periodicidade de ${x} saiu errada.`,
  },
  {
    valor: "OUTRO",
    rotulo: "Outro",
    frase: (x) => `Outro problema em ${x}.`,
  },
];

/** Onde a IA errou — a primeira pergunta do caminho "Errou". */
export type Area = "exames" | "brnet" | "paciente" | "documento" | "outro";

/**
 * Problemas que não apontam exame. `area` diz em qual pergunta do modal cada um
 * aparece; viajam em `document_issues`.
 *
 * Os de "documento" saíram do que os revisores escreviam no antigo campo
 * "Motivo da rejeição" (272 textos no dev, em ordem de frequência), e são
 * também motivo de rejeição — o código de rejeição tem o mesmo nome.
 */
export const CATEGORIAS_DOCUMENTO: Array<{
  valor: string;
  rotulo: string;
  area: Exclude<Area, "exames">;
  frase: string;
}> = [
  { valor: "BRNET_EXPEDICAO", rotulo: "A expedição existe", area: "brnet", frase: "A expedição em aberto existia no BRNET." },
  { valor: "BRNET_PACIENTE", rotulo: "O paciente existe", area: "brnet", frase: "O paciente estava cadastrado no BRNET." },
  { valor: "BRNET_EXIGENCIA", rotulo: "Exigências erradas", area: "brnet", frase: "As exigências de exame vieram erradas do BRNET." },
  { valor: "OCR_NOME", rotulo: "Nome", area: "paciente", frase: "A IA leu o nome do paciente errado." },
  { valor: "OCR_CPF", rotulo: "CPF", area: "paciente", frase: "A IA leu o CPF errado." },
  { valor: "OCR_CNPJ", rotulo: "CNPJ", area: "paciente", frase: "A IA leu o CNPJ errado." },
  { valor: "OCR_DATA", rotulo: "Data", area: "paciente", frase: "A IA leu a data errada." },
  { valor: "ASO_INCOMPLETO", rotulo: "ASO cortado", area: "documento", frase: "ASO cortado ou em duas páginas." },
  { valor: "PRONTUARIO_INCOMPLETO", rotulo: "Só veio parte", area: "documento", frase: "Veio só parte do prontuário." },
  { valor: "ANEXOS_SEPARADOS", rotulo: "Vários anexos", area: "documento", frase: "Exames enviados em anexos separados." },
  { valor: "ASO_SEM_APTIDAO", rotulo: "ASO sem aptidão ou NR", area: "documento", frase: "ASO sem marcação de aptidão ou de NR." },
  { valor: "ASO_DADO_ERRADO", rotulo: "ASO com dado errado", area: "documento", frase: "ASO com data ou carimbo errado." },
  { valor: "ASO_SEM_REAPROVEITAMENTO", rotulo: "Sem ASO de reaproveitamento", area: "documento", frase: "Não usou o ASO de reaproveitamento." },
  { valor: "ENVIO_DUPLICADO", rotulo: "Duplicado", area: "documento", frase: "Documento enviado em duplicidade." },
  { valor: "PACIENTE_TROCADO", rotulo: "De outro paciente", area: "documento", frase: "Documento de outro paciente." },
  { valor: "DOC_ILEGIVEL", rotulo: "Ilegível", area: "documento", frase: "Documento ilegível." },
  { valor: "OUTRO_PROBLEMA", rotulo: "Outro", area: "outro", frase: "" },
];

/**
 * O que a clínica precisa corrigir. Gravado em `documents.rejection_codes`
 * junto do texto em `rejection_reason`; os de documento têm o mesmo nome da
 * categoria do parecer.
 */
export const CODIGOS_REJEICAO = [
  "EXAME_FALTANTE",
  "EXAME_OUTRA_DATA",
  "EXAME_ILEGIVEL",
  "EXAME_SEM_ASSINATURA",
  "EXAME_OUTRA_PESSOA",
  "ASO_INCOMPLETO",
  "ASO_SEM_APTIDAO",
  "ASO_DADO_ERRADO",
  "ASO_SEM_REAPROVEITAMENTO",
  "PRONTUARIO_INCOMPLETO",
  "ANEXOS_SEPARADOS",
  "ENVIO_DUPLICADO",
  "PACIENTE_TROCADO",
  "DOC_ILEGIVEL",
] as const;

export type CodigoRejeicao = (typeof CODIGOS_REJEICAO)[number];

export type RejectionCode = { codigo: CodigoRejeicao; exame?: string };

/** Como cada código de exame abre a frase do motivo: "Faltou: A e B." */
export const ROTULO_REJEICAO_EXAME: Partial<Record<CodigoRejeicao, string>> = {
  EXAME_FALTANTE: "Faltou",
  EXAME_OUTRA_DATA: "De outra data",
  EXAME_ILEGIVEL: "Ilegível ou incompleto",
  EXAME_SEM_ASSINATURA: "Sem carimbo ou assinatura",
  EXAME_OUTRA_PESSOA: "De outra pessoa",
};

/**
 * As respostas de "O que houve?" para um exame, pelo que a IA tinha dito dele.
 * É o que deixa a pergunta curta: num exame que ela deu como faltante, "não
 * estava" não faz sentido. `rejeicao` é o código que a resposta gera quando o
 * documento é rejeitado — as que não geram nenhum só corrigem a IA.
 */
export const OPCOES_EXAME: Record<
  "faltante" | "encontrado" | "avulso",
  Array<{ categoria: string; rotulo: string; rejeicao?: CodigoRejeicao }>
> = {
  faltante: [
    { categoria: "FALTANTE_INCORRETO", rotulo: "Estava no documento" },
    { categoria: "SINONIMO_NAO_RECONHECIDO", rotulo: "Com outro nome" },
    { categoria: "DADO_BRNET", rotulo: "Não é exigido" },
  ],
  encontrado: [
    { categoria: "ENCONTRADO_INCORRETO", rotulo: "Não estava", rejeicao: "EXAME_FALTANTE" },
    { categoria: "EXAME_OUTRA_DATA", rotulo: "De outra data", rejeicao: "EXAME_OUTRA_DATA" },
    { categoria: "EXAME_ILEGIVEL", rotulo: "Ilegível ou incompleto", rejeicao: "EXAME_ILEGIVEL" },
    { categoria: "EXAME_SEM_ASSINATURA", rotulo: "Sem carimbo", rejeicao: "EXAME_SEM_ASSINATURA" },
    { categoria: "EXAME_OUTRA_PESSOA", rotulo: "De outra pessoa", rejeicao: "EXAME_OUTRA_PESSOA" },
  ],
  // Digitado pelo revisor: não estava na lista do BRNET.
  avulso: [
    { categoria: "EXAME_NAO_RECONHECIDO", rotulo: "Estava, mas não foi lido" },
    { categoria: "DADO_BRNET", rotulo: "Faltou (o BRNET não exigiu)", rejeicao: "EXAME_FALTANTE" },
  ],
};

/**
 * Motivo externo: a IA leu o documento certo, e o revisor decidiu diferente por
 * uma razão que não estava nele. É um ACERTO da IA — o painel de acurácia lê
 * este campo do parecer para não contar a divergência como erro.
 *
 * Aparece quando o revisor libera o que a IA rejeitou e responde "Acertou". As
 * opções saíram do que os revisores escreviam na justificativa da aprovação
 * (medido no dev, em ordem de frequência — ver `app/models/feedback.py`).
 *
 * `frase` vai para `approval_reason`, a justificativa da aprovação — que a
 * clínica lê na notificação, por isso sem jargão. Mantém as palavras que a regex
 * antiga do painel conhece ("por fora", "não anexou a guia", "outro ticket",
 * "sem o exame"...): o parecer decide primeiro, mas o detalhe por exame ainda
 * classifica pelo texto. Em "Outro" a justificativa é o que o revisor escreveu.
 *
 * A chave é `codigo`, e não `valor`, porque o teste de contrato de
 * `CATEGORIAS_DOCUMENTO` lê todo `valor:` que vem depois dela neste arquivo.
 */
export const MOTIVOS_EXTERNOS: Array<{ codigo: MotivoExterno; rotulo: string; frase: string }> = [
  {
    codigo: "EXAME_POR_FORA",
    rotulo: "Exame feito em outro sistema ou parceiro",
    frase: "Exame feito por fora, em parceiro ou outro sistema.",
  },
  {
    codigo: "GUIA_NAO_ANEXADA",
    rotulo: "Clínica não anexou o voucher, mas os exames estão no PDF",
    frase: "A clínica não anexou a guia (voucher), mas os exames estão no anexo.",
  },
  {
    codigo: "CNPJ_DIVERGENTE",
    rotulo: "CNPJ do ASO é de outra empresa",
    frase: "O CNPJ do ASO é de outra empresa; o paciente foi conferido no BRNET.",
  },
  {
    codigo: "ATENDIMENTO_NAO_REGISTRADO",
    rotulo: "Atendimento ainda não registrado no BRNET",
    frase: "O atendimento ainda não estava registrado no BRNET quando o documento foi lido.",
  },
  {
    codigo: "OUTRO_TICKET",
    rotulo: "Enviado em duplicidade ou de outro ticket",
    frase: "Os exames apontados são de outro ticket ou foram lançados duas vezes.",
  },
  { codigo: "CLIENTE_AUTORIZOU", rotulo: "Cliente autorizou liberar sem o exame", frase: "Liberado sem o exame, autorizado pelo cliente." },
  { codigo: "OUTRO", rotulo: "Outro", frase: "" },
];

export type MotivoExterno =
  | "EXAME_POR_FORA"
  | "GUIA_NAO_ANEXADA"
  | "CNPJ_DIVERGENTE"
  | "ATENDIMENTO_NAO_REGISTRADO"
  | "OUTRO_TICKET"
  | "CLIENTE_AUTORIZOU"
  | "OUTRO";

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
  motivo_externo: MotivoExterno | null;
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
  /** Só com `IA_CORRETA`; com "OUTRO", `notes` é obrigatório. */
  motivo_externo?: MotivoExterno | null;
};
