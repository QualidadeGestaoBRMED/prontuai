"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { AppSidebar } from "@/components/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { RequireRole } from "@/components/require-role";
import UserDropdown from "@/components/user-dropdown";
import { API_ENDPOINTS } from "@/lib/config";
import { authFetch } from "@/lib/auth-fetch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { Info, Loader2, ClipboardList } from "lucide-react";
import { toast } from "sonner";

type ValidationItem = {
  id: string;
  filename: string;
  cpf?: string | null;
  status?: string | null;
  uploadedAt?: string | null;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  confidenceScore?: number | null;
  analysis?: string | null;
  approvalReason?: string | null;
  rejectionReason?: string | null;
};

/** Uma linha de `GET /v1/documents/revisoes`. */
type RevisaoApi = {
  id: string;
  filename: string;
  cpf?: string | null;
  validation_status?: string | null;
  uploaded_at?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  confidence_score?: number | null;
  analysis?: string | null;
  approval_reason?: string | null;
  rejection_reason?: string | null;
};

type PaginaRevisoes = {
  items: RevisaoApi[];
  page: number;
  total_items: number;
  total_pages: number;
};

const ITENS_POR_PAGINA = 20;

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("pt-BR");
}

function statusBadge(status?: string | null) {
  if (!status) return <span className="text-muted-foreground">-</span>;
  if (status === "validated") {
    return <Badge className="bg-emerald-500 text-white border-transparent">Aprovado</Badge>;
  }
  if (status === "rejected") {
    return <Badge className="bg-rose-500 text-white border-transparent">Rejeitado</Badge>;
  }
  return <Badge variant="secondary">Pendente</Badge>;
}

// Espelho de JUSTIFICATIVAS_VAZIAS em back-end/app/models/document.py, que
// aplica a mesma lista no filtro "Somente com justificativas" —
// `test_justificativas_vazias_batem_com_as_da_tela` compara as duas.
function normalizeReason(value?: string | null) {
  if (!value) return "";
  const trimmed = value.trim();
  if (!trimmed) return "";
  const lower = trimmed.toLowerCase();
  const ignored = new Set([
    "null",
    "none",
    "undefined",
    "n/a",
    "na",
    "-",
    "sem justificativa",
    "sem justificativas",
    "sem motivo",
    "sem observacao",
    "sem observação",
  ]);
  return ignored.has(lower) ? "" : trimmed;
}

