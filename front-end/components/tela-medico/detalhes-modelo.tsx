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

/** "Copiar" discreto: mostra "Copiado" por 2 s. Dentro de um <summary> não abre nem fecha a seção. */
function BotaoCopiar({ texto, rotulo = "Copiar" }: { texto: string; rotulo?: string }) {
  const [estado, setEstado] = useState<"ocioso" | "copiado" | "falhou">("ocioso")
  return (
    <button
      type="button"
      className="tech-copiar"
      onClick={async (e) => {
        e.preventDefault()
        e.stopPropagation()
        try {
          await navigator.clipboard.writeText(texto)
          setEstado("copiado")
        } catch {
          // Sem permissão de área de transferência (HTTP sem TLS): o texto já é selecionável na tela.
          setEstado("falhou")
        }
        window.setTimeout(() => setEstado("ocioso"), 2000)
      }}
    >
      {estado === "copiado" ? "Copiado" : estado === "falhou" ? "Selecione e copie" : rotulo}
    </button>
  )
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

  const textoIds = dados
    ? [
        `Caso no ml-exams: ${dados.caso_id ?? "—"}`,
        `Request id: ${dados.request_id ?? "—"}`,
        `Modelo: ${dados.versao_modelo ?? "—"}`,
        `Features: ${dados.versao_features ?? "—"}`,
        `Chamado em: ${dataHora(dados.chamado_em)}${dados.duracao_ms != null ? ` · ${dados.duracao_ms} ms` : ""}${
          dados.status_http != null ? ` · HTTP ${dados.status_http}` : ""
        }${dados.erro ? ` · ${dados.erro}` : ""}`,
      ].join("\n")
    : ""
  const textoGrupo = (linhas: [string, string][]) => linhas.map(([k, v]) => `${k}: ${v}`).join("\n")
  const textoFeatures = features ? JSON.stringify(features, null, 2) : ""
  const textoResposta = dados ? JSON.stringify(dados.resposta, null, 2) : ""
  const textoExames = dados
    ? [
        `Encontrados pelo OCR (${dados.exames_ocr.length}):\n  ${dados.exames_ocr.join("\n  ") || "—"}`,
        `Previstos no BRNET (${dados.exames_brnet.length}):\n  ${dados.exames_brnet.join("\n  ") || "—"}`,
        `Faltantes: ${dados.exames_faltantes.join(", ") || "nenhum"}`,
      ].join("\n\n")
    : ""
  const textoOcr = dados?.texto_ocr || "Sem texto do OCR."
  const textoTudo = dados
    ? [
        textoIds,
        ...grupos.map(([nome, linhas]) => `## ${nome}\n${textoGrupo(linhas)}`),
        `## Todas as features (JSON)\n${textoFeatures}`,
        `## Resposta do ml-exams (JSON)\n${textoResposta}`,
        `## Exames: OCR × BRNET\n${textoExames}`,
        `## Texto lido pelo OCR\n${textoOcr}`,
      ].join("\n\n")
    : ""

  return (
    <details
      className="tech"
      onToggle={(e) => {
        if (e.currentTarget.open && estado !== "pronto" && estado !== "carregando") carregar()
      }}
    >
      <summary>
        Ver o que foi enviado ao modelo
        {estado === "pronto" && dados && <BotaoCopiar texto={textoTudo} rotulo="Copiar tudo" />}
      </summary>
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
          <div className="tech-cab">
            <h4>Chamada ao ml-exams</h4>
            <BotaoCopiar texto={textoIds} />
          </div>
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
                  <div className="tech-cab">
                    <h5>
                      {nome} ({linhas.length})
                    </h5>
                    <BotaoCopiar texto={textoGrupo(linhas)} />
                  </div>
                  <pre>{textoGrupo(linhas)}</pre>
                </div>
              ))}
              <details>
                <summary>
                  Todas as features ({total}, JSON) <BotaoCopiar texto={textoFeatures} />
                </summary>
                <pre>{textoFeatures}</pre>
              </details>
              <details>
                <summary>
                  Resposta do ml-exams (JSON) <BotaoCopiar texto={textoResposta} />
                </summary>
                <pre>{textoResposta}</pre>
              </details>
            </>
          ) : (
            <p className="tech-msg">Nenhuma chamada ao modelo registrada para este documento.</p>
          )}

          <details>
            <summary>
              Exames: OCR × BRNET <BotaoCopiar texto={textoExames} />
            </summary>
            <pre>{textoExames}</pre>
          </details>
          <details>
            <summary>
              Texto lido pelo OCR <BotaoCopiar texto={textoOcr} />
            </summary>
            <pre className="tech-ocr">{textoOcr}</pre>
          </details>
        </>
      )}
    </details>
  )
}
