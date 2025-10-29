"use client";

import {
  AlertCircleIcon,
  FileArchiveIcon,
  FileIcon,
  FileSpreadsheetIcon,
  FileTextIcon,
  FileUpIcon,
  HeadphonesIcon,
  ImageIcon,
  VideoIcon,
  XIcon,
  ArrowRightIcon,
  TrashIcon,
  Loader2,
} from "lucide-react"
import { useState } from "react"

import {
  formatBytes,
  useFileUpload,
} from "@/hooks/use-file-upload"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import type { TabelaComparacaoItem } from "@/components/exames-comparativo-table";

export type Message =
  | { content: string; isUser: boolean; type?: "text"; skipTyping?: boolean }
  | { content: TabelaComparacaoItem[] | { exames_ocr: string[]; exames_brnet: string[] } | string; isUser: boolean; type: "tabela-exames"; skipTyping?: boolean };

const getFileIcon = (file: { file: File | { type: string; name: string } }) => {
  const fileType = file.file instanceof File ? file.file.type : file.file.type
  const fileName = file.file instanceof File ? file.file.name : file.file.name

  if (
    fileType.includes("pdf") ||
    fileName.endsWith(".pdf") ||
    fileType.includes("word") ||
    fileName.endsWith(".doc") ||
    fileName.endsWith(".docx")
  ) {
    return <FileTextIcon className="size-4 opacity-60" />
  } else if (
    fileType.includes("zip") ||
    fileType.includes("archive") ||
    fileName.endsWith(".zip") ||
    fileName.endsWith(".rar")
  ) {
    return <FileArchiveIcon className="size-4 opacity-60" />
  } else if (
    fileType.includes("excel") ||
    fileName.endsWith(".xls") ||
    fileName.endsWith(".xlsx")
  ) {
    return <FileSpreadsheetIcon className="size-4 opacity-60" />
  } else if (fileType.includes("video/")) {
    return <VideoIcon className="size-4 opacity-60" />
  } else if (fileType.includes("audio/")) {
    return <HeadphonesIcon className="size-4 opacity-60" />
  } else if (fileType.startsWith("image/")) {
    return <ImageIcon className="size-4 opacity-60" />
  }
  return <FileIcon className="size-4 opacity-60" />
}

