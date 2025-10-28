"use client";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { FileTextIcon, CalendarIcon, UserIcon, CheckCircleIcon } from "lucide-react";
import type { DocumentoHistorico } from "@/types/historico";

interface HistoricoModalProps {
  documento: DocumentoHistorico;
  children: React.ReactNode;
}

export function HistoricoModal({ documento, children }: HistoricoModalProps) {
  const statusColors = {
    sucesso: "text-green-600 bg-green-50 border-green-200",
    erro: "text-red-600 bg-red-50 border-red-200",
    processando: "text-yellow-600 bg-yellow-50 border-yellow-200",
    pendente: "text-gray-600 bg-gray-50 border-gray-200",
  };

  const statusLabels = {
    sucesso: "Sucesso",
    erro: "Erro",
    processando: "Processando",
    pendente: "Pendente",
  };

  return (
    <Dialog>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="flex flex-col gap-0 p-0 sm:max-h-[min(640px,80vh)] sm:max-w-lg [&>button:last-child]:top-3.5">
        <DialogHeader className="contents space-y-0 text-left">
          <DialogTitle className="border-b px-6 py-4 text-base flex items-center gap-2">
            <FileTextIcon size={20} />
            Detalhes do Documento
          </DialogTitle>
          <div className="overflow-y-auto">
            <DialogDescription asChild>
              <div className="px-6 py-4">
                <div className="space-y-4">
                  {/* Status Badge */}
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium border ${
                        statusColors[documento.status]
                      }`}
                    >
                      {statusLabels[documento.status]}
                    </span>
                    {documento.status === "sucesso" && (
                      <span className="text-xs text-muted-foreground">
                        {documento.compatibilidade}% de compatibilidade
                      </span>
                    )}
                  </div>

                  {/* Informações do documento */}
                  <div className="space-y-3 [&_strong]:font-semibold [&_strong]:text-foreground">
                    <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                      <FileTextIcon size={18} className="text-blue-600 mt-0.5" />
                      <div>
                        <p className="text-xs text-muted-foreground">Nome do arquivo</p>
                        <p className="text-sm font-medium">{documento.nome}</p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                      <UserIcon size={18} className="text-purple-600 mt-0.5" />
                      <div>
                        <p className="text-xs text-muted-foreground">CPF do paciente</p>
                        <p className="text-sm font-medium">{documento.cpf}</p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                      <CalendarIcon size={18} className="text-green-600 mt-0.5" />
                      <div>
                        <p className="text-xs text-muted-foreground">Data de upload</p>
                        <p className="text-sm font-medium">
                          {new Date(documento.dataUpload).toLocaleString("pt-BR", {
                            dateStyle: "short",
                            timeStyle: "short",
                          })}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Resumo dos exames */}
                  {documento.status === "sucesso" && (
                    <div className="space-y-2 pt-2 border-t">
                      <p className="text-xs font-semibold text-foreground uppercase tracking-wide">
                        Resumo da Análise
                      </p>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 rounded-lg bg-blue-50 border border-blue-200">
                          <p className="text-xs text-blue-700">Exames Encontrados</p>
                          <p className="text-2xl font-bold text-blue-600">
                            {documento.examesEncontrados}
                          </p>
                        </div>
                        <div className="p-3 rounded-lg bg-indigo-50 border border-indigo-200">
                          <p className="text-xs text-indigo-700">Exames Previstos</p>
                          <p className="text-2xl font-bold text-indigo-600">
                            {documento.examesPrevistos}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Mensagem de erro */}
                  {documento.status === "erro" && (
                    <div className="p-3 rounded-lg bg-red-50 border border-red-200">
                      <p className="text-xs font-semibold text-red-700 mb-1">Erro no processamento</p>
                      <p className="text-xs text-red-600">
                        Não foi possível processar este documento. Verifique se o arquivo está legível e tente novamente.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </DialogDescription>
            <DialogFooter className="px-6 pb-6 sm:justify-start">
              <DialogClose asChild>
                <Button type="button">Fechar</Button>
              </DialogClose>
            </DialogFooter>
          </div>
        </DialogHeader>
      </DialogContent>
    </Dialog>
  );
}
