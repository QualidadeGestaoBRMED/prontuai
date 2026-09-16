"use client";

import { useEffect, useMemo, useState } from "react";
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
import type { TabelaComparacaoItem } from "@/types/process";
import {
  CATEGORIAS_DOCUMENTO,
  CATEGORIAS_EXAME,
  OPCOES_FEEDBACK,
  ROTULO_VEREDITO,
  STATUS_COM_DETALHES,
  type DocumentFeedback,
  type DocumentFeedbackInput,
  type FeedbackIssueItem,
  type FeedbackStatus,
} from "@/types/feedback";

export type FeedbackAlvo = {
  documentId: string;
  paciente?: string;
  /**
   * Preenchida quando o modal veio logo depois da decisão. Indefinida quando
   * veio do botão "Avaliar IA" de um documento já decidido — nesse caso a
   * decisão pode ser antiga, e de outra pessoa, então não se fala dela.
   */
  decisao?: "aprovado" | "rejeitado";
  /** Tabela de comparação do documento — a mesma que o revisor acabou de conferir. */
  exames: TabelaComparacaoItem[];
};

type Props = {
  alvo: FeedbackAlvo | null;
  onClose: () => void;
};

/** Exames marcados e exames digitados, por categoria. */
type Selecao = Record<string, { daLista: string[]; digitados: string[] }>;

const VAZIO = { daLista: [], digitados: [] };

// Problemas primeiro: faltante e extra são o que o revisor veio contestar.
const ORDEM_VEREDITO: Record<string, number> = {
  faltante: 0,
  extra_no_ocr: 1,
  parcialmente_encontrado: 2,
  encontrado: 3,
};

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
 * Abre depois de `reviewTimer.encerrar()`, então o tempo gasto respondendo não
 * entra na métrica de tempo de revisão (ver docs/tempo-de-revisao-desenho.md).
 */
