"use client"

import { useState } from "react"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"

/** `GET /v1/documents/{id}/conduta-sugerida/detalhes`: a chamada ao ml-exams e o que o OCR leu. */
interface Detalhes {
  sugestao_id: number | null
  caso_id: string | null
  request_id: string | null
  versao_features: string | null
  versao_modelo: string | null
  chamado_em: string | null
  duracao_ms: number | null
  status_http: number | null
  erro: string | null
  features: Record<string, unknown> | null
  resposta: unknown
  exames_ocr: string[]
  exames_brnet: string[]
  exames_faltantes: string[]
  texto_ocr: string
}

// Valores que só dizem "não há": ficam fora da lista resumida, mas aparecem no JSON completo.
const VAZIOS = new Set(["", "nao", "nao_informado", "ausente", "sem_resultado", "sem_referencia"])

// A primeira regra que casa decide o grupo; a ordem importa.
const GRUPOS: [string, (k: string) => boolean][] = [
  ["Ficha médica", (k) => k.startsWith("ficha_")],
  ["Riscos e atividades", (k) => k.startsWith("risco_") || k.startsWith("atividade_")],
  [
    "Exames previstos e realizados",
    (k) => /__(obrigatorio|realizado)$/.test(k) || k.startsWith("n_exames") || k.startsWith("n_obrigatorios"),
  ],
  ["Laboratório", (k) => /__(valor|status|desvio|ref_min|ref_max)$/.test(k) || k === "n_parametros_alterados"],
  ["Laudos (ECG, RX, audiometria, espirometria e outros)", (k) => k.includes("__") || k.includes("_achado_")],
  ["Contexto", () => true],
]

function agrupar(features: Record<string, unknown>): [string, [string, string][]][] {
  const grupos = new Map<string, [string, string][]>(GRUPOS.map(([nome]) => [nome, []]))
  for (const [k, v] of Object.entries(features).sort(([a], [b]) => a.localeCompare(b))) {
    if (v === null || v === undefined || VAZIOS.has(String(v))) continue
    const nome = GRUPOS.find(([, casa]) => casa(k))?.[0] ?? "Contexto"
    grupos.get(nome)?.push([k, String(v)])
  }
  return [...grupos.entries()].filter(([, linhas]) => linhas.length > 0)
}

function dataHora(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR")
}

/**
 * Bloco recolhido no fim da coluna: o que foi enviado ao ml-exams (features), o que ele respondeu e o que o OCR
 * leu do documento. Para conferir uma sugestão estranha; só busca os dados quando é aberto.
 */
export function DetalhesModelo({ documentoId, sugestaoId }: { documentoId: string; sugestaoId: number | null }) {
  const [dados, setDados] = useState<Detalhes | null>(null)
  const [estado, setEstado] = useState<"fechado" | "carregando" | "pronto" | "erro">("fechado")

  const carregar = async () => {
    setEstado("carregando")
    try {
      const url = new URL(API_ENDPOINTS.DOCUMENT_CONDUTA_DETALHES(documentoId), window.location.origin)
      if (sugestaoId !== null) url.searchParams.set("sugestao_id", String(sugestaoId))
      const resposta = await authFetch(url.toString())
      if (!resposta.ok) throw new Error(String(resposta.status))
      setDados(await resposta.json())
      setEstado("pronto")
    } catch {
      setEstado("erro")
    }
  }

  const features = dados?.features ?? null
  const total = features ? Object.keys(features).length : 0
  const grupos = features ? agrupar(features) : []
  const comValor = grupos.reduce((n, [, linhas]) => n + linhas.length, 0)

  return (
    <details
      className="tech"
      onToggle={(e) => {
        if (e.currentTarget.open && estado !== "pronto" && estado !== "carregando") carregar()
      }}
    >
      <summary>Ver o que foi enviado ao modelo</summary>
      {estado === "carregando" && <p className="tech-msg">Carregando...</p>}
      {estado === "erro" && (
        <p className="tech-msg">
          Não foi possível carregar.{" "}
          <button type="button" className="tech-link" onClick={carregar}>
            Tentar de novo
          </button>
        </p>
      )}
      {estado === "pronto" && dados && (
        <>
          <dl className="tech-ids">
            <dt>Caso no ml-exams</dt>
            <dd>{dados.caso_id ?? "—"}</dd>
            <dt>Request id</dt>
            <dd>{dados.request_id ?? "—"}</dd>
            <dt>Modelo</dt>
            <dd>{dados.versao_modelo ?? "—"}</dd>
            <dt>Features</dt>
            <dd>{dados.versao_features ?? "—"}</dd>
            <dt>Chamado em</dt>
            <dd>
              {dataHora(dados.chamado_em)}
              {dados.duracao_ms != null ? ` · ${dados.duracao_ms} ms` : ""}
              {dados.status_http != null ? ` · HTTP ${dados.status_http}` : ""}
              {dados.erro ? ` · ${dados.erro}` : ""}
            </dd>
          </dl>

          {features ? (
            <>
              <h4>
                Features enviadas: {comValor} com valor, de {total}
              </h4>
              {grupos.map(([nome, linhas]) => (
                <div key={nome} className="tech-grupo">
                  <h5>
                    {nome} ({linhas.length})
                  </h5>
                  <pre>{linhas.map(([k, v]) => `${k}: ${v}`).join("\n")}</pre>
                </div>
              ))}
              <details>
                <summary>Todas as features ({total}, JSON)</summary>
                <pre>{JSON.stringify(features, null, 2)}</pre>
              </details>
              <details>
                <summary>Resposta do ml-exams (JSON)</summary>
                <pre>{JSON.stringify(dados.resposta, null, 2)}</pre>
              </details>
            </>
          ) : (
            <p className="tech-msg">Nenhuma chamada ao modelo registrada para este documento.</p>
          )}

          <details>
            <summary>Exames: OCR × BRNET</summary>
            <pre>
              {[
                `Encontrados pelo OCR (${dados.exames_ocr.length}):\n  ${dados.exames_ocr.join("\n  ") || "—"}`,
                `Previstos no BRNET (${dados.exames_brnet.length}):\n  ${dados.exames_brnet.join("\n  ") || "—"}`,
                `Faltantes: ${dados.exames_faltantes.join(", ") || "nenhum"}`,
              ].join("\n\n")}
            </pre>
          </details>
          <details>
            <summary>Texto lido pelo OCR</summary>
            <pre className="tech-ocr">{dados.texto_ocr || "Sem texto do OCR."}</pre>
          </details>
        </>
      )}
    </details>
  )
}
