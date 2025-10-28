"use client";

import { useState, useEffect } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import UserDropdown from "@/components/user-dropdown";
import {
  SettingsPanelProvider,
  SettingsPanel,
} from "@/components/settings-panel";
import Chat from "@/components/chat";
import { Message } from "@/components/file-uploader";
import { TabelaComparacaoItem } from "@/components/exames-comparativo-table";

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [aiTyping, setAiTyping] = useState("");
  const [systemQueue, setSystemQueue] = useState<Message[]>([]);
  const [isTypingSystem, setIsTypingSystem] = useState(false);

  // Processa a fila de mensagens do sistema
  useEffect(() => {
    if (!isTypingSystem && systemQueue.length > 0) {
      setIsTypingSystem(true);
      const msg = systemQueue[0];
      // Só pula aiTyping para type: "tabela-exames"
      if (msg.type === "tabela-exames") {
        setMessages((prev) => [...prev, msg]);
        setIsTypingSystem(false);
        setSystemQueue((q) => q.slice(1));
      } else {
        let i = 0;
        function typeWriter() {
          setAiTyping((msg.content as string).slice(0, i));
          if (i < (msg.content as string).length) {
            i++;
            setTimeout(typeWriter, 20);
          } else {
            setMessages((prev) => [...prev, msg]);
            setAiTyping("");
            setIsTypingSystem(false);
            setSystemQueue((q) => q.slice(1));
          }
        }
        typeWriter();
      }
    }
  }, [systemQueue, isTypingSystem]);

  // Função para adicionar mensagem do sistema à fila
  const onSystemMessage = (msg: Message) => {
    setSystemQueue((q) => [...q, msg]);
  };

  useEffect(() => {
    // Log do localStorage para depuração
    try {
      const chatHistory = localStorage.getItem("chat_history");
      console.log("[DEBUG] Conteúdo do localStorage[chat_history]:", chatHistory);
    } catch {
      console.warn("[DEBUG] Erro ao acessar localStorage");
    }
  }, [messages]);

  // Carregar histórico do localStorage ao montar
  useEffect(() => {
    const saved = localStorage.getItem("chat_history");
    if (saved) {
      try {
        const parsedMessages: Message[] = JSON.parse(saved);
        // Re-parse content for "tabela-exames" messages if it's a string
        const processedMessages = parsedMessages.map(msg => {
          if (msg.type === "tabela-exames" && typeof msg.content === "string") {
            try {
              return { ...msg, content: JSON.parse(msg.content) as TabelaComparacaoItem[] };
            } catch (e) {
              console.error("Failed to parse tabela-exames content from localStorage:", e);
              return msg; // Return original message if parsing fails
            }
          }
          return msg;
        });
        setMessages(processedMessages);
      } catch {
        localStorage.removeItem("chat_history");
      }
    }
  }, []);

  // Salvar histórico no localStorage sempre que messages mudar
  useEffect(() => {
    localStorage.setItem("chat_history", JSON.stringify(messages));
  }, [messages]);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="bg-sidebar group/sidebar-inset">
        <header className=" flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
          <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
          <div className="flex items-center gap-8 ml-auto">
            <nav className="flex items-center text-sm font-medium max-sm:hidden">
              <a
                className="text-sidebar-foreground/50 hover:text-sidebar-foreground/70 transition-colors [&[aria-current]]:text-sidebar-foreground before:content-['/'] before:px-4 before:text-sidebar-foreground/30 first:before:hidden"
                href="#"
                aria-current
              >
                Comparativos
              </a>
              <a
                className="text-sidebar-foreground/50 hover:text-sidebar-foreground/70 transition-colors [&[aria-current]]:text-sidebar-foreground before:content-['/'] before:px-4 before:text-sidebar-foreground/30 first:before:hidden"
                href="#"
              >
                Dashboard
              </a>
              <a
                className="text-sidebar-foreground/50 hover:text-sidebar-foreground/70 transition-colors [&[aria-current]]:text-sidebar-foreground before:content-['/'] before:px-4 before:text-sidebar-foreground/30 first:before:hidden"
                href="#"
              >
                Docs
              </a>
              <a
                className="text-sidebar-foreground/50 hover:text-sidebar-foreground/70 transition-colors [&[aria-current]]:text-sidebar-foreground before:content-['/'] before:px-4 before:text-sidebar-foreground/30 first:before:hidden"
                href="#"
              >
                Referências
              </a>
            </nav>
            <UserDropdown />
          </div>
        </header>
        <SettingsPanelProvider>
          <div className="flex h-[calc(100svh-4rem)] bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300">
            <Chat messages={messages} setMessages={setMessages} aiTyping={aiTyping} setAiTyping={setAiTyping} />
            <SettingsPanel onSystemMessage={onSystemMessage} />
          </div>
        </SettingsPanelProvider>
      </SidebarInset>
    </SidebarProvider>
  );
}
