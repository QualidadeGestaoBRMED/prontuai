"use client";

import { CheckIcon, XIcon, EyeIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useState } from "react";
import type { DocumentoChecagem } from "@/types/checagem";

type CheckagemActionsProps = {
  documento: DocumentoChecagem;
  onAprovar: (id: string) => void;
  onRejeitar: (id: string, motivo: string) => void;
};

export function CheckagemActions({
  documento,
  onAprovar,
  onRejeitar,
}: CheckagemActionsProps) {
  const [motivo, setMotivo] = useState("");

  return (
    <div className="flex gap-2">
      {/* Botão Visualizar */}
      {documento.documentoUrl && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => window.open(documento.documentoUrl, "_blank")}
          className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
        >
          <EyeIcon size={16} className="mr-1" />
          Visualizar
        </Button>
      )}

      {/* Botão Aprovar */}
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            size="sm"
            variant="outline"
            className="text-green-600 hover:text-green-700 hover:bg-green-50"
          >
            <CheckIcon size={16} className="mr-1" />
            Aprovar
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar aprovação</AlertDialogTitle>
            <AlertDialogDescription className="text-foreground">
              Tem certeza que deseja aprovar o documento do paciente{" "}
              <strong>{documento.paciente}</strong> (CPF: {documento.cpf})?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => onAprovar(documento.id)}
              className="bg-green-600 hover:bg-green-700"
            >
              Aprovar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Botão Rejeitar */}
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            size="sm"
            variant="outline"
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <XIcon size={16} className="mr-1" />
            Rejeitar
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Rejeitar documento</AlertDialogTitle>
            <AlertDialogDescription className="text-foreground">
              Informe o motivo da rejeição do documento do paciente{" "}
              <strong>{documento.paciente}</strong> (CPF: {documento.cpf}).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="motivo" className="text-foreground">Motivo da rejeição</Label>
            <Textarea
              id="motivo"
              placeholder="Ex: Documento ilegível, exames faltantes, etc."
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              rows={4}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setMotivo("")}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                onRejeitar(documento.id, motivo);
                setMotivo("");
              }}
              disabled={!motivo.trim()}
              className="bg-red-600 hover:bg-red-700"
            >
              Rejeitar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
