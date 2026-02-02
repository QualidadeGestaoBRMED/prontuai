"use client";

import { useState, useEffect } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import UserDropdown from "@/components/user-dropdown";
import { CheckagemTable } from "@/components/checagem-table";
import type { DocumentoChecagem } from "@/types/checagem";
import { toast } from "sonner";
import { useNotifications } from "@/hooks/use-notifications";
import { NotificationBell } from "@/components/notification-bell";
import { NotificationCenter } from "@/components/notification-center";
import { useSession } from "next-auth/react";
import { ProcessResult } from "@/types/process";
import { DocumentDetailsModalChecagem } from "@/components/document-details-modal-checagem";
import { RequireRole } from "@/components/require-role";
import { useDocuments } from "@/hooks/use-documents";
import { documentToProcessResult } from "@/lib/document-mapper";
import { API_ENDPOINTS } from "@/lib/config";
import { Loader2 } from "lucide-react";

export default function Page() {
  const [documentos, setDocumentos] = useState<DocumentoChecagem[]>([]);
  const [selectedResult, setSelectedResult] = useState<ProcessResult | null>(null);
  const { processResults, updateProcessResultStatus, addNotification, unreadCount, activeProcess, setNotificationCenterOpen } = useNotifications();
  const { documents, loading, refreshing, hasLoaded, lastUpdatedAt } = useDocuments();
  const sessionData = useSession();
  const session = sessionData?.data || null;
  const dbResults = documents.map(documentToProcessResult);
  const showRefreshing = refreshing && hasLoaded;

  const getChecagemPriority = (result: ProcessResult) => {
    if (result.status === 'pending_review') return 0;
    if (result.status === 'rejected' && !result.reviewedBy) return 0;
    if (result.status === 'approved' && !result.reviewedBy) return 1;
    return 2;
  };

  const getChecagemTimestamp = (result: ProcessResult) => {
    const dateValue = result.reviewedAt ?? result.processedAt ?? result.uploadedAt;
    return new Date(dateValue).getTime();
  };

  const handleViewDocument = async (result: ProcessResult) => {
    try {
      const headers: Record<string, string> = {};
      if (session?.accessToken) {
        headers.Authorization = `Bearer ${session.accessToken}`;
      }
      const response = await fetch(API_ENDPOINTS.DOCUMENT_VIEW(result.id), { headers });
      if (!response.ok) {
        toast.error("Não foi possível abrir o documento.");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      toast.error("Falha ao carregar o documento.");
    }
  };

  // Carrega documentos de processResults que precisam de revisão
  useEffect(() => {
    if (loading && !hasLoaded) return;
    const dbResults = documents.map(documentToProcessResult);
    const source = hasLoaded ? dbResults : processResults;
    // Converte ProcessResult para formato DocumentoChecagem
    // Inclui: aprovados pela IA (precisam de validação humana), pending_review (rejeitados pela IA), e rejeitados pela IA mas ainda não revisados por humano
    const pendingDocs: DocumentoChecagem[] = source
      .filter(result =>
        result.status === 'approved' ||
        result.status === 'pending_review' ||
        (result.status === 'rejected' && !result.reviewedBy)
      )
      .sort((a, b) => {
        const priorityDiff = getChecagemPriority(a) - getChecagemPriority(b);
        if (priorityDiff !== 0) return priorityDiff;
        return getChecagemTimestamp(b) - getChecagemTimestamp(a);
      })
      .map(result => ({
        id: result.id,
        cpf: result.cpf,
        paciente: result.patientName,
        dataUpload: new Date(result.uploadedAt).toISOString(),
        status: result.status === 'pending_review' ? 'pendente' as const :
                result.status === 'rejected' ? 'rejeitado' as const :
                'aprovado' as const,
        dataProcessamento: result.reviewedAt ? new Date(result.reviewedAt).toISOString() : undefined,
        motivoRejeicao: result.rejectionReason,
        examesFaltantes: result.examesFaltantes,
        examesExtras: result.examesExtras,
        // Preserva decisão original da IA para exibição do badge
        decisaoIA: result.reviewedBy ? undefined : (result.status as 'approved' | 'rejected' | 'pending_review') === 'pending_review' ? 'rejected' : result.status as 'approved' | 'rejected',
        submittedBy: result.submittedBy,
      }));

    setDocumentos(pendingDocs);
  }, [processResults, documents, loading, hasLoaded]);

  const handleAprovar = async (id: string, approvalReason: string) => {
    const sourceResults = hasLoaded ? dbResults : processResults;
    const result = sourceResults.find((r) => r.id === id);
    const approvalReasonValue = approvalReason?.trim() || "";
    const approvalReasonNormalized = approvalReasonValue.length ? approvalReasonValue : undefined;

    // Atualiza no contexto de notificações
    updateProcessResultStatus(
      id,
      'approved',
      session?.user?.email || 'revisor@grupobrmed.com.br',
      undefined,
      approvalReasonNormalized
    );

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`;
    }

    try {
      console.info("[CHECAGEM] Aprovando documento", { id, approvalReason: approvalReasonNormalized });
      const response = await fetch(`${API_ENDPOINTS.DOCUMENTS}/${id}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({
          validation_status: 'validated',
          result_payload: {
            ...(result?.result || {}),
            reviewed_by: session?.user?.email || 'revisor@grupobrmed.com.br',
            reviewed_at: new Date().toISOString(),
            approvalReason: approvalReasonNormalized,
          }
        })
      });
      const text = await response.text().catch(() => "");
      console.info("[CHECAGEM] Resposta aprovação", { status: response.status, ok: response.ok, body: text });
    } catch (error) {
      console.error("[CHECAGEM] Falha ao aprovar documento", error);
    }

    // Atualiza estado local (array documentos)
    setDocumentos((docs) =>
      docs.map((doc) =>
        doc.id === id
          ? {
              ...doc,
              status: "aprovado",
              dataProcessamento: new Date().toISOString(),
              approvalReason: approvalReasonNormalized,
            }
          : doc
      )
    );

    // Cria notificação para o remetente
    if (result) {
      const reviewerEmail = session?.user?.email || 'revisor@grupobrmed.com.br'
      const reviewerName = session?.user?.name || 'um revisor'
      const mensagemJustificativa = approvalReasonNormalized
        ? ` Justificativa: ${approvalReasonNormalized}`
        : ""

      addNotification({
        type: 'review_approved',
        title: 'Documento Aprovado',
        message: `Seu documento do paciente ${result.patientName} foi aprovado por ${reviewerName}.${mensagemJustificativa}`,
        read: false,
        metadata: {
          documentId: id,
          cpf: result.cpf,
          reviewerEmail,
          approvalReason: approvalReasonNormalized,
        },
        variant: 'success',
      });
    }

    toast.success("Documento aprovado", {
      description: `Documento do paciente ${result?.patientName} foi aprovado com sucesso.`,
    });
  };

  const handleRejeitar = async (id: string, motivo: string) => {
    const result = (dbResults.length ? dbResults : processResults).find((r) => r.id === id);

    // Atualiza no contexto de notificações
    updateProcessResultStatus(id, 'rejected', session?.user?.email || 'revisor@grupobrmed.com.br', motivo);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (session?.accessToken) {
      headers.Authorization = `Bearer ${session.accessToken}`;
    }

    try {
      console.info("[CHECAGEM] Rejeitando documento", { id, motivo });
      const response = await fetch(`${API_ENDPOINTS.DOCUMENTS}/${id}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({
          validation_status: 'rejected',
          result_payload: {
            ...(result?.result || {}),
            reviewed_by: session?.user?.email || 'revisor@grupobrmed.com.br',
            reviewed_at: new Date().toISOString(),
            rejectionReason: motivo,
          }
        })
      });
      const text = await response.text().catch(() => "");
      console.info("[CHECAGEM] Resposta rejeição", { status: response.status, ok: response.ok, body: text });
    } catch (error) {
      console.error("[CHECAGEM] Falha ao rejeitar documento", error);
    }

    // Atualiza estado local
    setDocumentos((docs) =>
      docs.map((doc) =>
        doc.id === id
          ? {
              ...doc,
              status: "rejeitado",
              dataProcessamento: new Date().toISOString(),
              motivoRejeicao: motivo,
            }
          : doc
      )
    );

    // Cria notificação para o remetente
    if (result) {
      const reviewerEmail = session?.user?.email || 'revisor@grupobrmed.com.br'

      addNotification({
        type: 'review_rejected',
        title: 'Documento Rejeitado',
        message: `Seu documento do paciente ${result.patientName} foi rejeitado: ${motivo}`,
        read: false,
        metadata: {
          documentId: id,
          cpf: result.cpf,
          reviewerEmail,
        },
        variant: 'error',
      });
    }

    toast.error("Documento rejeitado", {
      description: `Documento do paciente ${result?.patientName} foi rejeitado.`,
    });
  };

  const handleViewDetails = (id: string) => {
    const result = (dbResults.length ? dbResults : processResults).find((r) => r.id === id);
    if (result) {
      setSelectedResult(result);
    }
  };

  return (
    <RequireRole allowedRoles={["ADMIN", "CHECKER"]}>
      <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="bg-sidebar group/sidebar-inset">
        <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
          <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
          <h1 className="text-lg font-semibold">Checagem de Documentos</h1>
          <div className="flex items-center gap-2 ml-auto">
            <NotificationBell
              unreadCount={unreadCount}
              hasActiveProcess={!!activeProcess}
              onClick={() => setNotificationCenterOpen(true)}
            />
            <UserDropdown />
          </div>
        </header>

        <div className="flex flex-col h-[calc(100svh-4rem)] bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
          <div className="flex-1 flex flex-col p-4 md:p-6 lg:p-8 overflow-hidden">
            {lastUpdatedAt && (
              <p className="text-xs text-muted-foreground/70 mb-2">
                Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
              </p>
            )}
            {/* Estatísticas compactas */}
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-gradient-to-br from-yellow-50 to-yellow-100 border border-yellow-200 rounded-lg p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-medium text-yellow-700 uppercase tracking-wide">Pendentes</div>
                    <div className="text-3xl font-bold text-yellow-600 mt-1">
                      {documentos.filter((d) => d.status === "pendente").length}
                    </div>
                  </div>
                  <div className="size-12 rounded-full bg-yellow-200 flex items-center justify-center">
                    <svg className="size-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
              </div>

              <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-medium text-green-700 uppercase tracking-wide">Aprovados</div>
                    <div className="text-3xl font-bold text-green-600 mt-1">
                      {documentos.filter((d) => d.status === "aprovado").length}
                    </div>
                  </div>
                  <div className="size-12 rounded-full bg-green-200 flex items-center justify-center">
                    <svg className="size-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
              </div>

              <div className="bg-gradient-to-br from-red-50 to-red-100 border border-red-200 rounded-lg p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-medium text-red-700 uppercase tracking-wide">Rejeitados</div>
                    <div className="text-3xl font-bold text-red-600 mt-1">
                      {documentos.filter((d) => d.status === "rejeitado").length}
                    </div>
                  </div>
                  <div className="size-12 rounded-full bg-red-200 flex items-center justify-center">
                    <svg className="size-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
              </div>
            </div>

            {showRefreshing && (
              <div className="mb-4 border rounded-lg bg-white p-3 flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                <span>Atualizando documentos do banco...</span>
                {lastUpdatedAt && (
                  <span className="text-xs text-muted-foreground/70">
                    Última atualização: {lastUpdatedAt.toLocaleTimeString("pt-BR")}
                  </span>
                )}
              </div>
            )}

            {/* Tabela de checagem - ocupando todo espaço disponível */}
            <div className="flex-1 bg-white rounded-lg p-6 shadow-sm overflow-hidden flex flex-col">
              {loading && !hasLoaded ? (
                <div className="flex-1 flex items-center justify-center text-muted-foreground gap-3">
                  <Loader2 className="size-4 animate-spin" />
                  <span>Sincronizando documentos com o banco...</span>
                </div>
              ) : (
                <CheckagemTable
                  documentos={documentos}
                  onAprovar={handleAprovar}
                  onRejeitar={handleRejeitar}
                  onViewDetails={handleViewDetails}
                />
              )}
            </div>
          </div>
        </div>
      </SidebarInset>
      <NotificationCenter />
      <DocumentDetailsModalChecagem
        open={!!selectedResult}
        onOpenChange={(open) => !open && setSelectedResult(null)}
        result={selectedResult}
        onAprovar={handleAprovar}
        onRejeitar={handleRejeitar}
        onViewDocument={selectedResult ? () => handleViewDocument(selectedResult) : undefined}
      />
      </SidebarProvider>
    </RequireRole>
  );
}