export default function ValidacoesPage() {
  const { data: session } = useSession();
  const [items, setItems] = useState<ValidationItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [loading, setLoading] = useState(true);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [selected, setSelected] = useState<ValidationItem | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const [cpfFilter, setCpfFilter] = useState("");
  const [reviewerFilter, setReviewerFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [textFilter, setTextFilter] = useState("");
  const [onlyWithJustification, setOnlyWithJustification] = useState(false);

  // Filtro novo volta para a primeira página: a página 30 de "todos" não
  // existe em "rejeitados". A volta acontece junto com a troca do filtro, no
  // mesmo render — num efeito à parte, a tela consultava antes a página antiga
  // já filtrada, só para descartar a resposta.

  // Os campos de texto filtram 400ms depois da última tecla: cada mudança é uma
  // consulta ao banco, e a busca na mensagem da IA leva alguns segundos.
  const [filtrosAplicados, setFiltrosAplicados] = useState({ cpf: "", revisor: "", texto: "" });
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const novo = { cpf: cpfFilter.trim(), revisor: reviewerFilter.trim(), texto: textFilter.trim() };
      const atual = filtrosAplicados;
      // Mesmo valor, nada a fazer: senão abrir a tela já consultava duas vezes.
      if (atual.cpf === novo.cpf && atual.revisor === novo.revisor && atual.texto === novo.texto) return;
      setFiltrosAplicados(novo);
      setPage(1);
    }, 400);
    return () => window.clearTimeout(timeout);
  }, [cpfFilter, reviewerFilter, textFilter, filtrosAplicados]);

  const trocarStatus = (valor: string) => {
    setStatusFilter(valor);
    setPage(1);
  };
  const trocarSoComJustificativa = (valor: boolean) => {
    setOnlyWithJustification(valor);
    setPage(1);
  };

  // Resposta de uma consulta antiga não pode sobrescrever a da mais nova.
  const abortRef = useRef<AbortController | null>(null);

  /**
   * A página vem pronta do servidor, do envio mais recente para o mais antigo.
   * Antes a tela baixava todos os documentos (~69 MB) e filtrava aqui — e, sem
   * ordenação na consulta, a lista terminava num documento de 24/09.
   */
  const fetchDocuments = useCallback(async () => {
    if (!session?.user?.email) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const url = new URL(API_ENDPOINTS.DOCUMENTS_REVISOES, window.location.origin);
      url.searchParams.set("page", String(page));
      url.searchParams.set("page_size", String(ITENS_POR_PAGINA));
      if (filtrosAplicados.cpf) url.searchParams.set("cpf", filtrosAplicados.cpf);
      if (filtrosAplicados.revisor) url.searchParams.set("revisor", filtrosAplicados.revisor);
      if (filtrosAplicados.texto) url.searchParams.set("texto", filtrosAplicados.texto);
      if (statusFilter !== "all") url.searchParams.set("status_filter", statusFilter);
      if (onlyWithJustification) url.searchParams.set("so_com_justificativa", "true");

      const response = await authFetch(url.toString(), { cache: "no-store", signal: controller.signal });
      if (!response.ok) {
        throw new Error("Erro ao carregar documentos");
      }
      const data = (await response.json()) as PaginaRevisoes;
      setItems(
        data.items.map((doc) => ({
          id: doc.id,
          filename: doc.filename,
          cpf: doc.cpf,
          status: doc.validation_status,
          uploadedAt: doc.uploaded_at ?? null,
          reviewedBy: doc.reviewed_by ?? null,
          reviewedAt: doc.reviewed_at ?? null,
          confidenceScore: doc.confidence_score ?? null,
          analysis: doc.analysis ?? null,
          approvalReason: normalizeReason(doc.approval_reason),
          rejectionReason: normalizeReason(doc.rejection_reason),
        })),
      );
      setTotalPages(data.total_pages || 1);
      setTotalItems(data.total_items || 0);
      // O servidor devolve a última página que existe se a pedida passou do fim.
      if (data.page && data.page !== page) setPage(data.page);
      setLastUpdatedAt(new Date());
    } catch (error) {
      if (controller.signal.aborted) return;
      console.error("Erro:", error);
      toast.error("Erro ao carregar revisões");
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }, [session?.user?.email, page, filtrosAplicados, statusFilter, onlyWithJustification]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const highlightLiberacao = (text?: string | null) => {
    if (!text) return null;
    const phrase = "Liberação concedida";
    const lower = text.toLowerCase();
    const idx = lower.indexOf(phrase.toLowerCase());
    if (idx === -1) return text;
    const before = text.slice(0, idx);
    const match = text.slice(idx, idx + phrase.length);
    const after = text.slice(idx + phrase.length);
    return (
      <>
        {before}
        <span className="font-semibold text-emerald-700">{match}</span>
        {after}
      </>
    );
  };

  const openDetails = (item: ValidationItem) => {
    setSelected(item);
    setDetailsOpen(true);
  };

  return (
    <RequireRole allowedRoles={["ADMIN"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar group/sidebar-inset">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <div className="flex items-center gap-2">
              <ClipboardList className="size-5" />
              <h1 className="text-lg font-semibold">Revisões</h1>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <UserDropdown />
            </div>
          </header>

          <div className="flex-1 overflow-auto bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
            <div className="p-6 md:p-8 lg:p-12 space-y-6 mx-auto w-full max-w-6xl">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">
                  Revisões com justificativas registradas, sem depender dos logs de auditoria.
                </p>
                {lastUpdatedAt && (
                  <p className="text-xs text-muted-foreground/70">
                    Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
                  </p>
                )}
              </div>

              <div className="rounded-lg border bg-white p-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-4">
                  <div className="space-y-1">
                    <Label htmlFor="validation-cpf">CPF</Label>
                    <Input
                      id="validation-cpf"
                      placeholder="Somente números"
                      value={cpfFilter}
                      onChange={(event) => setCpfFilter(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="validation-reviewer">Revisor</Label>
                    <Input
                      id="validation-reviewer"
                      placeholder="email@dominio.com"
                      value={reviewerFilter}
                      onChange={(event) => setReviewerFilter(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="validation-status">Status</Label>
                    <select
                      id="validation-status"
                      className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                      value={statusFilter}
                      onChange={(event) => trocarStatus(event.target.value)}
                    >
                      <option value="all">Todos</option>
                      <option value="validated">Aprovados</option>
                      <option value="rejected">Rejeitados</option>
                      <option value="pending">Pendentes</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="validation-text">Texto</Label>
                    <Input
                      id="validation-text"
                      placeholder="Buscar na mensagem..."
                      value={textFilter}
                      onChange={(event) => setTextFilter(event.target.value)}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="size-4 rounded border border-input"
                      checked={onlyWithJustification}
                      onChange={(event) => trocarSoComJustificativa(event.target.checked)}
                    />
                    Somente com justificativas
                  </label>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button onClick={fetchDocuments} disabled={loading}>
                    {loading && <Loader2 className="mr-2 size-4 animate-spin" />}
                    Atualizar
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setCpfFilter("");
                      setReviewerFilter("");
                      setTextFilter("");
                      trocarStatus("all");
                      trocarSoComJustificativa(false);
                    }}
                  >
                    Limpar filtros
                  </Button>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {loading ? (
                  <div className="rounded-lg border bg-white p-8 text-center text-muted-foreground md:col-span-2">
                    <div className="inline-flex items-center gap-2">
                      <Loader2 className="size-4 animate-spin" />
                      <span>Carregando revisões...</span>
                    </div>
                  </div>
                ) : items.length === 0 ? (
                  <div className="rounded-lg border bg-white p-8 text-center text-muted-foreground md:col-span-2">
                    Nenhuma revisão encontrada com os filtros atuais.
                  </div>
                ) : (
                  items.map((item) => (
                    <div
                      key={item.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => openDetails(item)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openDetails(item);
                        }
                      }}
                      className="w-full text-left rounded-lg border bg-white p-4 transition hover:border-slate-300 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="space-y-1">
                          <div className="font-semibold text-slate-800">{item.filename}</div>
                          <div className="text-xs text-muted-foreground">
                            CPF: {item.cpf || "-"} · Enviado em {formatDateTime(item.uploadedAt)}
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          {statusBadge(item.status)}
                          <div className="flex items-center gap-1">
                            <span>Score de confiança:</span>
                            <span className="font-semibold text-slate-700">
                              {typeof item.confidenceScore === "number" ? `${Math.round(item.confidenceScore)}%` : "-"}
                            </span>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  className="text-muted-foreground hover:text-slate-700"
                                  aria-label="Como o score é calculado"
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  <Info className="size-3.5" />
                                </button>
                              </TooltipTrigger>
                              <TooltipContent className="max-w-xs text-xs">
                                Score de confiança combina qualidade do OCR, cobertura dos exames obrigatórios e consistência dos campos detectados.
                              </TooltipContent>
                            </Tooltip>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {item.reviewedBy ? `Revisor: ${item.reviewedBy}` : "Sem revisor"}
                          </span>
                        </div>
                      </div>
                      <div className="mt-3 text-sm text-slate-600 line-clamp-3">
                        {highlightLiberacao(item.analysis)}
                      </div>
                      {((item.approvalReason && item.approvalReason.trim()) ||
                        (item.rejectionReason && item.rejectionReason.trim())) && (
                        <div className="mt-3 text-xs text-muted-foreground">
                          {item.approvalReason ? "Com justificativa de aprovação" : "Com justificativa de rejeição"}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>

              {totalItems > 0 && (
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
                  <span>
                    Página {page} de {totalPages} · {totalItems.toLocaleString("pt-BR")}{" "}
                    {totalItems === 1 ? "revisão" : "revisões"}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={loading || page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      Anterior
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={loading || page >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
            <DialogContent className="max-w-3xl">
              <DialogHeader>
                <DialogTitle>Revisão</DialogTitle>
              </DialogHeader>
              {selected ? (
                <div className="space-y-4 text-sm text-slate-700">
                  <div className="grid gap-2 md:grid-cols-2">
                    <div>
                      <div className="text-xs uppercase text-muted-foreground">Documento</div>
                      <div className="font-medium">{selected.filename}</div>
                      <div className="text-xs text-muted-foreground">CPF: {selected.cpf || "-"}</div>
                    </div>
                    <div>
                      <div className="text-xs uppercase text-muted-foreground">Status</div>
                      <div>{statusBadge(selected.status)}</div>
                      <div className="text-xs text-muted-foreground">
                        Score de confiança: {typeof selected.confidenceScore === "number" ? `${Math.round(selected.confidenceScore)}%` : "-"}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {selected.reviewedBy ? `Revisor: ${selected.reviewedBy}` : "Sem revisor"}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border bg-slate-50 p-3">
                    <div className="text-xs uppercase text-muted-foreground mb-1">Mensagem</div>
                    <p className="text-sm text-slate-700 whitespace-pre-wrap">
                      {highlightLiberacao(selected.analysis)}
                    </p>
                  </div>

                  {((selected.approvalReason && selected.approvalReason.trim()) ||
                    (selected.rejectionReason && selected.rejectionReason.trim())) && (
                    <div className="grid gap-3 md:grid-cols-2">
                      {selected.approvalReason && (
                        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                          <div className="text-xs uppercase text-emerald-700 mb-1">Justificativa de aprovação</div>
                          <p className="text-sm text-emerald-800 whitespace-pre-wrap">{selected.approvalReason}</p>
                        </div>
                      )}
                      {selected.rejectionReason && (
                        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
                          <div className="text-xs uppercase text-rose-700 mb-1">Justificativa de rejeição</div>
                          <p className="text-sm text-rose-800 whitespace-pre-wrap">{selected.rejectionReason}</p>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="text-xs text-muted-foreground">
                    Enviado em {formatDateTime(selected.uploadedAt)} · Revisado em {formatDateTime(selected.reviewedAt)}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">Nenhum item selecionado.</div>
              )}
            </DialogContent>
          </Dialog>
        </SidebarInset>
      </SidebarProvider>
    </RequireRole>
  );
}
