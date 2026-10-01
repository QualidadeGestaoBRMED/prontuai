"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangleIcon, Loader2Icon, PlusIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { API_ENDPOINTS } from "@/lib/config";
import { authFetch } from "@/lib/auth-fetch";
import { cn } from "@/lib/utils";
import {
  CATEGORIAS_DOCUMENTO,
  CATEGORIAS_EXAME,
  OPCOES_FEEDBACK,
  STATUS_COM_DETALHES,
  comporResumo,
  type DocumentFeedback,
  type DocumentFeedbackInput,
  type FeedbackIssueItem,
  type FeedbackStatus,
} from "@/types/feedback";

export type FeedbackAlvo = {
  documentId: string;
  paciente?: string;
  cpf?: string;
  /**
   * "decisao": o diálogo veio de Aprovar/Rejeitar e a decisão AINDA NÃO foi
   * tomada — ele confirma a decisão e, de quebra, coleta o parecer.
   * "avaliacao": veio do botão "Avaliar IA" de um documento já decidido; aqui
   * só se coleta o parecer.
   */
  modo: "decisao" | "avaliacao";
  /** No modo "decisao", qual decisão está sendo confirmada. */
  decisao?: "aprovado" | "rejeitado";
  /**
   * A IA chegou a um veredito de aprovação neste documento: comparou de verdade
   * e não apontou nenhum exame faltante.
   *
   * Não basta a lista de faltantes estar vazia. Quando a IA falha antes de
   * comparar — não leu o CPF, o CNPJ veio errado, o paciente não estava no BRNET
   * — ela também fica vazia, e ali a IA não aprovou nada: não houve julgamento.
   * Medido no banco de dev entre os rejeitados sem faltantes: dos 522, 153 são
   * falha técnica e 80 são regra de negócio (expedição em aberto), todos com
   * `erro` preenchido e sem exames obrigatórios. Tratar esses como "a IA
   * aprovou" marcaria "A IA errou" em 45% dos casos sem que a IA tivesse
   * errado — e contaminaria a própria medição de acurácia que este parecer
   * alimenta.
   */
  iaAprovou?: boolean;
  /**
   * Exames que o BRNET exigia e a IA não encontrou, com o nome canônico que a
   * API devolveu (`validation_result.exames_faltantes`).
   *
   * Vem daqui, e não da `tabela_comparacao`, por dois motivos: a tabela falta em
   * 12% dos documentos, e ela mistura nome de catálogo com texto saído do OCR —
   * deixar o revisor apontar um nome de OCR sujaria justamente o dado que deve
   * alimentar o catálogo de sinônimos.
   */
  exames: string[];
};

/** O que sai do diálogo quando ele confirma uma decisão. */
export type DecisaoConfirmada = {
  /** Parecer sobre a IA, ou null quando o revisor optou por não avaliar. */
  parecer: DocumentFeedbackInput | null;
};

type Props = {
  alvo: FeedbackAlvo | null;
  onClose: () => void;
  /**
   * Só no modo "decisao". Grava a decisão e, se houver, o parecer — nesta
   * ordem, porque o back-end recusa parecer de documento sem decisão humana
   * (409). Deve lançar em caso de falha: o diálogo fica aberto com tudo
   * preenchido, para o revisor não perder o que digitou.
   */
  onConfirmarDecisao?: (dados: DecisaoConfirmada) => Promise<void>;
};

/** Exames marcados e exames digitados, por categoria. */
type Selecao = Record<string, { daLista: string[]; digitados: string[] }>;

const VAZIO = { daLista: [], digitados: [] };

// Todo exame da lista é faltante — é o único recorte que a API devolve aqui.
const VEREDITO_DA_LISTA = "faltante";

