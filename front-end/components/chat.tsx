"use client";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  RiShining2Line,
  RiAttachment2,
  RiMicLine,
  RiLeafLine,
} from "@remixicon/react";
import { ChatMessage } from "@/components/chat-message";
import { useRef, useEffect, useState } from "react";
import { Bot, Square, RefreshCw  } from "lucide-react";
import { cn } from "@/lib/utils";
import ExamesComparativoTable, { TabelaComparacaoItem } from "@/components/exames-comparativo-table";
import { Message } from "@/components/file-uploader";

export default function Chat({
  messages,
  setMessages,
  aiTyping,
  setAiTyping,
}: {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  aiTyping: string;
  setAiTyping: React.Dispatch<React.SetStateAction<string>>;
}) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, aiTyping]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage = inputMessage.trim();
    setInputMessage("");
    setIsLoading(true);

    const newConversation = [...messages, { content: userMessage, isUser: true }];
    setMessages(newConversation);

    abortControllerRef.current = new AbortController();

    try {
      const pergunta = userMessage;
      const recentHistory = messages.slice(-10);
      const historico = recentHistory.map(msg => ({
        role: msg.isUser ? "user" : "assistant",
        content: msg.content,
      }));

      const response = await fetch("http://localhost:8000/v1/faq", { 

        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          pergunta,
          historico,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`Error: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullResponse = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullResponse += decoder.decode(value, { stream: true });
      }

      const responseJson = JSON.parse(fullResponse);
      const aiContent = responseJson.resposta_gerada || "Desculpe, não foi possível gerar uma resposta.";
      
      setIsLoading(false); // Network loading is done, now start typing effect.

      // Typewriter effect
      let i = 0;
      function typeWriter() {
        setAiTyping(aiContent.slice(0, i));
        if (i < aiContent.length) {
          i++;
          setTimeout(typeWriter, 20); // Adjust typing speed here
        } else {
          setMessages((prev) => [...prev, { content: aiContent, isUser: false }]);
          setAiTyping("");
        }
      }
      typeWriter();

    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        setMessages((prev) => [
          ...prev,
          { content: "Operação cancelada pelo usuário.", isUser: false },
        ]);
      } else {
        console.error(err);
        setMessages((prev) => [
          ...prev,
          { content: "Desculpe, ocorreu um erro. Tente novamente.", isUser: false },
        ]);
      }
      setIsLoading(false);
    } finally {
      setIsCancelling(false);
      abortControllerRef.current = null;
    }
  };
  
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCancelRun = async () => {
    if (!isLoading || isCancelling) return;

    setIsCancelling(true);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  return (
    <ScrollArea className="flex-1 [&>div>div]:h-full w-full shadow-md md:rounded-s-[inherit] min-[1024px]:rounded-e-3xl bg-background">
      <div className="h-full flex flex-col px-4 md:px-6 lg:px-8">
        {/* Header */}
        <div className="py-5 bg-background sticky top-0 z-10 before:absolute before:inset-x-0 before:bottom-0 before:h-px before:bg-gradient-to-r before:from-black/[0.06] before:via-black/10 before:to-black/[0.06]">
          <div className="flex items-center justify-between gap-2">
            <Breadcrumb>
              <BreadcrumbList className="sm:gap-1.5">
                <BreadcrumbItem>
                  <BreadcrumbLink href="#">Comparativos</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Chat</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
            <div className="flex items-center gap-1 -my-2 -me-2">
              <Button variant="ghost" className="px-2" onClick={() => {
                localStorage.removeItem("chat_history");
                setMessages([]);
              }}>
                <RefreshCw
                  className="text-current size-4"
                  size={16}
                  aria-hidden="true"
                />
                <span className="max-sm:sr-only">Limpar Histórico</span>
              </Button>
            </div>
          </div>
        </div>
        {/* Chat */}
        <div className="relative grow">
          <div className="max-w-3xl mx-auto mt-6 space-y-6">
            <div className="text-center my-8">
              <div className="inline-flex items-center bg-white rounded-full border border-black/[0.08] shadow-xs text-xs font-medium py-1 px-3 text-foreground/80">
                <RiShining2Line
                  className="me-1.5 text-muted-foreground/70 -ms-1"
                  size={14}
                  aria-hidden="true"
                />
                Hoje
              </div>
            </div>
            {messages.map((message, index) => {
              // Detecta JSON válido em mensagens de texto (mesmo dentro de blocos markdown)
              if (
                message.type !== "tabela-exames" &&
                typeof message.content === "string"
              ) {
                let jsonString = message.content.trim();
                // Remove blocos markdown e espaços extras
                jsonString = jsonString.replace(/^```json/i, "");
                jsonString = jsonString.replace(/^```/, "");
                jsonString = jsonString.replace(/```$/, "");
                jsonString = jsonString.trim();
                // Tenta parsear se parece um array
                if (jsonString.startsWith("[") && jsonString.endsWith("]")) {
                  try {
                    const tabela = JSON.parse(jsonString);
                    if (Array.isArray(tabela) && tabela[0]?.exame) {
                      return (
                        <ChatMessage key={index} isUser={message.isUser} isTableMessage={true}>
                          <ExamesComparativoTable tabela={tabela} />
                        </ChatMessage>
                      );
                    }
                  } catch (e) {
                    console.warn("Falha ao parsear JSON para tabela:", e, jsonString);
                  }
                }
              }
              return (
                <ChatMessage key={index} isUser={message.isUser}>
                  {message.type === "tabela-exames" ? (
                    (() => {
                      console.log("Raw message.content for tabela-exames:", message.content);
                      let tabela: TabelaComparacaoItem[] | null = null;
                      if (Array.isArray(message.content)) {
                        tabela = message.content as TabelaComparacaoItem[];
                      } else if (typeof message.content === "string") {
                        try {
                          tabela = JSON.parse(message.content) as TabelaComparacaoItem[];
                        } catch (e) {
                          console.error("Failed to parse tabela-exames content from string:", e);
                        }
                      }
                      if (tabela) {
                        console.log("Rendering ExamesComparativoTable with:", tabela);
                        return <ExamesComparativoTable tabela={tabela} />;
                      }
                      return <p>Erro ao exibir tabela de exames.</p>;
                    })()
                  ) : (
                    <p>{message.content}</p>
                  )}
                </ChatMessage>
              );
            })}
            {isLoading && !aiTyping && (
              <ChatMessage>
                <div className="flex items-center gap-1 h-6">
                  <span className="inline-block w-2 h-2 rounded-full bg-black animate-bounce [animation-delay:0ms]"></span>
                  <span className="inline-block w-2 h-2 rounded-full bg-neutral-400 animate-bounce [animation-delay:150ms]"></span>
                  <span className="inline-block w-2 h-2 rounded-full bg-neutral-200 animate-bounce [animation-delay:300ms]"></span>
                </div>
              </ChatMessage>
            )}
            {aiTyping && (
              <ChatMessage>
                <span>{aiTyping}</span>
              </ChatMessage>
            )}
            <div ref={messagesEndRef} aria-hidden="true" />
          </div>
        </div>
        {/* Footer */}
        <div className="sticky bottom-0 pt-4 md:pt-8 z-50">
          <div className="max-w-3xl mx-auto bg-background rounded-[20px] pb-4 md:pb-8">
            <div className="relative rounded-[20px] border border-transparent bg-muted transition-colors focus-within:bg-muted/50 focus-within:border-input has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 [&:has(input:is(:disabled))_*]:pointer-events-none">
              <textarea
                className="flex sm:min-h-[84px] w-full bg-transparent px-4 py-3 text-[15px] leading-relaxed text-foreground placeholder:text-muted-foreground/70 focus-visible:outline-none [resize:none]"
                placeholder="Me pergunte qualquer coisa..."
                aria-label="Enter your prompt"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyPress}
                disabled={isLoading}
              />
              {/* Textarea buttons */}
              <div className="flex items-center justify-between gap-2 p-3">
                {/* Left buttons */}
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    className="rounded-full size-8 border-none hover:bg-background hover:shadow-md transition-[box-shadow]"
                  >
                    <RiAttachment2
                      className="text-muted-foreground/70 size-5"
                      size={20}
                      aria-hidden="true"
                    />
                    <span className="sr-only">Attach</span>
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="rounded-full size-8 border-none hover:bg-background hover:shadow-md transition-[box-shadow]"
                  >
                    <RiMicLine
                      className="text-muted-foreground/70 size-5"
                      size={20}
                      aria-hidden="true"
                    />
                    <span className="sr-only">Audio</span>
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="rounded-full size-8 border-none hover:bg-background hover:shadow-md transition-[box-shadow]"
                  >
                    <RiLeafLine
                      className="text-muted-foreground/70 size-5"
                      size={20}
                      aria-hidden="true"
                    />
                    <span className="sr-only">Action</span>
                  </Button>
                </div>
                {/* Right buttons */}
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    className={cn(
                      "rounded-full size-8 border-none transition-all duration-200",
                      isLoading 
                        ? "hover:bg-red-100 hover:shadow-md cursor-pointer hover:scale-105" 
                        : "hover:bg-background hover:shadow-md"
                    )}
                    onClick={isLoading && !isCancelling ? handleCancelRun : undefined}
                    disabled={isCancelling}
                  >
                    {isLoading ? (
                      <Square
                        className={cn(
                          "size-5",
                          isCancelling 
                            ? "text-orange-500 animate-pulse" 
                            : "text-muted-foreground/70"
                        )}
                        size={20}
                        aria-hidden="true"
                      />
                    ) : (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="16"
                        height="16"
                        fill="none"
                      >
                        <g clipPath="url(#icon-a)">
                          <path
                            fill="url(#icon-b)"
                            d="m8 .333 2.667 5 5 2.667-5 2.667-2.667 5-2.667-5L.333 8l5-2.667L8 .333Z"
                          />
                          <path
                            stroke="#451A03"
                            strokeOpacity=".04"
                            d="m8 1.396 2.225 4.173.072.134.134.071L14.604 8l-4.173 2.226-.134.071-.072.134L8 14.604l-2.226-4.173-.071-.134-.134-.072L1.396 8l4.173-2.226.134-.071.071-.134L8 1.396Z"
                          />
                        </g>
                        <defs>
                          <linearGradient
                            id="icon-b"
                            x1="8"
                            x2="8"
                            y1=".333"
                            y2="15.667"
                            gradientUnits="userSpaceOnUse"
                          >
                            <stop stopColor="#FDE68A" />
                            <stop offset="1" stopColor="#F59E0B" />
                          </linearGradient>
                          <clipPath id="icon-a">
                            <path fill="#fff" d="M0 0h16v16H0z" />
                          </clipPath>
                        </defs>
                      </svg>
                    )}
                    <span className="sr-only">
                      {isCancelling ? "Cancelando..." : isLoading ? "Stop" : "Generate"}
                    </span>
                  </Button>

                    <Button
                      size="lg"
                      variant="default"
                      className="
                        group 
                        relative 
                        inline-flex 
                        items-center 
                        justify-center 
                        overflow-hidden
                        px-6 py-2
                      "
                      onClick={handleSendMessage}
                      disabled={isLoading}
                    >
                        {/* Texto centralizado e que só se move no hover */}
                        <span
                          className="
                            text-sm
                            transition-transform 
                            duration-200 
                            group-hover:-translate-x-3
                          "
                        >
                          {isLoading ? "" : "Perguntar"}
                        </span>

                        {/* Ícone absolutamente posicionado, invisível até o hover */}
                        <Bot
                          className={cn(
                            "pb-1 size-6 absolute top-1/2 right-2 -translate-y-1/2 transition-all duration-200",
                            isLoading ? "opacity-100 right-3" : "opacity-0 group-hover:opacity-100"
                          )}
                        />
                    </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ScrollArea>
  );
}
