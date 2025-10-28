"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { RiMapPinLine, RiUploadLine, RiCheckDoubleLine, RiLightbulbLine } from "@remixicon/react";

interface TourStep {
  title: string;
  description: string;
  icon: typeof RiMapPinLine;
  anchorSelector: string;
}

const tourSteps: TourStep[] = [
  {
    icon: RiUploadLine,
    title: "Submissão",
    description:
      "Faça upload de documentos médicos para análise automática via OCR e validação contra o sistema BRNET.",
    anchorSelector: "[data-tour='submissao']",
  },
  {
    icon: RiCheckDoubleLine,
    title: "Checagem",
    description:
      "Revise documentos rejeitados e aprove ou rejeite manualmente com justificativas detalhadas.",
    anchorSelector: "[data-tour='checagem']",
  },
  {
    icon: RiLightbulbLine,
    title: "Insights",
    description:
      "Consulte nossa base de conhecimento com perguntas sobre medicina ocupacional e normas reguladoras.",
    anchorSelector: "[data-tour='insights']",
  },
  {
    icon: RiMapPinLine,
    title: "Navegação",
    description:
      "Use a barra lateral para navegar entre as funcionalidades. Clique no seu avatar para acessar configurações.",
    anchorSelector: "[data-tour='sidebar']",
  },
];

export function TourGuiado() {
  const [currentTip, setCurrentTip] = useState(0);
  const [isOpen, setIsOpen] = useState(false);

  const handleNavigation = () => {
    if (currentTip === tourSteps.length - 1) {
      setCurrentTip(0);
      setIsOpen(false);
    } else {
      setCurrentTip(currentTip + 1);
    }
  };

  const CurrentIcon = tourSteps[currentTip].icon;

  return (
    <Popover
      open={isOpen}
      onOpenChange={(open) => {
        setIsOpen(open);
        if (open) setCurrentTip(0);
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="w-full justify-start">
          <RiMapPinLine size={16} className="mr-2" />
          Iniciar Tour
        </Button>
      </PopoverTrigger>

      {/* O PopoverAnchor será definido pelos elementos com data-tour */}
      <PopoverContent
        className="max-w-[320px] py-4 shadow-lg"
        side="right"
        align="center"
        showArrow={true}
      >
        <div className="space-y-4">
          <div className="flex items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
              <CurrentIcon size={20} className="text-primary" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold">
                {tourSteps[currentTip].title}
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {tourSteps[currentTip].description}
              </p>
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 pt-2 border-t">
            <span className="text-xs text-muted-foreground">
              {currentTip + 1}/{tourSteps.length}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs font-medium"
              onClick={handleNavigation}
            >
              {currentTip === tourSteps.length - 1 ? "Concluir" : "Próximo"}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
