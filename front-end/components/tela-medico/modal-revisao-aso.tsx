"use client"

import { useEffect, useMemo, useState } from "react"
import { Loader2 } from "lucide-react"
import { useNormalidade } from "@/components/comparacao-detalhada"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { carregarTextoDocumento, useLocalizacoes } from "@/hooks/use-localizacoes"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"
import { montarAnalise } from "./documento-medico"
import { TelaMedico, type PdfDocumento } from "./tela-medico"
import type { Analise, DecisaoMedico, DocumentoAprovado, SituacaoAso } from "./tipos"

type Sugestao = Pick<
  Analise,
  "conduta_sugerida" | "motivo_sem_sugestao" | "versao_modelo" | "confianca_calibrada" | "prob_encaminhamento" | "caso_id" | "sugestao_id"
> & {
  /** A exibição registrada no back-end: a decisão aponta para ela (o que o médico viu). */
  exibicao_id: number | null
  /** A última decisão gravada para o documento, para reabrir com o selo "Registrado". */
  decisao_registrada: SituacaoAso | null
}

const SEM_SUGESTAO_CARREGADA: Sugestao = {
  conduta_sugerida: null,
  motivo_sem_sugestao: null,
  versao_modelo: "",
  confianca_calibrada: false,
  prob_encaminhamento: null,
  caso_id: null,
  sugestao_id: null,
  exibicao_id: null,
  decisao_registrada: null,
}

/** A conduta sugerida pelo modelo (`GET /v1/documents/{id}/conduta-sugerida`); null enquanto calcula. */
function useCondutaSugerida(documentoId: string | null): Sugestao | null {
  const [sugestao, setSugestao] = useState<Sugestao | null>(null)
  useEffect(() => {
    setSugestao(null)
    if (!documentoId) return
    let ativo = true
    authFetch(API_ENDPOINTS.DOCUMENT_CONDUTA_SUGERIDA(documentoId))
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error(String(resposta.status))
        const dados = await resposta.json()
        if (!ativo) return
        setSugestao({
          conduta_sugerida: dados.conduta_sugerida ?? null,
          motivo_sem_sugestao: dados.motivo_sem_sugestao ?? null,
          versao_modelo: dados.versao_modelo ?? "",
          confianca_calibrada: !!dados.confianca_calibrada,
          prob_encaminhamento: typeof dados.prob_encaminhamento === "number" ? dados.prob_encaminhamento : null,
          caso_id: typeof dados.caso_id === "string" ? dados.caso_id : null,
          sugestao_id: typeof dados.sugestao_id === "number" ? dados.sugestao_id : null,
          exibicao_id: typeof dados.exibicao_id === "number" ? dados.exibicao_id : null,
          decisao_registrada: dados.decisao_registrada?.situacao_aso ?? null,
        })
      })
      .catch(() => {
        // Rota ou modelo fora do ar: a tela abre sem sugestão, com a mensagem de indisponível.
        if (ativo) setSugestao(SEM_SUGESTAO_CARREGADA)
      })
    return () => {
      ativo = false
    }
  }, [documentoId])
  return sugestao
}

interface ModalRevisaoAsoProps {
  documento: DocumentoAprovado | null
  onOpenChange: (open: boolean) => void
  decisaoRegistrada?: SituacaoAso | null
  onRegistrar?: (decisao: DecisaoMedico) => void
}

/** O PDF do documento, baixado uma vez por abertura do modal. */
function usePdf(documentoId: string | null): PdfDocumento | null {
  const [pdf, setPdf] = useState<PdfDocumento | null>(null)
  useEffect(() => {
    setPdf(null)
    if (!documentoId) return
    let ativo = true
    let url: string | null = null
    authFetch(API_ENDPOINTS.DOCUMENT_VIEW(documentoId))
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error(String(resposta.status))
        const blob = await resposta.blob()
        if (!ativo) return
        url = URL.createObjectURL(blob)
        setPdf({ blob, url, carregarTexto: () => carregarTextoDocumento(documentoId) })
      })
      .catch(() => {
        // Arquivado ou fora do ar: a tela avisa no lugar do documento.
        if (ativo) setPdf({ blob: null, url: null, carregarTexto: async () => null })
      })
    return () => {
      ativo = false
      if (url) URL.revokeObjectURL(url)
    }
  }, [documentoId])
  return pdf
}

