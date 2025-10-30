"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { HelpCircleIcon, FileTextIcon, CheckCircleIcon, AlertCircleIcon, SearchIcon } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { useState, useMemo } from "react";

type FaqItem = {
  value: string;
  icon: React.ReactNode;
  title: string;
  content: React.ReactNode;
};

export function CentroAjudaDialog() {
  const [searchQuery, setSearchQuery] = useState("");

  const faqItems: FaqItem[] = useMemo(() => [
    {
      value: "item-1",
      icon: <FileTextIcon size={18} className="text-blue-600" />,
      title: "Como fazer upload de documentos?",
      content: (
        <ol className="list-decimal list-inside space-y-2 text-sm">
          <li>Clique no botão &ldquo;Adicionar Arquivo&rdquo; ou arraste o arquivo para a área indicada</li>
          <li>Selecione um ou mais documentos (PDF, imagem, etc.)</li>
          <li>Aguarde o processamento automático via OCR</li>
          <li>O sistema irá comparar automaticamente com os dados do BRNET</li>
        </ol>
      )
    },
    {
      value: "item-2",
      icon: <CheckCircleIcon size={18} className="text-green-600" />,
      title: "O que significa cada status de documento?",
      content: (
        <div className="space-y-3 text-sm">
          <div>
            <strong className="text-yellow-600">Pendente:</strong> Documento aguardando validação manual
          </div>
          <div>
            <strong className="text-green-600">Aprovado:</strong> Documento validado e aprovado
          </div>
          <div>
            <strong className="text-red-600">Rejeitado:</strong> Documento rejeitado por inconsistências
          </div>
        </div>
      )
    },
    {
      value: "item-3",
      icon: <AlertCircleIcon size={18} className="text-amber-600" />,
      title: "Por que meu documento foi rejeitado?",
      content: (
        <>
          <p className="text-sm">
            Documentos podem ser rejeitados por diversos motivos:
          </p>
          <ul className="list-disc list-inside space-y-1 mt-2 text-sm">
            <li>Exames obrigatórios não encontrados no documento</li>
            <li>CPF não identificado ou inválido</li>
            <li>Documento ilegível ou de baixa qualidade</li>
            <li>Incompatibilidade com as exigências do BRNET</li>
          </ul>
          <p className="text-sm mt-2">
            Verifique o motivo específico na página de Checagem.
          </p>
        </>
      )
    },
    {
      value: "item-4",
      icon: <FileTextIcon size={18} className="text-indigo-600" />,
      title: "Como funciona a comparação de exames?",
      content: (
        <>
          <p className="text-sm">
            O ProntuAI utiliza inteligência artificial para comparar os exames encontrados no documento com os exames autorizados no sistema BRNET:
          </p>
          <ul className="list-disc list-inside space-y-1 mt-2 text-sm">
            <li>OCR extrai os nomes dos exames do documento</li>
            <li>Sistema busca exames autorizados no BRNET via CPF</li>
            <li>IA compara e identifica equivalências (ex: &ldquo;hemograma completo&rdquo; = &ldquo;exame de sangue&rdquo;)</li>
            <li>Gera relatório de compatibilidade automático</li>
          </ul>
        </>
      )
    },
    {
      value: "item-5",
      icon: <CheckCircleIcon size={18} className="text-blue-600" />,
      title: "Preciso de suporte adicional",
      content: (
        <>
          <p className="text-sm">
            Entre em contato com o suporte técnico:
          </p>
          <ul className="list-none space-y-1 mt-2 text-sm">
            <li><strong>Email:</strong> suporte@grupobrmed.com.br</li>
            <li><strong>Telefone:</strong> (85) 3000-0000</li>
            <li><strong>Horário:</strong> Segunda a Sexta, 8h às 18h</li>
          </ul>
        </>
      )
    }
  ], []);

  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) return faqItems;

    const query = searchQuery.toLowerCase();
    return faqItems.filter(item =>
      item.title.toLowerCase().includes(query)
    );
  }, [faqItems, searchQuery]);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="w-full justify-start" data-tour="ajuda">
          <HelpCircleIcon size={16} className="mr-2" />
          Central de Ajuda
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Central de Ajuda - ProntuAI</DialogTitle>
          <DialogDescription>
            Encontre respostas para as perguntas mais frequentes sobre o sistema
          </DialogDescription>
        </DialogHeader>

        <div className="relative mb-4">
          <SearchIcon size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Buscar perguntas..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>

        <div className="overflow-y-auto flex-1 pr-2">
          {filteredItems.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>Nenhuma pergunta encontrada para &ldquo;{searchQuery}&rdquo;</p>
            </div>
          ) : (
            <Accordion type="single" collapsible className="w-full">
              {filteredItems.map((item) => (
                <AccordionItem key={item.value} value={item.value}>
                  <AccordionTrigger className="text-left">
                    <div className="flex items-center gap-2">
                      {item.icon}
                      <span>{item.title}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    {item.content}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
