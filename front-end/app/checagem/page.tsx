"use client";

import { useState } from "react";
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

// Mock data - Em produção, viria do backend
const mockDocumentos: DocumentoChecagem[] = [
  {
    id: "1",
    cpf: "123.456.789-00",
    paciente: "João Silva Santos",
    dataUpload: "2025-10-27T10:30:00",
    status: "pendente",
    examesFaltantes: 2,
    examesExtras: 1,
  },
  {
    id: "2",
    cpf: "987.654.321-00",
    paciente: "Maria Oliveira Costa",
    dataUpload: "2025-10-27T14:15:00",
    status: "pendente",
    examesFaltantes: 0,
    examesExtras: 3,
  },
  {
    id: "3",
    cpf: "456.789.123-00",
    paciente: "Pedro Henrique Alves",
    dataUpload: "2025-10-26T09:00:00",
    status: "aprovado",
    dataProcessamento: "2025-10-26T09:30:00",
    examesFaltantes: 0,
    examesExtras: 0,
  },
  {
    id: "4",
    cpf: "321.654.987-00",
    paciente: "Ana Paula Rodrigues",
    dataUpload: "2025-10-26T16:45:00",
    status: "rejeitado",
    dataProcessamento: "2025-10-26T17:00:00",
    motivoRejeicao: "Documento ilegível - qualidade da imagem insuficiente",
    examesFaltantes: 5,
    examesExtras: 0,
  },
  {
    id: "5",
    cpf: "789.123.456-00",
    paciente: "Carlos Eduardo Lima",
    dataUpload: "2025-10-28T08:20:00",
    status: "pendente",
    examesFaltantes: 1,
    examesExtras: 0,
  },
];

export default function Page() {
  const [documentos, setDocumentos] =
    useState<DocumentoChecagem[]>(mockDocumentos);

  const handleAprovar = (id: string) => {
    setDocumentos((docs) =>
      docs.map((doc) =>
        doc.id === id
          ? {
              ...doc,
              status: "aprovado",
              dataProcessamento: new Date().toISOString(),
            }
          : doc
      )
    );

    const doc = documentos.find((d) => d.id === id);
    toast.success("Documento aprovado", {
      description: `Documento do paciente ${doc?.paciente} foi aprovado com sucesso.`,
    });
  };

  const handleRejeitar = (id: string, motivo: string) => {
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

    const doc = documentos.find((d) => d.id === id);
    toast.error("Documento rejeitado", {
      description: `Documento do paciente ${doc?.paciente} foi rejeitado.`,
    });
  };

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="bg-sidebar group/sidebar-inset">
        <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
          <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
          <h1 className="text-lg font-semibold">Checagem de Documentos</h1>
          <div className="flex items-center gap-2 ml-auto">
            <UserDropdown />
          </div>
        </header>

        <div className="flex flex-col h-[calc(100svh-4rem)] bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
          <div className="flex-1 flex flex-col p-4 md:p-6 lg:p-8 overflow-hidden">
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

            {/* Tabela de checagem - ocupando todo espaço disponível */}
            <div className="flex-1 bg-white rounded-lg p-6 shadow-sm overflow-hidden flex flex-col">
              <CheckagemTable
                documentos={documentos}
                onAprovar={handleAprovar}
                onRejeitar={handleRejeitar}
              />
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
