"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

type AuditLog = {
  id?: string | null;
  user_id?: string | null;
  user_email?: string | null;
  user_role?: string | null;
  action: string;
  resource?: string | null;
  resource_id?: string | null;
  method?: string | null;
  path?: string | null;
  status_code?: number | null;
  ip?: string | null;
  user_agent?: string | null;
  request_id?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
};

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("pt-BR");
}

function statusBadge(status?: number | null) {
  if (!status) return <span className="text-muted-foreground">-</span>;
  if (status >= 500) {
    return (
      <Badge className="bg-rose-500 text-white border-transparent">
        {status}
      </Badge>
    );
  }
  if (status >= 400) {
    return (
      <Badge className="bg-amber-500 text-white border-transparent">
        {status}
      </Badge>
    );
  }
  if (status >= 300) {
    return <Badge variant="secondary">{status}</Badge>;
  }
  return (
    <Badge className="bg-emerald-500 text-white border-transparent">
      {status}
    </Badge>
  );
}

function methodBadge(method?: string | null) {
  if (!method) return <span className="text-muted-foreground">-</span>;
  const normalized = method.toUpperCase();
  const colors: Record<string, string> = {
    POST: "bg-indigo-500 text-white border-transparent",
    PUT: "bg-sky-500 text-white border-transparent",
    PATCH: "bg-amber-500 text-white border-transparent",
    DELETE: "bg-rose-500 text-white border-transparent",
  };
  const className = colors[normalized] ?? "bg-slate-200 text-slate-700 border-transparent";
  return <Badge className={className}>{normalized}</Badge>;
}

