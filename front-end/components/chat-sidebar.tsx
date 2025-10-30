"use client"

import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ChatMessage } from "@/components/chat-message"
import { useRef, useEffect, useState } from "react"
import { Bot, Square, RefreshCw, MessageSquare } from "lucide-react"
import { cn } from "@/lib/utils"

export interface Message {
  content: string
  isUser: boolean
  type?: "text"
  skipTyping?: boolean
}

interface ChatSidebarProps {
  initialMessage?: string
  className?: string
}

export function ChatSidebar({ initialMessage, className }: ChatSidebarProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)
  const [aiTyping, setAiTyping] = useState("")
  const abortControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, aiTyping])

  useEffect(() => {
    if (initialMessage) {
      setMessages([
        {
          content: initialMessage,
          isUser: false,
          skipTyping: true,
        },
      ])
    }
  }, [initialMessage])

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return

    const userMessage = inputMessage.trim()
    setInputMessage("")
    setIsLoading(true)

    const newConversation = [...messages, { content: userMessage, isUser: true }]
    setMessages(newConversation)

    abortControllerRef.current = new AbortController()

    try {
      const pergunta = userMessage
      const recentHistory = messages.slice(-10)
      const historico = recentHistory.map((msg) => ({
        role: msg.isUser ? "user" : "assistant",
        content: msg.content,
      }))

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
      })

      if (!response.ok || !response.body) {
        throw new Error(`Error: ${response.statusText}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let fullResponse = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        fullResponse += decoder.decode(value, { stream: true })
      }

      const responseJson = JSON.parse(fullResponse)
      const aiContent =
        responseJson.resposta_gerada || "Desculpe, não foi possível gerar uma resposta."

      setIsLoading(false)

      // Typewriter effect
      let i = 0
      function typeWriter() {
        setAiTyping(aiContent.slice(0, i))
        if (i < aiContent.length) {
          i++
          setTimeout(typeWriter, 20)
        } else {
          setMessages((prev) => [...prev, { content: aiContent, isUser: false }])
          setAiTyping("")
        }
      }
      typeWriter()
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        setMessages((prev) => [
          ...prev,
          { content: "Operação cancelada pelo usuário.", isUser: false },
        ])
      } else {
        console.error(err)
        setMessages((prev) => [
          ...prev,
          { content: "Desculpe, ocorreu um erro. Tente novamente.", isUser: false },
        ])
      }
      setIsLoading(false)
    } finally {
      setIsCancelling(false)
      abortControllerRef.current = null
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleCancelRun = async () => {
    if (!isLoading || isCancelling) return

    setIsCancelling(true)
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }

  const handleClearHistory = () => {
    setMessages(
      initialMessage
        ? [
            {
              content: initialMessage,
              isUser: false,
              skipTyping: true,
            },
          ]
        : []
    )
  }

  return (
    <div
      className={cn(
        "flex flex-col h-full bg-muted/30 border-l",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 p-4 border-b bg-background/50">
        <div className="flex items-center gap-2">
          <MessageSquare className="size-5 text-primary" />
          <h3 className="font-semibold text-sm">FAQ Assistente</h3>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-8"
          onClick={handleClearHistory}
          disabled={messages.length === 0}
        >
          <RefreshCw className="size-4" />
          <span className="sr-only">Limpar histórico</span>
        </Button>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4">
          {messages.length === 0 && !initialMessage && (
            <div className="text-center text-sm text-muted-foreground py-8">
              <MessageSquare className="size-12 mx-auto mb-3 opacity-20" />
              <p>Pergunte qualquer coisa</p>
              <p className="text-xs mt-1">sobre saúde ocupacional</p>
            </div>
          )}

          {messages.map((message, index) => (
            <ChatMessage key={index} isUser={message.isUser}>
              <p className="text-sm">{message.content}</p>
            </ChatMessage>
          ))}

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
              <span className="text-sm">{aiTyping}</span>
            </ChatMessage>
          )}

          <div ref={messagesEndRef} aria-hidden="true" />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="p-4 border-t bg-background/50">
        <div className="space-y-2">
          <div className="relative rounded-lg border bg-background">
            <textarea
              className="flex min-h-[80px] w-full bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none resize-none"
              placeholder="Pergunte algo..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyPress}
              disabled={isLoading}
            />
          </div>

          <div className="flex items-center justify-between gap-2">
            {isLoading && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-8"
                onClick={handleCancelRun}
                disabled={isCancelling}
              >
                <Square className="size-3 mr-1" />
                {isCancelling ? "Cancelando..." : "Parar"}
              </Button>
            )}

            <div className={cn("flex-1", !isLoading && "flex justify-end")}>
              <Button
                size="sm"
                className="h-8"
                onClick={handleSendMessage}
                disabled={isLoading || !inputMessage.trim()}
              >
                <Bot className={cn("size-4", inputMessage.trim() && "mr-1.5")} />
                {inputMessage.trim() && "Perguntar"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