export function FeedbackChecagemDialog({ alvo, onClose }: Props) {
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
        setCategorias(Object.keys(doBanco));
        setSelecao(doBanco);
        setProblemasDoc(salvo.document_issues ?? []);
        setNotas(salvo.notes ?? "");
      })
      .catch(() => undefined)
      .finally(() => {
        if (vivo) setCarregando(false);
      });
    return () => {
      vivo = false;
    };
  }, [alvo]);

  const exames = useMemo(() => {
    const tabela = alvo?.exames ?? [];
    return [...tabela].sort(
      (a, b) =>
        (ORDEM_VEREDITO[a.status] ?? 9) - (ORDEM_VEREDITO[b.status] ?? 9) ||
        a.exame.localeCompare(b.exame, "pt-BR"),
    );
  }, [alvo]);

  function selecionarStatus(valor: FeedbackStatus) {
    setStatus(valor);
    setErro(null);
    if (!STATUS_COM_DETALHES.includes(valor)) {
      setCategorias([]);
      setSelecao({});
      setRascunhos({});
      setProblemasDoc([]);
      setNotas("");
    }
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
    setSelecao((atual) => {
      const item = atual[categoria] ?? VAZIO;
      const jaTem = [...item.daLista, ...item.digitados].some(
        (x) => x.toLocaleLowerCase("pt-BR") === nome.toLocaleLowerCase("pt-BR"),
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
    const veredito = new Map(exames.map((e) => [e.exame, e.status]));
    return categorias.flatMap((categoria) => {
      const item = selecao[categoria] ?? VAZIO;
      return [
        ...item.daLista.map((exame) => ({
          categoria,
          exame,
          veredito_ia: veredito.get(exame) ?? null,
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
  }, [categorias, selecao, exames]);

  const precisaDetalhes = Boolean(status) && STATUS_COM_DETALHES.includes(status as FeedbackStatus);
  // Todo motivo marcado precisa de pelo menos um exame: um chip aceso e vazio
  // seria exatamente o parecer solto que este formulário existe para evitar.
  const semExame = categorias.filter(
    (c) => !itens.some((i) => i.categoria === c),
  );
  // Um problema de documento sozinho já basta: nome corrompido é erro real da IA
  // e não tem exame a que amarrar.
  const apontouAlgo = itens.length > 0 || problemasDoc.length > 0;
  const formularioValido = Boolean(
    status &&
      (!precisaDetalhes ||
        (apontouAlgo && semExame.length === 0 && notas.trim().length > 0)),
  );

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
    if (!precisaDetalhes || formularioValido) return null;
    // O motivo aceso e vazio vem ANTES do "marque o que a IA errou": com um chip
    // aceso, o revisor já marcou — pedir que marque de novo mandaria ele olhar
    // para o lugar errado da tela.
    if (semExame.length > 0) {
      const rotulos = semExame
        .map((c) => CATEGORIAS_EXAME.find((x) => x.valor === c)?.rotulo ?? c)
        .join(", ");
      return `Escolha ao menos um exame para: ${rotulos}.`;
    }
    if (!apontouAlgo) return "Marque o que a IA errou — em algum exame ou no documento.";
    return "Descreva o que aconteceu.";
  })();

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
      notes: precisaDetalhes ? notas.trim() : null,
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
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Como foi o resultado da IA?</DialogTitle>
          <DialogDescription>
            Documento
            {alvo?.paciente ? (
              <>
                {" de "}
                <strong>{alvo.paciente}</strong>
              </>
            ) : null}
            {alvo?.decisao ? ` ${alvo.decisao}.` : "."} Esta resposta é opcional e não
            muda a decisão registrada — ela alimenta a medição de acurácia e a correção
            do motor de comparação.
          </DialogDescription>
        </DialogHeader>

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
                "cursor-pointer rounded-md border px-4 py-3 text-left transition-colors",
                status === opcao.valor
                  ? "border-blue-500 bg-blue-50 ring-1 ring-blue-200"
                  : "hover:border-muted-foreground/40 hover:bg-muted/50",
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
              <p className="text-xs font-semibold uppercase tracking-[.08em] text-muted-foreground">
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
                        ? "border-amber-500 bg-amber-50 text-amber-900"
                        : "text-muted-foreground hover:bg-muted/50",
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
              const soDigitado = meta?.soDigitado || exames.length === 0;
              return (
                <div key={categoria} className="rounded-md border bg-muted/30 p-3">
                  <p className="text-sm font-medium text-foreground">
                    {meta?.rotulo ?? categoria}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      {soDigitado ? "— digite o exame" : "— em quais exames?"}
                    </span>
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{meta?.ajuda}</p>

                  {!soDigitado && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {exames.map((e) => (
                        <button
                          key={e.exame}
                          type="button"
                          onClick={() => alternarExame(categoria, e.exame)}
                          className={cn(
                            "cursor-pointer rounded-md border px-2 py-1 text-xs transition-colors",
                            item.daLista.includes(e.exame)
                              ? "border-blue-500 bg-blue-50 text-blue-900"
                              : "bg-background hover:bg-muted",
                          )}
                        >
                          {e.exame}
                          <span className="ml-1.5 text-[10px] text-muted-foreground">
                            {ROTULO_VEREDITO[e.status] ?? e.status}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}

                  {item.digitados.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {item.digitados.map((nome) => (
                        <span
                          key={nome}
                          className="inline-flex items-center gap-1 rounded-md border border-blue-500 bg-blue-50 px-2 py-1 text-xs text-blue-900"
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
                        soDigitado
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
              <p className="text-xs font-semibold uppercase tracking-[.08em] text-muted-foreground">
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
                        ? "border-amber-500 bg-amber-50 text-amber-900"
                        : "text-muted-foreground hover:bg-muted/50",
                    )}
                  >
                    {rotulo}
                  </button>
                ))}
              </div>
            </div>

            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-[.08em] text-muted-foreground">
                Conte o que aconteceu <span className="text-red-600">*</span>
              </span>
              <Textarea
                value={notas}
                onChange={(e) => {
                  setNotas(e.target.value);
                  setErro(null);
                }}
                rows={3}
                maxLength={5000}
                placeholder="Ex.: a audiometria estava na página 2, com o nome abreviado."
                className="mt-2"
              />
            </label>
          </div>
        )}

        {erro && (
          <p className="flex items-center gap-2 text-sm text-red-700">
            <AlertTriangleIcon className="size-4 shrink-0" /> {erro}
          </p>
        )}

        <DialogFooter className="sm:justify-between">
          <p
            className={cn(
              "text-xs",
              pendencia ? "text-amber-700" : "text-muted-foreground",
            )}
          >
            {pendencia
              ? pendencia
              : apontouAlgo
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
                : "Responder leva menos de um minuto — e é opcional."}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose} disabled={salvando}>
              Agora não
            </Button>
            <Button onClick={enviar} disabled={salvando || carregando || !formularioValido}>
              {salvando && <Loader2Icon className="animate-spin" />}
              {existente ? "Salvar alterações" : "Enviar parecer"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
