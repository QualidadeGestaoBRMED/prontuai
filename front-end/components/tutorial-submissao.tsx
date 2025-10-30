"use client";

import { InfoIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useState } from "react";

export function TutorialSubmissao() {
  const [isVisible, setIsVisible] = useState(true);

  if (!isVisible) return null;

  return (
    <Card className="border-blue-200 bg-blue-50/50">
      <CardContent className="p-4">
        <div className="flex gap-3">
          <InfoIcon size={20} className="text-blue-600 shrink-0 mt-0.5" />
          <div className="flex-1 space-y-2">
            <h3 className="font-medium text-sm text-blue-900">
              Como usar a Submissão de Documentos
            </h3>
            <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
              <li>Faça upload de documentos médicos em PDF ou imagem</li>
              <li>O sistema extrai automaticamente os exames via OCR</li>
              <li>Valida contra os exames autorizados no BRNET</li>
              <li>Resultados aparecem em tempo real no chat</li>
            </ul>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 shrink-0"
            onClick={() => setIsVisible(false)}
          >
            <XIcon size={14} />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
