"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { RiMapPinLine } from "@remixicon/react";
import ShepherdLib from "shepherd.js";
import "shepherd.js/dist/css/shepherd.css";

type ShepherdTour = {
  complete(): void;
  start(): void;
  addStep(options: unknown): void;
}

export function TourGuiado() {
  const tourRef = useRef<ShepherdTour | null>(null);

  useEffect(() => {
    // Cleanup on unmount
    return () => {
      if (tourRef.current) {
        tourRef.current.complete();
        tourRef.current = null;
      }
    };
  }, []);

  const startTour = () => {
    // Create new tour instance
    const tour = new ShepherdLib.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        cancelIcon: {
          enabled: true,
        },
        classes: "shepherd-theme-custom",
        scrollTo: { behavior: "smooth", block: "center" },
        modalOverlayOpeningPadding: 8,
        modalOverlayOpeningRadius: 8,
      },
    });

    // Helper function to wait for element
    const waitForElement = (selector: string, timeout = 5000): Promise<Element> => {
      return new Promise((resolve, reject) => {
        const element = document.querySelector(selector);
        if (element) {
          resolve(element);
          return;
        }

        const observer = new MutationObserver(() => {
          const element = document.querySelector(selector);
          if (element) {
            observer.disconnect();
            resolve(element);
          }
        });

        observer.observe(document.body, {
          childList: true,
          subtree: true,
        });

        setTimeout(() => {
          observer.disconnect();
          reject(new Error(`Element ${selector} not found after ${timeout}ms`));
        }, timeout);
      });
    };

    // Step 1: Sidebar completa
    tour.addStep({
      id: "sidebar-nav",
      title: "Navegação",
      text: "Use a barra lateral para navegar entre as funcionalidades do ProntuAI. Vamos conhecer cada seção!",
      attachTo: {
        element: "[data-tour='sidebar-completa']",
        on: "right",
      },
      buttons: [
        {
          text: "Próximo",
          action: tour.next,
        },
      ],
    });

    // Step 2: Enviar Exames
    tour.addStep({
      id: "enviar-exames",
      title: "Enviar Exames",
      text: "Faça upload de documentos médicos para análise automática via OCR e validação contra o sistema BRNET.",
      attachTo: {
        element: "[data-tour='enviar exames']",
        on: "right",
      },
      buttons: [
        {
          text: "Anterior",
          action: tour.back,
          classes: "shepherd-button-secondary",
        },
        {
          text: "Próximo",
          action: tour.next,
        },
      ],
      when: {
        show: async function() {
          try {
            await waitForElement("[data-tour='enviar exames']", 3000);
          } catch (error) {
            console.error("Elemento enviar exames não encontrado:", error);
          }
        },
      },
    });

    // Step 3: Checagem
    tour.addStep({
      id: "checagem",
      title: "Checagem",
      text: "Revise documentos rejeitados e aprove ou rejeite manualmente com justificativas detalhadas.",
      attachTo: {
        element: "[data-tour='checagem']",
        on: "right",
      },
      buttons: [
        {
          text: "Anterior",
          action: tour.back,
          classes: "shepherd-button-secondary",
        },
        {
          text: "Próximo",
          action: tour.next,
        },
      ],
      when: {
        show: async function() {
          try {
            await waitForElement("[data-tour='checagem']", 3000);
          } catch (error) {
            console.error("Elemento checagem não encontrado:", error);
          }
        },
      },
    });

    // Step 4: Insights
    tour.addStep({
      id: "insights",
      title: "Insights",
      text: "Consulte nossa base de conhecimento com perguntas sobre medicina ocupacional e normas reguladoras.",
      attachTo: {
        element: "[data-tour='insights']",
        on: "right",
      },
      buttons: [
        {
          text: "Anterior",
          action: tour.back,
          classes: "shepherd-button-secondary",
        },
        {
          text: "Próximo",
          action: tour.next,
        },
      ],
      when: {
        show: async function() {
          try {
            await waitForElement("[data-tour='insights']", 3000);
          } catch (error) {
            console.error("Elemento insights não encontrado:", error);
          }
        },
      },
    });

    // Step 5: Central de Ajuda
    tour.addStep({
      id: "ajuda",
      title: "Central de Ajuda",
      text: "Acesse a central de ajuda com perguntas frequentes e informações de suporte. Use a busca para encontrar respostas rapidamente!",
      attachTo: {
        element: "[data-tour='ajuda']",
        on: "right",
      },
      buttons: [
        {
          text: "Anterior",
          action: tour.back,
          classes: "shepherd-button-secondary",
        },
        {
          text: "Concluir",
          action: tour.complete,
        },
      ],
      when: {
        show: async function() {
          try {
            await waitForElement("[data-tour='ajuda']", 3000);
          } catch (error) {
            console.error("Elemento ajuda não encontrado:", error);
          }
        },
      },
    });

    tourRef.current = tour;
    tour.start();
  };

  return (
    <Button
      variant="outline"
      size="sm"
      className="w-full justify-start"
      onClick={startTour}
    >
      <RiMapPinLine size={16} className="mr-2" />
      Iniciar Tour
    </Button>
  );
}