/**
 * Abre a Revisão do ASO por cima da lista, como o modal de detalhes da
 * Checagem. Usa o `DialogContent` do app (que solta o clique ao fechar), mas
 * sem a caixa dele: quem desenha o cartão, o espaço em volta e o X é a tela do
 * protótipo. Por isso o X padrão do Dialog fica escondido.
 *
 * Monta a análise com o que já existe: o documento aprovado, a leitura de
 * normalidade pela faixa do laudo, a posição dos exames no PDF e a conduta
 * sugerida pelo modelo.
 */
export function ModalRevisaoAso({ documento, onOpenChange, decisaoRegistrada, onRegistrar }: ModalRevisaoAsoProps) {
  const id = documento?.documento_id ?? null
  const normalidade = useNormalidade(id)
  const localizacoes = useLocalizacoes(id)
  const pdf = usePdf(id)
  const sugestao = useCondutaSugerida(id)

  const analise = useMemo(() => {
    if (!documento || normalidade.fase === "carregando" || !sugestao) return null
    return {
      ...montarAnalise(documento, normalidade.fase === "pronta" ? normalidade.porExame : null, localizacoes.porExame),
      conduta_sugerida: sugestao.conduta_sugerida,
      motivo_sem_sugestao: sugestao.motivo_sem_sugestao,
      versao_modelo: sugestao.versao_modelo,
      confianca_calibrada: sugestao.confianca_calibrada,
      prob_encaminhamento: sugestao.prob_encaminhamento,
      caso_id: sugestao.caso_id,
      sugestao_id: sugestao.sugestao_id,
    }
  }, [documento, normalidade, localizacoes.porExame, sugestao])

  /** Grava a decisão no back-end (trilha de auditoria) antes de marcar como registrada. */
  const registrar = async (decisao: DecisaoMedico): Promise<boolean> => {
    if (!documento) return false
    const resposta = await authFetch(API_ENDPOINTS.DOCUMENT_CONDUTA_DECISAO(documento.documento_id), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...decisao, exibicao_id: sugestao?.exibicao_id ?? null }),
    })
    if (!resposta.ok) return false
    onRegistrar?.(decisao)
    return true
  }

  return (
    <Dialog open={!!documento} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby={undefined}
        className="block !w-screen !h-svh !max-w-none !max-h-none p-0 gap-0 border-0 rounded-none bg-transparent shadow-none overflow-hidden [&>button:last-child]:hidden"
      >
        {documento && analise ? (
          <TelaMedico
            key={documento.documento_id}
            analise={analise}
            paciente={documento.paciente_nome}
            pdf={pdf}
            onFechar={() => onOpenChange(false)}
            decisaoRegistrada={decisaoRegistrada ?? sugestao?.decisao_registrada ?? null}
            onRegistrar={registrar}
          />
        ) : (
          // Enquanto a leitura de normalidade chega: a tela abriria sem os
          // valores e mudaria os "Pontos de atenção" na frente do médico.
          <div
            className="flex h-full items-center justify-center"
            onClick={(e) => {
              if (e.target === e.currentTarget) onOpenChange(false)
            }}
          >
            <DialogTitle className="sr-only">Revisão do ASO</DialogTitle>
            <div className="flex items-center gap-2 rounded-lg bg-white px-5 py-4 text-sm text-muted-foreground shadow">
              <Loader2 className="size-4 animate-spin" />
              Lendo os exames do documento...
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
