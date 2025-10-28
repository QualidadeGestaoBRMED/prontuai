"use client";

import { FileTextIcon, CheckCircle2Icon, XCircleIcon, ClockIcon, LoaderIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { HistoricoModal } from "@/components/historico-modal";
import type { DocumentoHistorico, StatusProcessamento } from "@/types/historico";

type HistoricoDocumentosProps = {
  documentos: DocumentoHistorico[];
};

const statusConfig: Record<
  StatusProcessamento,
  {
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    className: string;
  }
> = {
  sucesso: {
    label: "Sucesso",
    icon: CheckCircle2Icon,
    className: "bg-green-400/20 text-green-700 border-green-400/50",
  },
  erro: {
    label: "Erro",
    icon: XCircleIcon,
    className: "bg-red-400/20 text-red-700 border-red-400/50",
  },
  processando: {
    label: "Processando",
    icon: LoaderIcon,
    className: "bg-blue-400/20 text-blue-700 border-blue-400/50",
  },
  pendente: {
    label: "Pendente",
    icon: ClockIcon,
    className: "bg-yellow-400/20 text-yellow-700 border-yellow-400/50",
  },
};

export function HistoricoDocumentos({ documentos }: HistoricoDocumentosProps) {
  if (documentos.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-8 text-center">
          <FileTextIcon size={48} className="text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">
            Nenhum documento processado ainda
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <ScrollArea className="h-[500px] rounded-lg border">
      <div className="p-4 space-y-3">
        {documentos.map((doc) => {
          const config = statusConfig[doc.status];
          const IconComponent = config.icon;

          return (
            <HistoricoModal key={doc.id} documento={doc}>
              <Card className="overflow-hidden cursor-pointer hover:bg-accent/50 transition-colors">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      {/* Nome do documento */}
                      <div className="flex items-center gap-2 mb-2">
                        <FileTextIcon size={18} className="text-muted-foreground shrink-0" />
                        <h4 className="font-medium truncate">{doc.nome}</h4>
                      </div>

                      {/* Informações do documento */}
                      <div className="space-y-1 text-sm text-muted-foreground">
                        <div className="flex items-center gap-2">
                          <span className="font-mono">{doc.cpf}</span>
                          <span>•</span>
                          <span>{new Date(doc.dataUpload).toLocaleString("pt-BR")}</span>
                        </div>

                        {/* Estatísticas */}
                        {doc.status === "sucesso" && (
                          <div className="flex items-center gap-3 text-xs">
                            <span>
                              Exames: {doc.examesEncontrados}/{doc.examesPrevistos}
                            </span>
                            <span>•</span>
                            <span
                              className={cn(
                                "font-medium",
                                doc.compatibilidade >= 80
                                  ? "text-green-600"
                                  : doc.compatibilidade >= 50
                                    ? "text-yellow-600"
                                    : "text-red-600"
                              )}
                            >
                              Compatibilidade: {doc.compatibilidade}%
                            </span>
                          </div>
                        )}

                        {/* Mensagem de erro */}
                        {doc.mensagem && (
                          <p className="text-xs text-red-600 mt-2">{doc.mensagem}</p>
                        )}
                      </div>
                    </div>

                    {/* Status Badge */}
                    <Badge variant="outline" className={cn("shrink-0", config.className)}>
                      <IconComponent
                        className={cn(
                          "mr-1",
                          doc.status === "processando" && "animate-spin"
                        )}
                        size={14}
                      />
                      {config.label}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
            </HistoricoModal>
          );
        })}
      </div>
    </ScrollArea>
  );
}
