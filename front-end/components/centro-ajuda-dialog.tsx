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
import { HelpCircleIcon, FileTextIcon, CheckCircleIcon, AlertCircleIcon } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

export function CentroAjudaDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="w-full justify-start">
          <HelpCircleIcon size={16} className="mr-2" />
          Central de Ajuda
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Central de Ajuda - ProntuAI</DialogTitle>
          <DialogDescription>
            Encontre respostas para as perguntas mais frequentes sobre o sistema
          </DialogDescription>
        </DialogHeader>

        <Accordion type="single" collapsible className="w-full">
          <AccordionItem value="item-1">
            <AccordionTrigger className="text-left">
              <div className="flex items-center gap-2">
                <FileTextIcon size={18} className="text-blue-600" />
                <span>Como fazer upload de documentos?</span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <ol className="list-decimal list-inside space-y-2 text-sm">
                <li>Clique no botão "Adicionar Arquivo" ou arraste o arquivo para a área indicada</li>
                <li>Selecione um ou mais documentos (PDF, imagem, etc.)</li>
                <li>Aguarde o processamento automático via OCR</li>
                <li>O sistema irá comparar automaticamente com os dados do BRNET</li>
              </ol>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="item-2">
            <AccordionTrigger className="text-left">
              <div className="flex items-center gap-2">
                <CheckCircleIcon size={18} className="text-green-600" />
                <span>O que significa cada status de documento?</span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
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
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="item-3">
            <AccordionTrigger className="text-left">
              <div className="flex items-center gap-2">
                <AlertCircleIcon size={18} className="text-amber-600" />
                <span>Por que meu documento foi rejeitado?</span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
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
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="item-4">
            <AccordionTrigger className="text-left">
              <div className="flex items-center gap-2">
                <FileTextIcon size={18} className="text-indigo-600" />
                <span>Como funciona a comparação de exames?</span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <p className="text-sm">
                O ProntuAI utiliza inteligência artificial para comparar os exames encontrados no documento com os exames autorizados no sistema BRNET:
              </p>
              <ul className="list-disc list-inside space-y-1 mt-2 text-sm">
                <li>OCR extrai os nomes dos exames do documento</li>
                <li>Sistema busca exames autorizados no BRNET via CPF</li>
                <li>IA compara e identifica equivalências (ex: "hemograma completo" = "exame de sangue")</li>
                <li>Gera relatório de compatibilidade automático</li>
              </ul>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="item-5">
            <AccordionTrigger className="text-left">
              <div className="flex items-center gap-2">
                <CheckCircleIcon size={18} className="text-blue-600" />
                <span>Preciso de suporte adicional</span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <p className="text-sm">
                Entre em contato com o suporte técnico:
              </p>
              <ul className="list-none space-y-1 mt-2 text-sm">
                <li><strong>Email:</strong> suporte@grupobrmed.com.br</li>
                <li><strong>Telefone:</strong> (85) 3000-0000</li>
                <li><strong>Horário:</strong> Segunda a Sexta, 8h às 18h</li>
              </ul>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </DialogContent>
    </Dialog>
  );
}
