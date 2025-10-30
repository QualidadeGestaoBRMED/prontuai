"use client";

import { useState, useEffect } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import UserDropdown from "@/components/user-dropdown";
import Chat from "@/components/chat";
import { Message } from "@/components/file-uploader";
import { TabelaComparacaoItem } from "@/components/exames-comparativo-table";

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [aiTyping, setAiTyping] = useState("");

  // Carregar histórico do localStorage ao montar
  useEffect(() => {
    const saved = localStorage.getItem("insights_history");
    if (saved) {
      try {
        const parsedMessages: Message[] = JSON.parse(saved);
        // Re-parse content for "tabela-exames" messages if it's a string
        const processedMessages = parsedMessages.map((msg) => {
          if (msg.type === "tabela-exames" && typeof msg.content === "string") {
            try {
              return {
                ...msg,
                content: JSON.parse(msg.content) as TabelaComparacaoItem[],
              };
            } catch (e) {
              console.error(
                "Failed to parse tabela-exames content from localStorage:",
                e
              );
              return msg;
            }
          }
          return msg;
        });
        setMessages(processedMessages);
      } catch {
        localStorage.removeItem("insights_history");
      }
    }
  }, []);

  // Salvar histórico no localStorage sempre que messages mudar
  useEffect(() => {
    localStorage.setItem("insights_history", JSON.stringify(messages));
  }, [messages]);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="bg-sidebar group/sidebar-inset">
        <header className="flex h-16 shrink-0 items-center gap-2 px-4 md:px-6 lg:px-8 bg-sidebar text-sidebar-foreground relative before:absolute before:inset-y-3 before:-left-px before:w-px before:bg-gradient-to-b before:from-white/5 before:via-white/15 before:to-white/5 before:z-50">
          <SidebarTrigger className="-ms-2 text-sidebar-foreground hover:text-sidebar-foreground/70" />
          <h1 className="text-lg font-semibold">Insights e FAQ</h1>
          <div className="flex items-center gap-2 ml-auto">
            <UserDropdown />
          </div>
        </header>

        <div className="flex flex-col h-[calc(100svh-4rem)] bg-[hsl(240_5%_92.16%)] md:rounded-s-3xl md:group-peer-data-[state=collapsed]/sidebar-inset:rounded-s-none transition-all ease-in-out duration-300 overflow-hidden">
          <div className="flex flex-1 min-h-0">
            <Chat
              messages={messages}
              setMessages={setMessages}
              aiTyping={aiTyping}
              setAiTyping={setAiTyping}
            />
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
