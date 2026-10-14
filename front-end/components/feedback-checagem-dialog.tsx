"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangleIcon, BotIcon, CheckIcon, Loader2Icon, PlusIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { API_ENDPOINTS } from "@/lib/config";
import { authFetch } from "@/lib/auth-fetch";
import { cn } from "@/lib/utils";
import {
  CATEGORIAS_DOCUMENTO,
  CATEGORIAS_EXAME,
  OPCOES_EXAME,
  ROTULO_REJEICAO_EXAME,
  juntarNomes,
  type Area,
  type CodigoRejeicao,
  type DocumentFeedback,
  type DocumentFeedbackInput,
  type FeedbackIssueItem,
  type RejectionCode,
  type Veredito,
} from "@/types/feedback";
import type { DocumentProcessingResult } from "@/types/process";

/** Um exame da lista do modal, com o que a IA disse dele. */
export type ExamePrevisto = { nome: string; veredito: Veredito | null };

/** O que a IA decidiu sozinha, antes de qualquer revisão humana. */
export type DecisaoIA = {
  decisao: "aprovado" | "rejeitado";
  /** `false` quando ela parou antes de comparar exames (CPF, CNPJ, BRNET). */
  comparou: boolean;
  /** O que ela disse, numa frase. Se ela acertou a rejeição, é o motivo que fica. */
  motivo: string;
  /** Exames que ela apontou como faltantes, com o nome do BRNET. */
  faltantes: string[];
};

export type FeedbackAlvo = {
  documentId: string;
  paciente?: string;
  cpf?: string;
  /**
   * "decisao": veio de Aprovar/Rejeitar e a decisão AINDA NÃO foi gravada — o
   * diálogo a confirma e coleta o parecer junto.
   * "avaliacao": veio de "Avaliar IA" num documento já decidido.
   */
  modo: "decisao" | "avaliacao";
  /** A decisão humana: a que está sendo confirmada, ou a que já foi gravada. */
  decisao: "aprovado" | "rejeitado";
  ia: DecisaoIA;
  /** Os exames que o revisor pode apontar — ver `examesDoResultado`. */
  exames: ExamePrevisto[];
};

/** O que sai do diálogo quando ele confirma uma decisão. */
export type DecisaoConfirmada = {
  parecer: DocumentFeedbackInput;
  /** Só na rejeição: o texto que a clínica lê e os códigos que o geraram. */
  rejeicao?: { motivo: string; codigos: RejectionCode[] };
};

type Props = {
  alvo: FeedbackAlvo | null;
  onClose: () => void;
  /**
   * Só no modo "decisao". Grava a decisão e o parecer — nesta ordem, porque o
   * back-end recusa parecer de documento sem decisão humana (409). Deve lançar
   * em caso de falha: o diálogo fica aberto com tudo marcado.
   */
  onConfirmarDecisao?: (dados: DecisaoConfirmada) => Promise<void>;
};