export default function AuditoriaPage() {
  const { data: session } = useSession();

  // Com DEV_AUTH_BYPASS não existe sessão do NextAuth, mas o proxy injeta o
  // Bearer do mesmo jeito. Esperar por session.user.email deixava a tabela
  // presa em "Carregando logs..." para sempre em dev.
  const bypassAuth =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";
  const podeCarregar = bypassAuth || !!session?.user?.email;
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const [userEmail, setUserEmail] = useState("");
  const [action, setAction] = useState("");
  const [requestId, setRequestId] = useState("");
  const [since, setSince] = useState("");
  const [limit, setLimit] = useState("200");
  const [hideNotifications, setHideNotifications] = useState(true);

  const queryParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", limit || "200");
    if (userEmail.trim()) params.set("user_email", userEmail.trim());
    if (action.trim()) params.set("action", action.trim());
    if (requestId.trim()) params.set("request_id", requestId.trim());
    if (since) {
      const date = new Date(since);
      if (!Number.isNaN(date.getTime())) {
        params.set("since", date.toISOString());
      }
    }
    return params.toString();
  }, [userEmail, action, requestId, since, limit]);

  const formatMetadata = (metadata?: Record<string, unknown> | null) => {
    if (!metadata || Object.keys(metadata).length === 0) return null;
    try {
      return JSON.stringify(metadata, null, 2);
    } catch {
      return null;
    }
  };
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
  const openDetails = (log: AuditLog) => {
    setSelectedLog(log);
    setDetailsOpen(true);
  };
  const validationMessage =
    typeof selectedLog?.metadata?.validation_message === "string"
      ? selectedLog.metadata.validation_message
      : null;
  const approvalReason =
    typeof selectedLog?.metadata?.approval_reason === "string"
      ? selectedLog.metadata.approval_reason
      : null;
  const rejectionReason =
    typeof selectedLog?.metadata?.rejection_reason === "string"
      ? selectedLog.metadata.rejection_reason
      : null;

  const fetchLogs = useCallback(async () => {
    if (!podeCarregar) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const response = await authFetch(`${API_ENDPOINTS.AUDIT_LOGS}?${queryParams}`);

      if (!response.ok) {
        throw new Error("Erro ao carregar logs de auditoria");
      }

      const data = (await response.json()) as AuditLog[];
      const filtered = hideNotifications
        ? data.filter((log) => {
            const actionText = (log.action || "").toLowerCase();
            const resourceText = (log.resource || "").toLowerCase();
            const pathText = (log.path || "").toLowerCase();
            return (
              !actionText.includes("notifications") &&
              resourceText !== "notifications" &&
              !pathText.includes("/v1/notifications")
            );
          })
        : data;
      setLogs(filtered);
      setLastUpdatedAt(new Date());
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar logs de auditoria");
    } finally {
      setLoading(false);
    }
  }, [podeCarregar, queryParams, hideNotifications]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  return (
    <RequireRole allowedRoles={["ADMIN"]}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="bg-sidebar group/sidebar-inset">
          <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
            <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-5" />
              <h1 className="text-lg font-semibold">Auditoria</h1>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <UserDropdown />
            </div>
          </header>

          <div className="flex-1 overflow-auto bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
            <div className="p-6 md:p-8 lg:p-12 space-y-6 mx-auto w-full max-w-7xl">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">
                  Acompanhe ações sensíveis feitas no sistema (POST/PUT/PATCH/DELETE).
                </p>
                {lastUpdatedAt && (
                  <p className="text-xs text-muted-foreground/70">
                    Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
                  </p>
                )}
              </div>

              <div className="rounded-lg border bg-white p-4 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  <div className="space-y-1">
                    <Label htmlFor="audit-user-email">Usuário</Label>
                    <Input
                      id="audit-user-email"
                      placeholder="email@dominio.com"
                      value={userEmail}
                      onChange={(event) => setUserEmail(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="audit-action">Ação</Label>
                    <Input
                      id="audit-action"
                      placeholder="patch:/v1/documents/..."
                      value={action}
                      onChange={(event) => setAction(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="audit-request-id">Request ID</Label>
                    <Input
                      id="audit-request-id"
                      placeholder="fa38-48b4..."
                      value={requestId}
                      onChange={(event) => setRequestId(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="audit-since">Desde</Label>
                    <Input
                      id="audit-since"
                      type="datetime-local"
                      value={since}
                      onChange={(event) => setSince(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="audit-limit">Limite</Label>
                    <Input
                      id="audit-limit"
                      type="number"
                      min={1}
                      max={1000}
                      value={limit}
                      onChange={(event) => setLimit(event.target.value)}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button onClick={fetchLogs} disabled={loading}>
                    {loading && <Loader2 className="mr-2 size-4 animate-spin" />}
                    Atualizar
                  </Button>
                  <Button
                    variant={hideNotifications ? "secondary" : "outline"}
                    onClick={() => setHideNotifications((prev) => !prev)}
                  >
                    {hideNotifications ? "Mostrando: sem notificações" : "Mostrando: com notificações"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setUserEmail("");
                      setAction("");
                      setRequestId("");
                      setSince("");
                      setLimit("200");
                      setHideNotifications(true);
                    }}
                  >
                    Limpar filtros
                  </Button>
                </div>
              </div>

              <div className="rounded-lg border bg-white overflow-x-auto">
                {/*
                  Com table-fixed a largura de cada coluna vem da PRIMEIRA linha,
                  ou seja do cabeçalho. Largura declarada só no <td> do corpo é
                  ignorada — era o que fazia as 9 colunas ficarem iguais e o
                  conteúdo de "Ação" ser pintado por cima de "Recurso".
                  min-w mantém a proporção e joga a diferença no scroll lateral.
                */}
                <Table className="w-full table-fixed min-w-[1170px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[140px]">Data</TableHead>
                      <TableHead className="w-[165px]">Usuário</TableHead>
                      <TableHead className="w-[225px]">Ação</TableHead>
                      <TableHead className="w-[145px]">Recurso</TableHead>
                      {/* 115px porque o método mais largo é BACKGROUND, não DELETE. */}
                      <TableHead className="w-[115px]">Método</TableHead>
                      <TableHead className="w-[80px]">Status</TableHead>
                      <TableHead className="w-[100px]">IP</TableHead>
                      <TableHead className="w-[130px]">Request ID</TableHead>
                      <TableHead className="w-[70px]">Detalhes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
                          <div className="inline-flex items-center gap-2">
                            <Loader2 className="size-4 animate-spin" />
                            <span>Carregando logs...</span>
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : logs.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
                          Nenhum log encontrado com os filtros atuais.
                        </TableCell>
                      </TableRow>
                    ) : (
                      logs.map((log) => (
                        <Fragment key={log.id ?? `${log.request_id}-${log.created_at}`}>
                          <TableRow className="align-top">
                            <TableCell className="text-sm text-muted-foreground">
                              {formatDateTime(log.created_at)}
                            </TableCell>
                            <TableCell className="text-sm">
                              <div
                                className="font-medium truncate"
                                title={log.user_email ?? "Sistema/Automação"}
                              >
                                {log.user_email ?? "Sistema/Automação"}
                              </div>
                              <div className="text-xs text-muted-foreground truncate">
                                {log.user_role ?? "-"}
                              </div>
                            </TableCell>
                            {/*
                              truncate (overflow hidden + nowrap) é o que impede
                              o texto de ser pintado fora da célula. O valor
                              inteiro fica no title e no modal "Ver".
                            */}
                            <TableCell className="text-sm">
                              <div className="font-medium truncate" title={log.action}>
                                {log.action}
                              </div>
                              <div
                                className="text-xs text-muted-foreground truncate"
                                title={log.path ?? undefined}
                              >
                                {log.path ?? "-"}
                              </div>
                            </TableCell>
                            <TableCell className="text-sm">
                              <div
                                className="font-medium truncate"
                                title={log.resource ?? undefined}
                              >
                                {log.resource ?? "-"}
                              </div>
                              <div
                                className="text-xs text-muted-foreground truncate"
                                title={log.resource_id ?? undefined}
                              >
                                {log.resource_id ?? "-"}
                              </div>
                            </TableCell>
                            <TableCell>{methodBadge(log.method)}</TableCell>
                            <TableCell>{statusBadge(log.status_code)}</TableCell>
                            <TableCell className="text-sm text-muted-foreground truncate">
                              {log.ip ?? "-"}
                            </TableCell>
                            <TableCell
                              className="text-xs text-muted-foreground truncate"
                              title={log.request_id ?? undefined}
                            >
                              {log.request_id ?? "-"}
                            </TableCell>
                            <TableCell>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openDetails(log)}
                              >
                                Ver
                              </Button>
                            </TableCell>
                          </TableRow>
                        </Fragment>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
              <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
                <DialogContent className="max-w-3xl">
                  <DialogHeader>
                    <DialogTitle>Detalhes da auditoria</DialogTitle>
                  </DialogHeader>
                  {selectedLog ? (
                    <div className="space-y-4 text-sm text-slate-700">
                      <div className="grid gap-2 md:grid-cols-2">
                        <div>
                          <div className="text-xs uppercase text-muted-foreground">Usuário</div>
                          <div className="font-medium">{selectedLog.user_email ?? "Sistema/Automação"}</div>
                          <div className="text-xs text-muted-foreground">{selectedLog.user_role ?? "-"}</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase text-muted-foreground">Ação</div>
                          <div className="font-medium">{selectedLog.action}</div>
                          <div className="text-xs text-muted-foreground">{selectedLog.path ?? "-"}</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase text-muted-foreground">Status</div>
                          <div>{statusBadge(selectedLog.status_code)}</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase text-muted-foreground">Request ID</div>
                          <div className="text-xs text-muted-foreground">{selectedLog.request_id ?? "-"}</div>
                        </div>
                      </div>

                      {validationMessage && (
                        <div className="rounded-lg border bg-slate-50 p-3">
                          <div className="text-xs uppercase text-muted-foreground mb-1">Análise da Revisão</div>
                          <p className="text-sm text-slate-700">
                            {highlightLiberacao(validationMessage)}
                          </p>
                        </div>
                      )}

                      {(approvalReason || rejectionReason) && (
                        <div className="grid gap-3 md:grid-cols-2">
                          {approvalReason && (
                            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                              <div className="text-xs uppercase text-emerald-700 mb-1">Justificativa de aprovação</div>
                              <p className="text-sm text-emerald-800">
                                {approvalReason}
                              </p>
                            </div>
                          )}
                          {rejectionReason && (
                            <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
                              <div className="text-xs uppercase text-rose-700 mb-1">Justificativa de rejeição</div>
                              <p className="text-sm text-rose-800">
                                {rejectionReason}
                              </p>
                            </div>
                          )}
                        </div>
                      )}

                      <div>
                        <div className="text-xs uppercase text-muted-foreground mb-1">Metadata</div>
                        <pre className="whitespace-pre-wrap break-words rounded bg-white p-3 border text-xs">
                          {formatMetadata(selectedLog.metadata) ?? "-"}
                        </pre>
                      </div>
                      <div>
                        <div className="text-xs uppercase text-muted-foreground mb-1">User Agent</div>
                        <div className="text-xs text-muted-foreground break-words">
                          {selectedLog.user_agent ?? "-"}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">Nenhum log selecionado.</div>
                  )}
                </DialogContent>
              </Dialog>
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
    </RequireRole>
  );
}