/**
 * Paleta do modal, nos tokens do sistema (app/globals.css) e nos mesmos
 * padrões das telas de catálogo e dashboard: `primary` é o azul-escuro da marca,
 * `secondary` o petróleo, e caixas/pílulas usam `primary` com transparência.
 * Centralizado aqui para as dezenas de ocorrências não voltarem a divergir —
 * antes era tudo cor crua do Tailwind (blue/amber), fora da identidade visual.
 */
const ESTILO = {
  rotulo: "text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary",
  caixa: "rounded-lg border border-primary/10 bg-primary/5 p-3",
  cartao: "border-primary/15 bg-card hover:border-primary/25 hover:bg-primary/5",
  cartaoAtivo: "border-secondary bg-secondary/10 ring-1 ring-secondary/30",
  pilula:
    "border-primary/15 bg-primary/5 text-primary/80 hover:border-primary/25 hover:bg-primary/10",
  pilulaAtiva: "border-secondary bg-secondary text-white shadow-sm",
  exame:
    "border-primary/15 bg-white/80 text-foreground hover:border-primary/25 hover:bg-primary/5",
  exameAtivo: "border-secondary bg-secondary/10 font-medium text-secondary",
  resumo: "rounded-lg border border-secondary/20 bg-secondary/5 p-3",
  // Atenção (falta preencher) no âmbar da marca; erro de verdade segue o
  // vermelho que os formulários do sistema já usam.
  pendencia: "text-destructive",
  erro: "text-red-600",
  obrigatorio: "text-red-600",
} as const;