/** Para comparar nomes de exame: sem caixa, sem acento, sem espaço sobrando. */
function normalizarNome(nome: string): string {
  return nome
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** O payload às vezes chega sem a lista, ou com algo que não é lista. */
function textos(valor: unknown): string[] {
  return Array.isArray(valor) ? valor.filter((v): v is string => typeof v === "string") : [];
}

const MINUSCULAS = new Set(["a", "ao", "com", "da", "das", "de", "do", "dos", "e", "em", "na", "no", "o", "ou", "por", "sem"]);

/**
 * "RAIO-X DE TÓRAX PA (OIT)" → "Raio-X de tórax PA (OIT)". O BRNET devolve tudo
 * em caixa alta, e uma fileira de pílulas em maiúsculas é ruído puro. Siglas
 * (até 3 letras, ou entre parênteses) ficam como estão. Só para exibir: o que
 * vai para a API é sempre o nome original.
 */
export function nomeLegivel(nome: string): string {
  if (/\p{Ll}/u.test(nome)) return nome;
  let profundidade = 0;
  let primeira = true;
  let saida = "";
  for (const parte of nome.split(/([\p{L}\p{N}]+)/u)) {
    if (!/^[\p{L}\p{N}]+$/u.test(parte)) {
      for (const c of parte) {
        if (c === "(") profundidade++;
        if (c === ")") profundidade = Math.max(0, profundidade - 1);
      }
      saida += parte;
      continue;
    }
    const minuscula = parte.toLowerCase();
    let palavra =
      profundidade > 0 || /\d/.test(parte) || (parte.length <= 3 && !MINUSCULAS.has(minuscula))
        ? parte
        : minuscula;
    if (primeira) {
      palavra = palavra.charAt(0).toUpperCase() + palavra.slice(1);
      primeira = false;
    }
    saida += palavra;
  }
  return saida;
}

/**
 * Os exames que o BRNET exigia, cada um com o que a IA disse dele.
 *
 * O nome vem de `brmed_result.exames_obrigatorios` — nome de catálogo, saído da
 * API e não do OCR — e não da `tabela_comparacao`, que falta em 12% dos
 * documentos e mistura nome de catálogo com texto lido do PDF. A tabela só
 * entra para saber quem ficou "parcialmente encontrado". Os extras (nome de
 * OCR) ficam de fora: não pesam na decisão, e só alongariam a lista.
 *
 * Sem `validation_result` a IA não chegou a comparar e o veredito fica nulo:
 * mostrar "encontrado" ali seria inventar um julgamento que não houve.
 */
export function examesDoResultado(r?: DocumentProcessingResult | null): ExamePrevisto[] {
  if (!r) return [];
  const comparou = Boolean(r.validation_result);
  const faltantes = new Set(textos(r.validation_result?.exames_faltantes).map(normalizarNome));
  const parciais = new Set(
    (Array.isArray(r.tabela_comparacao) ? r.tabela_comparacao : [])
      .filter((t) => t?.status === "parcialmente_encontrado" && typeof t.exame === "string")
      .map((t) => normalizarNome(t.exame)),
  );
  const vistos = new Set<string>();
  const lista: ExamePrevisto[] = [];
  const incluir = (nome: string, veredito: Veredito | null) => {
    const chave = normalizarNome(nome);
    if (!chave || vistos.has(chave)) return;
    vistos.add(chave);
    lista.push({ nome: nome.trim(), veredito });
  };
  for (const nome of textos(r.brmed_result?.exames_obrigatorios)) {
    const chave = normalizarNome(nome);
    incluir(
      nome,
      !comparou
        ? null
        : faltantes.has(chave)
          ? "faltante"
          : parciais.has(chave)
            ? "parcialmente_encontrado"
            : "encontrado",
    );
  }
  // Faltante fora da lista de exigidos não deveria existir, mas a lista de
  // exigidos pode faltar no payload — e o faltante é justamente o exame que o
  // revisor mais precisa conseguir apontar.
  for (const nome of textos(r.validation_result?.exames_faltantes)) incluir(nome, "faltante");
  return lista;
}

/**
 * O que a IA decidiu, lido do resultado dela — e não do status do documento,
 * que depois da revisão passa a ser o da pessoa.
 *
 * Erro de negócio ou técnico (paciente não encontrado, CNPJ inválido, expedição
 * em aberto) é rejeição sem comparação: 347 dos 628 motivos de rejeição
 * gravados no dev eram essa mensagem copiada.
 */
export function decisaoDaIA(r?: DocumentProcessingResult | null): DecisaoIA {
  const erro = [r?.erro, r?.error, r?.business_error?.message].find(
    (x): x is string => typeof x === "string" && x.trim().length > 0,
  );
  if (erro) return { decisao: "rejeitado", comparou: false, motivo: erro.trim(), faltantes: [] };
  const faltantes = textos(r?.validation_result?.exames_faltantes);
  if (faltantes.length > 0) {
    return {
      decisao: "rejeitado",
      comparou: true,
      motivo: `Faltou: ${juntarNomes(faltantes.map(nomeLegivel))}.`,
      faltantes,
    };
  }
  const exigidos = textos(r?.brmed_result?.exames_obrigatorios).length;
  return {
    decisao: "aprovado",
    comparou: true,
    motivo: exigidos
      ? `Encontrou ${exigidos === 1 ? "o exame exigido" : `os ${exigidos} exames exigidos`} pelo BRNET.`
      : "Aprovou o documento.",
    faltantes: [],
  };
}

type Linha = ExamePrevisto & { avulso: boolean };

const ROTULO_AREA: Record<Area, string> = {
  exames: "Nos exames",
  brnet: "Na consulta ao BRNET",
  paciente: "Nos dados do paciente",
  documento: "No documento",
  outro: "Outro",
};

const PERGUNTA_AREA: Record<Exclude<Area, "exames" | "outro">, string> = {
  brnet: "O que estava errado na consulta?",
  paciente: "O que ela leu errado?",
  documento: "O que veio errado no documento?",
};

function opcoesDe(linha: Linha) {
  if (linha.avulso) return OPCOES_EXAME.avulso;
  return linha.veredito === "faltante" ? OPCOES_EXAME.faltante : OPCOES_EXAME.encontrado;
}

function areaDe(problema: string): Exclude<Area, "exames"> | undefined {
  return CATEGORIAS_DOCUMENTO.find((c) => c.valor === problema)?.area;
}

/**
 * O texto que o modal escreve sozinho em `notes`: uma frase por exame e uma
 * por problema, na ordem da tela. Pura de propósito — roda ao salvar e ao
 * reabrir um parecer, para separar o texto automático do comentário do revisor.
 */
function frasesDoParecer(itens: Array<{ categoria: string; exame: string }>, problemas: string[]) {
  const frases: string[] = [];
  for (const { categoria, exame } of itens) {
    const frase = CATEGORIAS_EXAME.find((c) => c.valor === categoria)?.frase;
    if (frase) frases.push(frase(nomeLegivel(exame)));
  }
  for (const valor of problemas) {
    const frase = CATEGORIAS_DOCUMENTO.find((c) => c.valor === valor)?.frase;
    if (frase) frases.push(frase);
  }
  return frases;
}

const ESTILO = {
  pergunta: "mb-2 flex flex-wrap items-baseline gap-2 text-sm font-semibold text-foreground",
  dica: "text-xs font-normal text-muted-foreground",
  grupo: "mb-1.5 mt-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground first:mt-0",
  pilula:
    "inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-white px-3 py-1.5 text-[13px] text-foreground transition-colors hover:border-primary/40 dark:bg-white/5",
  pilulaAtiva: "border-primary bg-primary text-primary-foreground hover:border-primary dark:bg-primary",
  radio:
    "cursor-pointer rounded-lg border border-border bg-white px-2.5 py-1 text-[12.5px] text-foreground transition-colors hover:border-primary/40 dark:bg-white/5",
  radioAtivo: "border-secondary bg-secondary/10 font-semibold ring-1 ring-inset ring-secondary dark:bg-secondary/15",
  passo: "animate-in fade-in-0 slide-in-from-top-1 duration-200 motion-reduce:animate-none",
} as const;

/** Bolinha de seleção das pílulas de múltipla escolha. */
function Marca({ ativa }: { ativa: boolean }) {
  return (
    <span
      className={cn(
        "grid size-3.5 place-items-center rounded-full border-[1.5px]",
        ativa ? "border-primary-foreground bg-primary-foreground text-primary" : "border-border",
      )}
    >
      {ativa && <CheckIcon className="size-2.5" strokeWidth={4} />}
    </span>
  );
}

/**
 * Confirma a decisão do revisor e pergunta uma coisa só: a IA acertou?
 *
 * Se acertou, acabou — numa rejeição, o motivo dela vira o motivo que vai para
 * a clínica. Se errou, o modal pergunta onde, e cada resposta abre a próxima
 * pergunta: nos exames → em quais → o que houve com cada um, com as opções do
 * que a IA tinha dito daquele exame. O "o que aconteceu" do parecer e o motivo
 * da rejeição saem dessas respostas; o revisor só escreve em "Outro".
 *
 * Substitui o texto livre de "Motivo da rejeição" e os três cartões de status
 * da versão anterior. A ideia é ser mais rápido do que digitar: quando a
 * decisão do revisor bate com a da IA, "Acertou" já vem marcado e o foco
 * começa no botão de confirmar — Enter e pronto. Quando contraria, "Errou" já
 * vem aberto, porque ali é preciso dizer onde.
 *
 * O status do parecer é deduzido, não perguntado: acertou → IA_CORRETA; errou
 * numa decisão igual à dela → com ressalvas; errou numa decisão contrária →
 * IA_INCORRETA.
 *
 * Enquanto está aberto o cronômetro de revisão fica pausado, então o tempo de
 * responder não entra no `review_active_ms` (ver docs/tempo-de-revisao-desenho.md).
 */
export function FeedbackChecagemDialog({ alvo, onClose, onConfirmarDecisao }: Props) {
  // O último alvo aberto, para desenhar a tela enquanto ela SOME. Quem fecha
  // zera `alvo` na hora, mas o Radix ainda anima a saída por ~200ms; sem isto,
  // nesse intervalo o título e as perguntas trocavam no meio do fade.
  const ultimoAlvo = useRef<FeedbackAlvo | null>(alvo);
  if (alvo) ultimoAlvo.current = alvo;
  const vis = alvo ?? ultimoAlvo.current;

  const [veredito, setVeredito] = useState<"acertou" | "errou" | null>(null);
  const [areas, setAreas] = useState<Area[]>([]);
  /** Exames apontados, pelo nome original (o que vai para a API). */
  const [exames, setExames] = useState<string[]>([]);
  /** A resposta de "O que houve?" de cada exame apontado. */
  const [oque, setOque] = useState<Record<string, string>>({});
  /** Problemas marcados nas perguntas de BRNET, paciente e documento. */
  const [problemas, setProblemas] = useState<string[]>([]);
  const [avulsos, setAvulsos] = useState<Linha[]>([]);
  const [incluindo, setIncluindo] = useState(false);
  const [rascunho, setRascunho] = useState("");
  const [notas, setNotas] = useState("");
  const [comentando, setComentando] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [existente, setExistente] = useState<DocumentFeedback | null>(null);

  // Depende de `alvo`, não de `alvo.documentId`: o componente fica montado entre
  // uma abertura e outra, e cada abertura cria um objeto novo. Com o id na lista
  // de dependências, reabrir O MESMO documento não dispararia nada e o
  // formulário voltaria com o rascunho abandonado da vez anterior.
  useEffect(() => {
    if (!alvo) return;
    let vivo = true;
    const concorda = alvo.ia.decisao === alvo.decisao;
    setVeredito(concorda ? "acertou" : "errou");
    setAreas([]);
    setExames([]);
    setOque({});
    setProblemas([]);
    setAvulsos([]);
    setIncluindo(false);
    setRascunho("");
    setNotas("");
    setComentando(false);
    setErro(null);
    setExistente(null);
    // No modo "decisao" o documento ainda nem foi decidido: não existe parecer
    // anterior para buscar, e o GET só atrasaria a abertura.
    if (alvo.modo === "decisao") return;
    setCarregando(true);
    authFetch(API_ENDPOINTS.DOCUMENT_FEEDBACK(alvo.documentId))
      .then((r) => (r.ok ? r.json() : null))
      .then((salvo: DocumentFeedback | null) => {
        if (!vivo || !salvo) return;
        setExistente(salvo);
        if (salvo.status === "IA_CORRETA") {
          setVeredito("acertou");
          return;
        }
        setVeredito("errou");
        // Remonta as respostas a partir do que foi gravado. Exame que não está
        // mais na lista (digitado, ou o resultado foi reprocessado) volta como
        // avulso.
        const doBanco: Record<string, string> = {};
        const marcados: string[] = [];
        const restaurados: Linha[] = [];
        for (const item of salvo.issue_items ?? []) {
          const chave = normalizarNome(item.exame);
          const linha =
            alvo.exames.find((e) => normalizarNome(e.nome) === chave) ??
            restaurados.find((e) => normalizarNome(e.nome) === chave);
          const nome = linha?.nome ?? item.exame;
          if (!linha) restaurados.push({ nome, veredito: null, avulso: true });
          if (!marcados.includes(nome)) marcados.push(nome);
          doBanco[nome] ??= item.categoria;
        }
        const docs = (salvo.document_issues ?? []).filter((p) => p !== "OUTRO_PROBLEMA");
        const areasSalvas = new Set<Area>();
        if (marcados.length) areasSalvas.add("exames");
        for (const p of salvo.document_issues ?? []) {
          const area = areaDe(p);
          if (area) areasSalvas.add(area);
        }
        setAreas([...areasSalvas]);
        setExames(marcados);
        setOque(doBanco);
        setProblemas(docs);
        setAvulsos(restaurados);
        // `notes` foi gravado como frases automáticas + comentário. Refaz as
        // frases e devolve ao campo só o comentário — senão, ao salvar de novo,
        // o texto automático entraria duplicado.
        const automatico = frasesDoParecer(salvo.issue_items ?? [], docs).join("\n");
        const gravado = salvo.notes ?? "";
        const comentario =
          automatico && gravado.startsWith(automatico)
            ? gravado.slice(automatico.length).trim()
            : gravado;
        setNotas(comentario);
        setComentando(Boolean(comentario));
      })
      .catch(() => undefined)
      .finally(() => {
        if (vivo) setCarregando(false);
      });
    return () => {
      vivo = false;
    };
  }, [alvo]);

  const modoDecisao = vis?.modo === "decisao";
  const rejeitando = vis?.decisao === "rejeitado";
  const ia = vis?.ia;
  const concorda = ia?.decisao === vis?.decisao;
  // Rejeitar o que a IA aprovou e dizer que ela acertou não deixa motivo
  // nenhum para a clínica: o único caminho ali é apontar onde ela errou.
  const acertoImpossivel = rejeitando && ia?.decisao === "aprovado";

  const linhas: Linha[] = useMemo(
    () => [...(vis?.exames ?? []).map((e) => ({ ...e, avulso: false })), ...avulsos],
    [vis, avulsos],
  );

  const areasPossiveis: Area[] = ia?.comparou
    ? ["exames", "paciente", ...(rejeitando ? (["documento"] as const) : []), "outro"]
    : ["brnet", "paciente", ...(rejeitando ? (["documento"] as const) : []), "outro"];

  const errou = veredito === "errou";
  const apontaExames = errou && areas.includes("exames");

  const itens: FeedbackIssueItem[] = useMemo(() => {
    if (!apontaExames) return [];
    return exames.flatMap((nome) => {
      const linha = linhas.find((l) => l.nome === nome);
      if (!linha) return [];
      const categoria = oque[nome] ?? opcoesDe(linha)[0].categoria;
      return [{ categoria, exame: nome, veredito_ia: linha.veredito, fora_da_lista: linha.avulso }];
    });
  }, [apontaExames, exames, linhas, oque]);

  // Só os problemas das perguntas que estão abertas: desmarcar "No documento"
  // esconde a pergunta e leva junto o que estava marcado nela.
  const problemasValidos = useMemo(
    () => (errou ? problemas.filter((p) => areas.includes(areaDe(p) as Area)) : []),
    [errou, problemas, areas],
  );
  const pediuOutro = errou && areas.includes("outro");
  const documentIssues = [...problemasValidos, ...(pediuOutro ? ["OUTRO_PROBLEMA"] : [])];

  /** O motivo que a clínica lê, e os códigos que o geraram. Só na rejeição. */
  const rejeicao = useMemo(() => {
    if (!rejeitando || !ia) return null;
    if (!errou) {
      return {
        motivo: ia.motivo,
        codigos: ia.faltantes.map((exame) => ({ codigo: "EXAME_FALTANTE" as const, exame })),
      };
    }
    // Errou: parte do que ela apontou como faltante, tira o que o revisor disse
    // que não faltava, e soma o que ele apontou como faltando ou vindo errado.
    const apontados = new Set(itens.map((i) => i.exame));
    const porCodigo = new Map<CodigoRejeicao, string[]>();
    const somar = (codigo: CodigoRejeicao, exame: string) =>
      porCodigo.set(codigo, [...(porCodigo.get(codigo) ?? []), exame]);
    for (const exame of ia.faltantes) if (!apontados.has(exame)) somar("EXAME_FALTANTE", exame);
    for (const item of itens) {
      const linha = linhas.find((l) => l.nome === item.exame);
      const codigo = linha && opcoesDe(linha).find((o) => o.categoria === item.categoria)?.rejeicao;
      if (codigo) somar(codigo, item.exame);
    }
    const partes: string[] = [];
    const codigos: RejectionCode[] = [];
    for (const [codigo, nomes] of porCodigo) {
      partes.push(`${ROTULO_REJEICAO_EXAME[codigo]}: ${juntarNomes(nomes.map(nomeLegivel))}.`);
      for (const exame of nomes) codigos.push({ codigo, exame });
    }
    for (const p of problemasValidos) {
      const categoria = CATEGORIAS_DOCUMENTO.find((c) => c.valor === p);
      if (categoria?.area !== "documento") continue;
      partes.push(categoria.frase);
      codigos.push({ codigo: p as CodigoRejeicao });
    }
    if (notas.trim()) partes.push(notas.trim());
    return { motivo: partes.join(" "), codigos };
  }, [rejeitando, ia, errou, itens, linhas, problemasValidos, notas]);

  const frases = errou ? frasesDoParecer(itens, problemasValidos) : [];
  const textoParecer = [frases.join("\n"), notas.trim()].filter(Boolean).join("\n\n");

  /** O que falta responder, na ordem das perguntas. */
  const pendencia = (() => {
    if (!veredito) return "Diga se a IA acertou.";
    if (!errou) return null;
    if (areas.length === 0) return "Escolha onde a IA errou.";
    if (apontaExames && exames.length === 0) return "Escolha os exames.";
    for (const area of ["brnet", "paciente", "documento"] as const) {
      if (areas.includes(area) && !problemasValidos.some((p) => areaDe(p) === area)) {
        return PERGUNTA_AREA[area].replace("?", ".").replace(/^O que/, "Responda: o que");
      }
    }
    if (pediuOutro && !notas.trim()) return "Conte o que aconteceu.";
    if (rejeitando && rejeicao && !rejeicao.motivo) {
      return "Falta o motivo para a clínica: marque o que veio errado ou comente.";
    }
    return null;
  })();

  function montarParecer(): DocumentFeedbackInput | null {
    if (!veredito) return null;
    if (!errou) return { status: "IA_CORRETA", issue_items: [], document_issues: [], notes: null };
    return {
      status: concorda ? "IA_CORRETA_COM_AJUSTES" : "IA_INCORRETA",
      issue_items: itens,
      document_issues: documentIssues,
      notes: textoParecer || null,
    };
  }

  function escolherVeredito(valor: "acertou" | "errou") {
    if (valor === "acertou" && acertoImpossivel) return;
    setVeredito(valor);
    setErro(null);
  }

  function alternar<T>(lista: T[], valor: T): T[] {
    return lista.includes(valor) ? lista.filter((x) => x !== valor) : [...lista, valor];
  }

  function incluirExame() {
    const nome = rascunho.trim();
    if (!nome) return;
    // Digitou um exame que já está na lista, só que em outra caixa ou sem
    // acento? Marca o da lista, com o nome original. Sem isto ele entrava como
    // `fora_da_lista`, com nome fora do padrão e marcado para curadoria.
    const jaListado = linhas.find((l) => normalizarNome(l.nome) === normalizarNome(nome));
    if (!jaListado) setAvulsos((atuais) => [...atuais, { nome, veredito: null, avulso: true }]);
    const alvoNome = jaListado?.nome ?? nome;
    setExames((atuais) => (atuais.includes(alvoNome) ? atuais : [...atuais, alvoNome]));
    setRascunho("");
    setIncluindo(false);
  }

  async function confirmar() {
    const parecer = montarParecer();
    if (!alvo || !parecer || pendencia) return;
    setSalvando(true);
    setErro(null);
    try {
      if (alvo.modo === "decisao") {
        // Não chama onClose(): depois de decidir, quem fecha (e fecha também o
        // modal de detalhes atrás) é a página. Fechar por aqui passaria pelo
        // caminho de cancelamento, que religa o cronômetro de revisão.
        await onConfirmarDecisao?.({ parecer, rejeicao: rejeicao ?? undefined });
        return;
      }
      const resposta = await authFetch(API_ENDPOINTS.DOCUMENT_FEEDBACK(alvo.documentId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parecer),
      });
      if (!resposta.ok) {
        const dados = await resposta.json().catch(() => null);
        throw new Error(dados?.detail ?? `Falha ao salvar o parecer (HTTP ${resposta.status}).`);
      }
      toast.success(existente ? "Parecer atualizado." : "Obrigado pelo parecer!");
      onClose();
    } catch (e) {
      // Nada foi gravado: o diálogo fica aberto com tudo marcado.
      setErro(e instanceof Error ? e.message : String(e));
    } finally {
      setSalvando(false);
    }
  }

  const faltantesDaIA = linhas.filter((l) => !l.avulso && l.veredito === "faltante");
  const encontradosDaIA = linhas.filter(
    (l) => !l.avulso && (l.veredito === "encontrado" || l.veredito === "parcialmente_encontrado"),
  );

  const pilulaExame = (linha: Linha) => {
    const ativo = exames.includes(linha.nome);
    return (
      <button
        key={linha.nome}
        type="button"
        aria-pressed={ativo}
        onClick={() => setExames((atuais) => alternar(atuais, linha.nome))}
        className={cn(ESTILO.pilula, ativo && ESTILO.pilulaAtiva)}
      >
        <Marca ativa={ativo} />
        {nomeLegivel(linha.nome)}
      </button>
    );
  };

  const resumo =
    rejeitando && modoDecisao && rejeicao?.motivo
      ? { rotulo: "Motivo que vai para a clínica", texto: rejeicao.motivo }
      : errou && frases.length > 0
        ? { rotulo: "Vai registrar", texto: frases.join(" ") }
        : null;

  return (
    // ESC e clique fora também são bloqueados durante o envio: fechar no meio da
    // gravação deixaria o revisor sem saber se a decisão foi registrada.
    <Dialog open={!!alvo} onOpenChange={(aberto) => !aberto && !salvando && onClose()}>
      {/* Ancorado no topo, e não centralizado: centralizado, o diálogo cresce
          para os dois lados a cada pergunta que abre e o próximo alvo foge do
          cursor. */}
      <DialogContent
        className="top-[6vh] flex max-h-[88vh] translate-y-0 flex-col gap-0 overflow-hidden p-0 sm:max-w-[560px]"
        // O foco começa no botão de confirmar: quando "Acertou" já vem marcado,
        // Enter confirma de primeira.
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          document.getElementById("feedback-confirmar")?.focus();
        }}
        onKeyDown={(e) => {
          if ((e.target as HTMLElement).closest("input, textarea")) return;
          const tecla = e.key.toLowerCase();
          if (tecla === "a") escolherVeredito("acertou");
          if (tecla === "e") escolherVeredito("errou");
        }}
      >
        <DialogHeader className="gap-1 px-6 pt-6 pr-12">
          <DialogTitle className="text-[19px] font-bold">
            {modoDecisao
              ? rejeitando
                ? "Rejeitar documento"
                : "Aprovar documento"
              : "Como foi o resultado da IA?"}
          </DialogTitle>
          <DialogDescription className="text-[13px]">
            {vis?.paciente ? (
              <span className="font-semibold text-foreground/80">{vis.paciente}</span>
            ) : (
              "Documento"
            )}
            {vis?.cpf ? ` · CPF ${vis.cpf}` : ""}
            {!modoDecisao && ` · ${rejeitando ? "rejeitado" : "aprovado"}`}
            {existente ? ` · avaliado por ${existente.reviewed_by_email ?? "outro revisor"}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 pt-4">
          <div className="grid gap-[18px]">
            {ia && (
              <div className="flex items-start gap-2.5 rounded-[10px] bg-primary/5 px-3 py-2.5 text-[13px] leading-snug text-foreground/85">
                <BotIcon className="mt-px size-4 shrink-0 text-muted-foreground" />
                <span>
                  <span className="font-semibold text-foreground">
                    {ia.decisao === "rejeitado" ? "A IA rejeitou." : "A IA aprovou."}
                  </span>{" "}
                  {ia.motivo}
                </span>
              </div>
            )}

            {carregando ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2Icon className="size-4 animate-spin" /> Carregando parecer…
              </p>
            ) : (
              <>
                <section>
                  <p className="mb-2.5 text-[15px] font-semibold text-foreground">A IA acertou?</p>
                  <div className="grid grid-cols-2 gap-2.5" role="radiogroup" aria-label="A IA acertou?">
                    <BotaoVeredito
                      tipo="acertou"
                      ativo={veredito === "acertou"}
                      desabilitado={acertoImpossivel}
                      onClick={() => escolherVeredito("acertou")}
                      titulo="Acertou"
                      detalhe={
                        acertoImpossivel
                          ? "Ela aprovou; você está rejeitando"
                          : rejeitando && ia?.decisao === "rejeitado"
                            ? "Mantém o motivo dela"
                            : "Confirma o resultado"
                      }
                    />
                    <BotaoVeredito
                      tipo="errou"
                      ativo={errou}
                      onClick={() => escolherVeredito("errou")}
                      titulo="Errou"
                      detalhe="Vou apontar onde"
                    />
                  </div>
                </section>

                {errou && (
                  <div className="grid gap-[18px]">
                    <section className={ESTILO.passo}>
                      <p className={ESTILO.pergunta}>
                        Onde ela errou? <span className={ESTILO.dica}>pode marcar mais de um</span>
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {areasPossiveis.map((area) => {
                          const ativa = areas.includes(area);
                          return (
                            <button
                              key={area}
                              type="button"
                              aria-pressed={ativa}
                              onClick={() => {
                                setAreas((atuais) => alternar(atuais, area));
                                setErro(null);
                              }}
                              className={cn(ESTILO.pilula, ativa && ESTILO.pilulaAtiva)}
                            >
                              <Marca ativa={ativa} />
                              {ROTULO_AREA[area]}
                            </button>
                          );
                        })}
                      </div>
                    </section>

                    {areasPossiveis
                      .filter((area) => areas.includes(area))
                      .map((area) => {
                        if (area === "exames") {
                          return (
                            <div key={area} className="grid gap-[18px]">
                              <section className={ESTILO.passo}>
                                <p className={ESTILO.pergunta}>Em quais exames?</p>
                                {faltantesDaIA.length > 0 && (
                                  <>
                                    <p className={ESTILO.grupo}>Ela apontou como faltante</p>
                                    <div className="flex flex-wrap gap-1.5">
                                      {faltantesDaIA.map(pilulaExame)}
                                    </div>
                                  </>
                                )}
                                <p className={ESTILO.grupo}>
                                  {faltantesDaIA.length > 0 ? "Ela deu como encontrado" : "Exames que ela encontrou"}
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {encontradosDaIA.map(pilulaExame)}
                                  {avulsos.map(pilulaExame)}
                                  {incluindo ? (
                                    <span className="inline-flex items-center rounded-full border border-secondary bg-white py-0.5 pl-3 pr-1 dark:bg-white/5">
                                      <input
                                        autoFocus
                                        value={rascunho}
                                        onChange={(e) => setRascunho(e.target.value)}
                                        onKeyDown={(e) => {
                                          if (e.key === "Enter") {
                                            // Enter aqui inclui o exame; não confirma o modal.
                                            e.preventDefault();
                                            incluirExame();
                                          }
                                        }}
                                        onBlur={() => !rascunho.trim() && setIncluindo(false)}
                                        maxLength={120}
                                        placeholder="Nome do exame"
                                        aria-label="Nome do exame"
                                        className="w-44 bg-transparent py-1 text-[13px] outline-none"
                                      />
                                      <button
                                        type="button"
                                        onClick={incluirExame}
                                        className="cursor-pointer rounded-full px-2 py-1 text-xs font-semibold text-secondary hover:bg-secondary/10"
                                      >
                                        Incluir
                                      </button>
                                    </span>
                                  ) : (
                                    <button
                                      type="button"
                                      onClick={() => setIncluindo(true)}
                                      className={cn(ESTILO.pilula, "border-dashed text-muted-foreground")}
                                    >
                                      <PlusIcon className="size-3.5" />
                                      Outro exame
                                    </button>
                                  )}
                                </div>
                              </section>

                              {exames.length > 0 && (
                                <section className={ESTILO.passo}>
                                  <p className={ESTILO.pergunta}>O que houve?</p>
                                  <div>
                                    {exames.map((nome) => {
                                      const linha = linhas.find((l) => l.nome === nome);
                                      if (!linha) return null;
                                      const opcoes = opcoesDe(linha);
                                      const atual = oque[nome] ?? opcoes[0].categoria;
                                      // Um parecer antigo pode ter resposta que hoje não é
                                      // oferecida para este exame: aparece junto, para não sumir.
                                      const extra = opcoes.some((o) => o.categoria === atual)
                                        ? []
                                        : [{ categoria: atual, rotulo: CATEGORIAS_EXAME.find((c) => c.valor === atual)?.rotulo ?? atual }];
                                      return (
                                        <div
                                          key={nome}
                                          className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-t py-2.5 first:border-t-0 first:pt-0.5"
                                        >
                                          <span className="min-w-0 text-sm font-medium text-foreground">
                                            {nomeLegivel(nome)}
                                            <span className="block text-[11px] font-normal text-muted-foreground">
                                              {linha.avulso
                                                ? "fora da lista"
                                                : linha.veredito === "faltante"
                                                  ? "IA: faltante"
                                                  : "IA: encontrado"}
                                            </span>
                                          </span>
                                          <div className="flex flex-wrap gap-1" role="radiogroup" aria-label={nomeLegivel(nome)}>
                                            {[...opcoes, ...extra].map((o) => (
                                              <button
                                                key={o.categoria}
                                                type="button"
                                                role="radio"
                                                aria-checked={atual === o.categoria}
                                                onClick={() => setOque((atuais) => ({ ...atuais, [nome]: o.categoria }))}
                                                className={cn(ESTILO.radio, atual === o.categoria && ESTILO.radioAtivo)}
                                              >
                                                {o.rotulo}
                                              </button>
                                            ))}
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </section>
                              )}
                            </div>
                          );
                        }
                        if (area === "outro") {
                          return (
                            <section key={area} className={ESTILO.passo}>
                              <p className={ESTILO.pergunta}>O que aconteceu?</p>
                              <Textarea
                                value={notas}
                                onChange={(e) => setNotas(e.target.value)}
                                rows={2}
                                maxLength={2000}
                                placeholder="Conte em poucas palavras."
                                className="bg-white text-[13px] dark:bg-white/5"
                              />
                            </section>
                          );
                        }
                        return (
                          <section key={area} className={ESTILO.passo}>
                            <p className={ESTILO.pergunta}>{PERGUNTA_AREA[area]}</p>
                            <div className="flex flex-wrap gap-1.5">
                              {CATEGORIAS_DOCUMENTO.filter((c) => c.area === area).map((c) => {
                                const ativo = problemas.includes(c.valor);
                                return (
                                  <button
                                    key={c.valor}
                                    type="button"
                                    aria-pressed={ativo}
                                    onClick={() => setProblemas((atuais) => alternar(atuais, c.valor))}
                                    className={cn(ESTILO.pilula, ativo && ESTILO.pilulaAtiva)}
                                  >
                                    {c.rotulo}
                                  </button>
                                );
                              })}
                            </div>
                          </section>
                        );
                      })}

                    {areas.length > 0 && !pediuOutro &&
                      (comentando ? (
                        <Textarea
                          autoFocus={!notas}
                          value={notas}
                          onChange={(e) => setNotas(e.target.value)}
                          rows={2}
                          maxLength={2000}
                          placeholder="Comentário opcional."
                          className={cn("bg-white text-[13px] dark:bg-white/5", ESTILO.passo)}
                        />
                      ) : (
                        <button
                          type="button"
                          onClick={() => setComentando(true)}
                          className="inline-flex w-fit cursor-pointer items-center gap-1 text-[13px] text-secondary hover:underline"
                        >
                          <PlusIcon className="size-3.5" /> Acrescentar comentário
                        </button>
                      ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <div className="grid gap-3 border-t px-6 pb-[18px] pt-3.5">
          {resumo && (
            <div className="grid gap-0.5 text-[13px] leading-normal text-foreground/85">
              <span className="text-[11px] text-muted-foreground">{resumo.rotulo}</span>
              {resumo.texto}
            </div>
          )}
          {erro && (
            <p className="flex items-center gap-2 text-sm text-red-600">
              <AlertTriangleIcon className="size-4 shrink-0" /> {erro}
            </p>
          )}
          <div className="flex flex-wrap items-center justify-end gap-2">
            {pendencia && !carregando && (
              <span className="mr-auto text-xs text-destructive">{pendencia}</span>
            )}
            <Button variant="ghost" onClick={onClose} disabled={salvando}>
              Cancelar
            </Button>
            <Button
              id="feedback-confirmar"
              onClick={confirmar}
              disabled={salvando || carregando || Boolean(pendencia)}
              // Mesmas cores dos botões do modal de detalhes. `variant="destructive"`
              // não serve — neste tema ele é âmbar, e o "Rejeitar" saía alaranjado.
              className={
                modoDecisao
                  ? rejeitando
                    ? "bg-red-600 text-white hover:bg-red-700"
                    : "bg-green-600 hover:bg-green-700"
                  : undefined
              }
            >
              {salvando && <Loader2Icon className="animate-spin" />}
              {modoDecisao
                ? rejeitando
                  ? "Rejeitar"
                  : "Aprovar"
                : existente
                  ? "Salvar alterações"
                  : "Salvar parecer"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Um dos dois botões de "A IA acertou?". */
function BotaoVeredito({
  tipo,
  ativo,
  desabilitado,
  onClick,
  titulo,
  detalhe,
}: {
  tipo: "acertou" | "errou";
  ativo: boolean;
  desabilitado?: boolean;
  onClick: () => void;
  titulo: string;
  detalhe: string;
}) {
  const Icone = tipo === "acertou" ? CheckIcon : XIcon;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={ativo}
      disabled={desabilitado}
      onClick={onClick}
      className={cn(
        "flex cursor-pointer items-center gap-3 rounded-xl border-[1.5px] border-border bg-white p-3.5 text-left transition-colors hover:border-primary/40 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border dark:bg-white/5",
        ativo && tipo === "acertou" && "border-secondary bg-secondary/10 hover:border-secondary dark:bg-secondary/15",
        ativo && tipo === "errou" && "border-destructive bg-destructive/10 hover:border-destructive dark:bg-destructive/15",
      )}
    >
      <span
        className={cn(
          "grid size-[30px] shrink-0 place-items-center rounded-full border-[1.5px] border-border text-muted-foreground transition-colors",
          ativo && tipo === "acertou" && "border-secondary bg-secondary text-white",
          ativo && tipo === "errou" && "border-destructive bg-destructive text-white",
        )}
      >
        <Icone className="size-4" strokeWidth={2.6} />
      </span>
      <span className="min-w-0">
        <span className="block text-[15px] font-semibold text-foreground">{titulo}</span>
        <span className="mt-px block text-xs text-muted-foreground">{detalhe}</span>
      </span>
      <kbd className="ml-auto hidden self-start rounded border px-1.5 font-mono text-[10px] text-muted-foreground sm:block">
        {tipo === "acertou" ? "A" : "E"}
      </kbd>
    </button>
  );
}