export default function Component({ onSystemMessage }: { onSystemMessage?: (msg: Message) => void }) {
  const maxSize = 100 * 1024 * 1024 // 10MB default
  const maxFiles = 10
  const [isImporting, setIsImporting] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressMessage, setProgressMessage] = useState("")

  const [
    { files, isDragging, errors },
    {
      handleDragEnter,
      handleDragLeave,
      handleDragOver,
      handleDrop,
      openFileDialog,
      removeFile,
      clearFiles,
      getInputProps,
    },
  ] = useFileUpload({
    multiple: true,
    maxFiles,
    maxSize,
  })

  // Função para importar o arquivo para o backend com SSE
  const handleImport = async () => {
    if (files.length === 0 || isImporting) return;

    setIsImporting(true);
    setProgress(0);
    setProgressMessage("Preparando envio...");
    onSystemMessage?.({ type: "text", content: "Recebi seu arquivo, aguarde um pouquinho enquanto analiso...", isUser: false });

    try {
      const formData = new FormData();
      let fileToSend = files[0].file;
      const fileName = files[0].file.name;

      if (!(fileToSend instanceof File)) {
        try {
          const fileMeta = files[0].file as {
            url: string;
            name: string;
            type: string;
          };
          const response = await fetch(fileMeta.url);
          const blob = await response.blob();
          fileToSend = new File([blob], fileMeta.name, { type: fileMeta.type });
        } catch {
          console.error("❌ Erro ao obter arquivo remoto");
          onSystemMessage?.({ type: "text", content: "❌ Erro ao obter arquivo remoto.", isUser: false });
          setIsImporting(false);
          setProgressMessage("");
          return;
        }
      }

      formData.append("arquivo", fileToSend, fileName);
      formData.append("exames_obrigatorios", JSON.stringify([]));

      console.log("📤 Enviando arquivo para processamento completo com SSE...");

      const uploadRes = await fetch("http://localhost:8000/v1/processar-documento-stream", {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        const errorData = await uploadRes.json();
        console.error("❌ Erro do backend:", errorData.detail || errorData);
        onSystemMessage?.({ type: "text", content: `❌ Erro no processamento: ${errorData.detail || JSON.stringify(errorData)}`, isUser: false });
        setIsImporting(false);
        setProgressMessage("");
        return;
      }

      const reader = uploadRes.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      if (!reader) {
        throw new Error("Não foi possível ler a resposta do servidor");
      }

      // Ler eventos SSE
      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          console.log("✅ Stream finalizado");
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonData = line.slice(6);
            try {
              const event = JSON.parse(jsonData);
              console.log("📨 Evento SSE recebido:", event);

              setProgress(event.progress);
              setProgressMessage(event.message);

              if (event.progress === 100 && event.resultado) {
                // Processar resultado final
                const data = event.resultado;
                console.log("✅ Processamento completo finalizado:", data);
                onSystemMessage?.({ type: "text", content: `Processamento concluído para CPF: ${data.cpf_processado || "Não encontrado"}`, isUser: false });

                onSystemMessage?.({ type: "text", content: `Exames extraídos do documento (OCR): ${data.exames_ocr || "Nenhum"}`, isUser: false });
                onSystemMessage?.({ type: "text", content: `Exames do BRNET: ${data.exames_brnet || "Nenhum"}`, isUser: false });

                if (data.tabela_comparacao && !data.erro) {
                  onSystemMessage?.({ type: "text", content: data.analise_comparacao, isUser: false });
                  onSystemMessage?.({ type: "tabela-exames", content: data.tabela_comparacao, isUser: false, skipTyping: true });

                  const faltantes = data.tabela_comparacao.filter((e: TabelaComparacaoItem) => e.status === "faltante");
                  if (faltantes.length > 0) {
                    const nomesFaltantes = faltantes.map((e: TabelaComparacaoItem) => e.exame).join(", ");
                    onSystemMessage?.({ type: "text", content: `Como há exames faltantes (${nomesFaltantes}), não posso autorizar o envio deste documento. Inclua os exames necessários e tente novamente.`, isUser: false });
                  } else {
                    onSystemMessage?.({ type: "text", content: data.decisao_final, isUser: false });
                  }
                } else if (data.erro) {
                    onSystemMessage?.({ type: "text", content: `❌ Erro: ${data.erro}`, isUser: false });
                } else {
                    onSystemMessage?.({ type: "text", content: "Não foi possível realizar a comparação de exames.", isUser: false });
                }
              } else if (event.progress === -1) {
                // Erro durante processamento
                onSystemMessage?.({ type: "text", content: `❌ ${event.message}`, isUser: false });
              }
            } catch (parseError) {
              console.error("❌ Erro ao parsear evento SSE:", parseError, jsonData);
            }
          }
        }
      }

    } catch (error) {
      console.error("❌ Erro geral no handleImport:", error);
      onSystemMessage?.({ type: "text", content: "❌ Ocorreu um erro inesperado durante o processamento do documento.", isUser: false });
    } finally {
      setIsImporting(false);
      setProgress(0);
      setProgressMessage("");
    }
  };
  
  return (
    <div className="flex flex-col gap-2">
      {/* Drop area */}
      <div
        role="button"
        onClick={openFileDialog}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        data-dragging={isDragging || undefined}
        className="border-input hover:bg-sidebar-ring/20 data-[dragging=true]:bg-slate-300 has-[input:focus]:border-ring has-[input:focus]:ring-ring/50 flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-4 transition-colors has-disabled:pointer-events-none has-disabled:opacity-50 has-[input:focus]:ring-[3px]"
      >
        <input
          {...getInputProps({ disabled: isImporting })}
          className="sr-only"
          aria-label="Importar arquivos"
        />

        <div className="flex flex-col items-center justify-center text-center">
            <div
              className="bg-background mb-2 flex size-11 shrink-0 items-center justify-center rounded-full border"
              aria-hidden="true"
            >
              <FileUpIcon className="size-4 opacity-60" />
            </div>
            <p className="text-muted-foreground mb-2 text-xs">
              Clique ou arraste e solte para importar seus documentos
            </p>
            <div className="text-muted-foreground/70 flex flex-wrap justify-center gap-1 text-xs">
              <span>Todos os arquivos</span>
              <span>∙</span>
              <span>Máximo {maxFiles} arquivos</span>
              <span>∙</span>
              <span>Até {formatBytes(maxSize)}</span>
            </div>
          </div>
       </div>

      {errors.length > 0 && (
        <div
          className="text-destructive flex items-center gap-1 text-xs"
          role="alert"
        >
          <AlertCircleIcon className="size-3 shrink-0" />
          <span>{errors[0]}</span>
        </div>
      )}

      {/* File list */}
      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((file) => (
            <div
              key={file.id}
              className="bg-background flex items-center justify-between gap-2 rounded-lg border p-2 pe-3"
            >
              <div className="flex items-center gap-3 overflow-hidden">
                <div className="flex aspect-square size-10 shrink-0 items-center justify-center rounded border">
                  {getFileIcon(file)}
                </div>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <p className="truncate text-[13px] font-medium">
                    {file.file instanceof File
                      ? file.file.name
                      : file.file.name}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {formatBytes(
                      file.file instanceof File
                        ? file.file.size
                        : file.file.size
                    )}
                  </p>
                </div>
              </div>

              <Button
                size="icon"
                variant="ghost"
                className="text-muted-foreground/80 hover:text-foreground -me-2 size-8 hover:bg-transparent"
                onClick={() => removeFile(file.id)}
                aria-label="Remove file"
              >
                <XIcon className="size-4" aria-hidden="true" />
              </Button>
            </div>
          ))}

          {/* Remover todos os arquivos  e importar */}

          {files.length >= 1 && (
            <div className="flex justify-center mt-4 gap-4">
              <Button
              onClick={clearFiles}
              size="sm"
              variant="outline"
              disabled={isImporting}
              className="
                group 
                relative 
                inline-flex 
                items-center 
                justify-center 
                overflow-hidden
                px-6 py-2
                hover:bg-red-400/90
                mt-2
              "
            >
            {/* Texto centralizado e que só se move no hover */}
            <span
              className="
                transition-transform 
                duration-200 
                group-hover:-translate-x-3
              "
            >
              Remover
            </span>

            {/* Ícone absolutamente posicionado, invisível até o hover */}
            <TrashIcon
              className="
                size-4 
                absolute 
                top-1/2 
                right-3 
                -translate-y-1/2 
                opacity-0 
                transition-all 
                duration-200 
                group-hover:opacity-100
              "
            />
        </Button>

              <Button
              size="sm"
              variant="secondary"
              className="
                group 
                relative 
                inline-flex 
                items-center 
                justify-center 
                overflow-hidden
                px-6 py-2
                mt-2
              "
              onClick={handleImport}
              disabled={isImporting}
            >
            {isImporting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Importando...
                </>
              ) : (
                <>
                  <span
                    className="
                transition-transform 
                duration-200 
                group-hover:-translate-x-3
              "
                  >
                    Importar
                  </span>
                  <ArrowRightIcon
                    className="
                size-4 
                absolute 
                top-1/2 
                right-3 
                -translate-y-1/2 
                opacity-0 
                transition-all 
                duration-200 
                group-hover:opacity-100
              "
                  />
                </>
              )}
        </Button>

            </div>
          )}

          {/* Barra de progresso */}
          {isImporting && progress > 0 && (
            <div className="mt-4 space-y-2">
              <Progress value={progress} className="w-full" />
              <p className="text-sm text-muted-foreground text-center">
                {progressMessage}
              </p>
            </div>
          )}
        </div>
      )}

    </div>
  )
}