/** Para comparar nomes de exame: sem caixa, sem acento, sem espaço sobrando. */
function normalizarNome(nome: string): string {
  return nome
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/**
 * Parecer do revisor sobre o acerto da IA.
 *
 * Portado do `FeedbackCard` da Triagem BR NET, com duas diferenças de fundo: lá
 * o parecer é obrigatório e destrava o download, aqui é **opcional** e nunca
 * bloqueia nada (a decisão já foi persistida antes deste modal abrir, em outra
 * requisição — falhar aqui não a desfaz); e aqui **todo motivo de exame aponta
 * para um exame**, porque "faltante incorreto" solto no documento não diz em
 * quê e não serve para corrigir o motor de comparação. Os erros que não são de
 * exame (nome, CPF, data, ilegibilidade) têm bloco próprio e viajam em
 * `document_issues` — um deles sozinho já é parecer válido.
 *
 * Duas portas de entrada: a decisão (aprovar/rejeitar) e o botão "Avaliar IA" de
 * um documento já decidido. Por causa da segunda, o modal **busca o parecer
 * salvo ao abrir** — sem isso, quem respondeu na hora da decisão e voltasse
 * depois sobrescreveria a própria resposta sem ver o que estava lá.
 *
 * Enquanto está aberto o cronômetro de revisão fica pausado, então o tempo de
 * preencher não entra no `review_active_ms` (ver docs/tempo-de-revisao-desenho.md).
 */
export function FeedbackChecagemDialog({ alvo, onClose, onConfirmarDecisao }: Props) {
  // O último alvo aberto, para desenhar a tela enquanto ela SOME. Quem fecha
  // zera `alvo` na hora, mas o Radix ainda anima a saída por ~200ms; sem isto,
  // nesse intervalo o título virava "Como foi o resultado da IA?", o motivo da
  // rejeição sumia e a lista de exames trocava pelo aviso de lista vazia — tudo
  // visível no fade (medido: aos 60ms o título já tinha trocado).
  const ultimoAlvo = useRef<FeedbackAlvo | null>(alvo);
  if (alvo) ultimoAlvo.current = alvo;
  const vis = alvo ?? ultimoAlvo.current;

  const [status, setStatus] = useState<FeedbackStatus | "">("");
  const [categorias, setCategorias] = useState<string[]>([]);
  const [selecao, setSelecao] = useState<Selecao>({});
  const [rascunhos, setRascunhos] = useState<Record<string, string>>({});
  const [problemasDoc, setProblemasDoc] = useState<string[]>([]);
  const [notas, setNotas] = useState("");
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
    setStatus("");
    setCategorias([]);
    setSelecao({});
    setRascunhos({});
    setProblemasDoc([]);
    setNotas("");
    setErro(null);
    setExistente(null);
    // Rejeitar algo que a IA tinha aprovado já é, em si, a afirmação de que a
    // IA errou — o revisor não deveria ter de dizer de novo. A sugestão é só
    // isto: fica marcada e o revisor troca à vontade, inclusive para "acertou
    // com ressalvas", que é o caso em que a rejeição veio de outro motivo.
    if (alvo.modo === "decisao" && alvo.decisao === "rejeitado" && alvo.iaAprovou) {
      setStatus("IA_INCORRETA");
    }
    // No modo "decisao" o documento ainda nem foi decidido: não existe parecer
    // anterior para buscar, e o GET só atrasaria a abertura.
    if (alvo.modo === "decisao") return;
    setCarregando(true);
    authFetch(API_ENDPOINTS.DOCUMENT_FEEDBACK(alvo.documentId))
      .then((r) => (r.ok ? r.json() : null))
      .then((salvo: DocumentFeedback | null) => {
        if (!vivo || !salvo) return;
        setExistente(salvo);
        setStatus(salvo.status);
        // Remonta a tela a partir dos pares gravados: categorias na ordem em que
        // aparecem, e cada exame de volta na coluna certa (marcado da lista ou
        // digitado à mão).
        const doBanco: Selecao = {};
        for (const item of salvo.issue_items ?? []) {
          const atual = doBanco[item.categoria] ?? { daLista: [], digitados: [] };
          if (item.fora_da_lista) atual.digitados = [...atual.digitados, item.exame];
          else atual.daLista = [...atual.daLista, item.exame];
          doBanco[item.categoria] = atual;
        }
        const docs = salvo.document_issues ?? [];
        setCategorias(Object.keys(doBanco));
        setSelecao(doBanco);
        setProblemasDoc(docs);
        // `notes` foi gravado como resumo automático + detalhe manual. Refaz o
        // resumo a partir dos pares e devolve ao campo só o que sobrar — senão,
        // ao salvar de novo, o resumo entraria duplicado.
        const resumoSalvo = comporResumo(
          Object.entries(doBanco).map(([categoria, v]) => ({
            categoria,
            nomes: [...v.daLista, ...v.digitados],
          })),
          docs,
        ).join("\n");
        const gravado = salvo.notes ?? "";
        setNotas(
          resumoSalvo && gravado.startsWith(resumoSalvo)
            ? gravado.slice(resumoSalvo.length).trim()
            : gravado,
        );
      })
      .catch(() => undefined)
      .finally(() => {
        if (vivo) setCarregando(false);
      });
    return () => {
      vivo = false;
    };
  }, [alvo]);

  const exames = useMemo(
    () => [...(vis?.exames ?? [])].sort((a, b) => a.localeCompare(b, "pt-BR")),
    [vis],
  );

  // Trocar de status NÃO apaga o que foi marcado: os três cartões ficam lado a
  // lado, e um clique errado em "A IA acertou" levava motivos, exames e texto
  // embora sem volta. Os detalhes só ficam escondidos — e não são enviados,
  // porque `montarParecer` só os inclui quando o status pede detalhamento.
  //
  // Clicar no cartão já marcado DESMARCA. Sem isso não há saída: escolher um
  // status que pede detalhamento trava o botão de enviar até detalhar, e o
  // parecer é opcional. Passou a importar quando a rejeição de algo aprovado
  // pela IA começou a vir com "A IA errou" já marcado — o revisor que só quer
  // rejeitar precisa conseguir limpar a sugestão.
  function selecionarStatus(valor: FeedbackStatus) {
    setStatus((atual) => (atual === valor ? "" : valor));
    setErro(null);
  }

  function alternarCategoria(valor: string) {
    setErro(null);
    setCategorias((atuais) => {
      if (!atuais.includes(valor)) return [...atuais, valor];
      // Desmarcar o motivo leva junto os exames dele: deixar seleção órfã de um
      // chip apagado mandaria para o servidor item que a tela não mostra mais.
      setSelecao((atual) => {
        const copia = { ...atual };
        delete copia[valor];
        return copia;
      });
      setRascunhos((atual) => {
        const copia = { ...atual };
        delete copia[valor];
        return copia;
      });
      return atuais.filter((x) => x !== valor);
    });
  }

  function alternarProblemaDoc(valor: string) {
    setErro(null);
    setProblemasDoc((atuais) =>
      atuais.includes(valor) ? atuais.filter((x) => x !== valor) : [...atuais, valor],
    );
  }

  function alternarExame(categoria: string, exame: string) {
    setErro(null);
    setSelecao((atual) => {
      const item = atual[categoria] ?? VAZIO;
      const daLista = item.daLista.includes(exame)
        ? item.daLista.filter((x) => x !== exame)
        : [...item.daLista, exame];
      return { ...atual, [categoria]: { ...item, daLista } };
    });
  }

  function adicionarDigitado(categoria: string) {
    const nome = (rascunhos[categoria] ?? "").trim();
    if (!nome) return;
    setErro(null);
    // Digitou um exame que está na lista do BRNET, só que em outra caixa ou sem
    // acento? Marca o chip da lista, com o nome canônico. Sem isto ele entrava
    // como `fora_da_lista`, com nome fora do padrão e marcado para curadoria, e
    // se o revisor também clicasse no chip o resumo saía "SUMÁRIO DE URINA (EAS)
    // e sumário de urina (eas) estavam..." — com o back gravando um item só.
    const daLista = exames.find((e) => normalizarNome(e) === normalizarNome(nome));
    setSelecao((atual) => {
      const item = atual[categoria] ?? VAZIO;
      if (daLista) {
        if (item.daLista.includes(daLista)) return atual;
        return { ...atual, [categoria]: { ...item, daLista: [...item.daLista, daLista] } };
      }
      const jaTem = [...item.daLista, ...item.digitados].some(
        (x) => normalizarNome(x) === normalizarNome(nome),
      );
      if (jaTem) return atual;
      return { ...atual, [categoria]: { ...item, digitados: [...item.digitados, nome] } };
    });
    setRascunhos((atual) => ({ ...atual, [categoria]: "" }));
  }

  function removerDigitado(categoria: string, nome: string) {
    setSelecao((atual) => {
      const item = atual[categoria] ?? VAZIO;
      return {
        ...atual,
        [categoria]: { ...item, digitados: item.digitados.filter((x) => x !== nome) },
      };
    });
  }

  const itens: FeedbackIssueItem[] = useMemo(() => {
    return categorias.flatMap((categoria) => {
      const item = selecao[categoria] ?? VAZIO;
      return [
        ...item.daLista.map((exame) => ({
          categoria,
          exame,
          veredito_ia: VEREDITO_DA_LISTA,
          fora_da_lista: false,
        })),
        ...item.digitados.map((exame) => ({
          categoria,
          exame,
          veredito_ia: null,
          fora_da_lista: true,
        })),
      ];
    });
  }, [categorias, selecao]);

  const precisaDetalhes = Boolean(status) && STATUS_COM_DETALHES.includes(status as FeedbackStatus);
  // Todo motivo marcado precisa de pelo menos um exame: um chip aceso e vazio
  // seria exatamente o parecer solto que este formulário existe para evitar.
  const semExame = categorias.filter(
    (c) => !itens.some((i) => i.categoria === c),
  );
  // Um problema de documento sozinho já basta: nome corrompido é erro real da IA
  // e não tem exame a que amarrar.
  const apontouAlgo = itens.length > 0 || problemasDoc.length > 0;
  /**
   * O "o que aconteceu" que o modal escreve sozinho. Por isso a descrição deixou
   * de ser obrigatória: o par motivo↔exame já diz o quê e onde, e a frase diz
   * isso por extenso. O revisor só escreve quando quer acrescentar algo — ou
   * quando marcou "Outro", que não tem frase pronta.
   */
  const resumo = useMemo(
    () =>
      comporResumo(
        categorias.map((categoria) => {
          const item = selecao[categoria] ?? VAZIO;
          return { categoria, nomes: [...item.daLista, ...item.digitados] };
        }),
        problemasDoc,
      ),
    [categorias, selecao, problemasDoc],
  );
  const pediuOutro = categorias.includes("OUTRO");
  const detalheObrigatorio = pediuOutro || (apontouAlgo && resumo.length === 0);
  const textoFinal = [resumo.join("\n"), notas.trim()].filter(Boolean).join("\n\n");

  const parecerValido = Boolean(
    status &&
      (!precisaDetalhes ||
        (apontouAlgo &&
          semExame.length === 0 &&
          (!detalheObrigatorio || notas.trim().length > 0))),
  );

  const modoDecisao = vis?.modo === "decisao";
  const rejeitando = vis?.decisao === "rejeitado";
  // Rejeitar não pede mais texto livre: o campo "Motivo da rejeição" saiu, e o
  // que há para dizer sobre o acerto da IA vai no parecer estruturado abaixo.
  // No modo decisão o parecer é opcional: sem status escolhido, aprova/rejeita
  // e pronto. Mas começar a preencher e parar no meio não passa — seria enviar
  // motivo sem exame, que é o que o formato existe para impedir.
  const parecerPendente = modoDecisao ? Boolean(status) && !parecerValido : !parecerValido;
  const podeEnviar = modoDecisao ? !parecerPendente : parecerValido;
  const formularioValido = podeEnviar;

  /**
   * O que falta para poder enviar, na ordem em que aparece no formulário.
   *
   * Existe porque o botão desabilitado não explica nada: no teste em tela, um
   * motivo aceso sem exame escolhido deixava o revisor diante de um botão cinza
   * e um rodapé dizendo "leva menos de um minuto", sem pista do que fazer. A
   * mensagem de `enviar()` nunca aparecia — botão desabilitado não dispara
   * clique.
   */
  const pendencia = (() => {
    if (!precisaDetalhes || parecerValido) return null;
    // O motivo aceso e vazio vem ANTES do "marque o que a IA errou": com um chip
    // aceso, o revisor já marcou — pedir que marque de novo mandaria ele olhar
    // para o lugar errado da tela.
    if (semExame.length > 0) {
      const rotulos = semExame
        .map((c) => CATEGORIAS_EXAME.find((x) => x.valor === c)?.rotulo ?? c)
        .join(", ");
      // Sem faltante do BRNET não há o que escolher: o único caminho é digitar.
      const verbo = exames.length === 0 ? "Informe" : "Escolha";
      return `${verbo} ao menos um exame para: ${rotulos}.`;
    }
    if (!apontouAlgo) return "Marque o que a IA errou — em algum exame ou no documento.";
    return pediuOutro ? "Conte o que houve em “Outro”." : "Descreva o que aconteceu.";
  })();

  function montarParecer(): DocumentFeedbackInput | null {
    if (!status) return null;
    return {
      status,
      issue_items: precisaDetalhes ? itens : [],
      document_issues: precisaDetalhes ? problemasDoc : [],
      notes: precisaDetalhes ? textoFinal || null : null,
    };
  }

  async function confirmarDecisao() {
    if (!alvo || !onConfirmarDecisao || !podeEnviar) return;
    setSalvando(true);
    setErro(null);
    try {
      // Não chama onClose(): depois de decidir, quem fecha (e fecha também o
      // modal de detalhes atrás) é a página. Fechar por aqui passaria pelo
      // caminho de cancelamento, que religa o cronômetro de revisão e deixaria
      // um acumulador órfão tiquetaqueando num documento já decidido.
      await onConfirmarDecisao({
        parecer: montarParecer(),
      });
    } catch (e) {
      // A página não gravou: o diálogo fica aberto com tudo preenchido.
      setErro(e instanceof Error ? e.message : String(e));
    } finally {
      setSalvando(false);
    }
  }

  async function enviar() {
    if (!alvo || !status || !formularioValido) {
      setErro(
        semExame.length > 0
          ? `Escolha ao menos um exame para: ${semExame
              .map((c) => CATEGORIAS_EXAME.find((x) => x.valor === c)?.rotulo ?? c)
              .join(", ")}.`
          : precisaDetalhes
            ? "Marque o que a IA errou, em quais exames, e descreva o que aconteceu."
            : "Selecione como foi o resultado da IA.",
      );
      return;
    }
    const corpo: DocumentFeedbackInput = {
      status,
      issue_items: precisaDetalhes ? itens : [],
      document_issues: precisaDetalhes ? problemasDoc : [],
      notes: precisaDetalhes ? textoFinal || null : null,
    };
    setSalvando(true);
    setErro(null);
    try {
      const resposta = await authFetch(API_ENDPOINTS.DOCUMENT_FEEDBACK(alvo.documentId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      if (!resposta.ok) {
        const dados = await resposta.json().catch(() => null);
        throw new Error(dados?.detail ?? `Falha ao salvar o parecer (HTTP ${resposta.status}).`);
      }
      // Sem isto o modal só sumia e o revisor não tinha como saber se gravou.
      toast.success(existente ? "Parecer atualizado." : "Obrigado pelo parecer!");
      onClose();
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e));
    } finally {
      setSalvando(false);
    }
  }

  return (
    // ESC e clique fora também são bloqueados durante o envio: fechar no meio do
    // PUT deixaria o revisor sem saber se o parecer foi gravado.
    <Dialog open={!!alvo} onOpenChange={(aberto) => !aberto && !salvando && onClose()}>
      {/* Ancorado no topo, e não centralizado: centralizado, o diálogo cresce para
          os dois lados a cada chip marcado e o próximo alvo foge do cursor
          (medido: 56px de salto depois de um único clique). */}
      <DialogContent className="top-[4vh] max-h-[92vh] translate-y-0 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {modoDecisao
              ? rejeitando
                ? "Rejeitar documento"
                : "Aprovar documento"
              : "Como foi o resultado da IA?"}
          </DialogTitle>
          <DialogDescription>
            {modoDecisao ? (
              <>
                {rejeitando ? "Rejeitando" : "Aprovando"} o documento
                {vis?.paciente ? (
                  <>
                    {" de "}
                    <strong>{vis.paciente}</strong>
                  </>
                ) : null}
                {vis?.cpf ? ` (CPF: ${vis.cpf})` : ""}.
              </>
            ) : (
              <>
                Documento
                {vis?.paciente ? (
                  <>
                    {" de "}
                    <strong>{vis.paciente}</strong>
                  </>
                ) : null}
                . Esta resposta é opcional e não muda a decisão registrada — ela
                alimenta a medição de acurácia e a correção do motor de comparação.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        {modoDecisao && (
          <div className="border-t pt-3">
            <p className="text-sm font-medium text-foreground">
              Como foi o resultado da IA?{" "}
              <span className="font-normal text-muted-foreground">— opcional</span>
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Não muda a decisão acima. Alimenta a medição de acurácia e a correção do
              motor de comparação.
            </p>
          </div>
        )}

        {carregando && (
          <p className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" /> Carregando parecer…
          </p>
        )}

        <div className="grid gap-2 sm:grid-cols-3">
          {OPCOES_FEEDBACK.map((opcao) => (
            <button
              key={opcao.valor}
              type="button"
              onClick={() => selecionarStatus(opcao.valor)}
              className={cn(
                "cursor-pointer rounded-lg border px-4 py-3 text-left transition-colors",
                status === opcao.valor
                  ? ESTILO.cartaoAtivo
                  : ESTILO.cartao,
              )}
            >
              <span className="block text-sm font-medium text-foreground">{opcao.titulo}</span>
              <span className="mt-1 block text-xs leading-4 text-muted-foreground">
                {opcao.descricao}
              </span>
            </button>
          ))}
        </div>

        {precisaDetalhes && (
          <div className="grid max-h-[46vh] gap-4 overflow-y-auto pr-1">
            <div>
              <p className={ESTILO.rotulo}>
                Em quais exames?
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {CATEGORIAS_EXAME.map(({ valor, rotulo, ajuda }) => (
                  <button
                    key={valor}
                    type="button"
                    title={ajuda}
                    onClick={() => alternarCategoria(valor)}
                    className={cn(
                      "cursor-pointer rounded-full border px-3 py-1.5 text-xs transition-colors",
                      categorias.includes(valor)
                        ? ESTILO.pilulaAtiva
                        : ESTILO.pilula,
                    )}
                  >
                    {rotulo}
                  </button>
                ))}
              </div>
            </div>

            {categorias.map((categoria) => {
              const meta = CATEGORIAS_EXAME.find((c) => c.valor === categoria);
              const item = selecao[categoria] ?? VAZIO;
              const semLista = exames.length === 0;
              return (
                <div key={categoria} className={ESTILO.caixa}>
                  <p className="text-sm font-medium text-foreground">
                    {meta?.rotulo ?? categoria}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      {semLista ? "— digite o exame" : "— em quais exames?"}
                    </span>
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{meta?.ajuda}</p>

                  {semLista ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      O BRNET não apontou exame faltante neste documento — digite o nome
                      abaixo.
                    </p>
                  ) : (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {exames.map((nome) => (
                        <button
                          key={nome}
                          type="button"
                          onClick={() => alternarExame(categoria, nome)}
                          className={cn(
                            "cursor-pointer rounded-md border px-2 py-1 text-xs transition-colors",
                            item.daLista.includes(nome)
                              ? ESTILO.exameAtivo
                              : ESTILO.exame,
                          )}
                        >
                          {nome}
                        </button>
                      ))}
                    </div>
                  )}

                  {item.digitados.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {item.digitados.map((nome) => (
                        <span
                          key={nome}
                          className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs", ESTILO.exameAtivo)}
                        >
                          {nome}
                          <button
                            type="button"
                            aria-label={`Remover ${nome}`}
                            onClick={() => removerDigitado(categoria, nome)}
                            className="cursor-pointer opacity-60 hover:opacity-100"
                          >
                            <XIcon className="size-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="mt-2 flex gap-2">
                    <Input
                      value={rascunhos[categoria] ?? ""}
                      onChange={(ev) =>
                        setRascunhos((atual) => ({ ...atual, [categoria]: ev.target.value }))
                      }
                      onKeyDown={(ev) => {
                        if (ev.key !== "Enter") return;
                        // Enter aqui não pode submeter nem fechar o modal.
                        ev.preventDefault();
                        adicionarDigitado(categoria);
                      }}
                      maxLength={300}
                      placeholder={
                        semLista
                          ? "Nome do exame como está no documento"
                          : "Outro exame, fora da lista acima"
                      }
                      className="h-8 text-xs"
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 shrink-0"
                      onClick={() => adicionarDigitado(categoria)}
                      disabled={!(rascunhos[categoria] ?? "").trim()}
                    >
                      <PlusIcon className="size-3.5" />
                      Incluir
                    </Button>
                  </div>
                </div>
              );
            })}

            <div>
              <p className={ESTILO.rotulo}>
                Problemas do documento
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Erros que não são de exame — não precisam apontar nada na lista acima.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {CATEGORIAS_DOCUMENTO.map(({ valor, rotulo, ajuda }) => (
                  <button
                    key={valor}
                    type="button"
                    title={ajuda}
                    onClick={() => alternarProblemaDoc(valor)}
                    className={cn(
                      "cursor-pointer rounded-full border px-3 py-1.5 text-xs transition-colors",
                      problemasDoc.includes(valor)
                        ? ESTILO.pilulaAtiva
                        : ESTILO.pilula,
                    )}
                  >
                    {rotulo}
                  </button>
                ))}
              </div>
            </div>

            {resumo.length > 0 && (
              <div className={ESTILO.resumo}>
                <p className={ESTILO.rotulo}>
                  O que aconteceu
                </p>
                <ul className="mt-1.5 space-y-1 text-sm text-foreground">
                  {resumo.map((frase) => (
                    <li key={frase}>{frase}</li>
                  ))}
                </ul>
              </div>
            )}

            <label className="block">
              <span className={ESTILO.rotulo}>
                {detalheObrigatorio ? (
                  <>
                    {pediuOutro ? "Conte o que houve em “Outro”" : "Conte o que aconteceu"}{" "}
                    <span className={ESTILO.obrigatorio}>*</span>
                  </>
                ) : (
                  <>
                    Quer acrescentar algo?{" "}
                    <span className="font-normal normal-case tracking-normal">— opcional</span>
                  </>
                )}
              </span>
              <Textarea
                value={notas}
                onChange={(e) => {
                  setNotas(e.target.value);
                  setErro(null);
                }}
                rows={2}
                maxLength={5000}
                placeholder={
                  pediuOutro
                    ? "Ex.: o exame veio com o resultado de outro paciente."
                    : "Ex.: estava na página 2, com o nome abreviado."
                }
                className="mt-2"
              />
            </label>
          </div>
        )}

        {erro && (
          <p className={cn("flex items-center gap-2 text-sm", ESTILO.erro)}>
            <AlertTriangleIcon className="size-4 shrink-0" /> {erro}
          </p>
        )}

        <DialogFooter className="sm:justify-between">
          <p
            className={cn(
              "text-xs",
              pendencia ? ESTILO.pendencia : "text-muted-foreground",
            )}
          >
            {pendencia
              ? pendencia
              : precisaDetalhes && apontouAlgo
              ? [
                  itens.length > 0 &&
                    `${itens.length} ${itens.length === 1 ? "exame" : "exames"}`,
                  problemasDoc.length > 0 &&
                    `${problemasDoc.length} no documento`,
                ]
                  .filter(Boolean)
                  .join(" · ")
              : existente
                ? `Já avaliado por ${existente.reviewed_by_email ?? "outro revisor"}.`
                : modoDecisao
                  ? "Pode seguir sem avaliar: o parecer é opcional."
                  : "Responder leva menos de um minuto — e é opcional."}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose} disabled={salvando}>
              {modoDecisao ? "Cancelar" : "Agora não"}
            </Button>
            <Button
              onClick={modoDecisao ? confirmarDecisao : enviar}
              disabled={salvando || carregando || !podeEnviar}
              // Mesmas cores dos botões que este diálogo substituiu: verde no
              // "Aprovar" do modal de detalhes, vermelho na confirmação de
              // rejeição. `variant="destructive"` não serve — neste tema ele é
              // âmbar (#CC851E), e o "Rejeitar" saía alaranjado.
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
                ? status
                  ? rejeitando
                    ? "Rejeitar e enviar parecer"
                    : "Aprovar e enviar parecer"
                  : rejeitando
                    ? "Rejeitar"
                    : "Aprovar"
                : existente
                  ? "Salvar alterações"
                  : "Enviar parecer"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
