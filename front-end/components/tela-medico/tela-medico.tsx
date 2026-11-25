"use client"

import * as DialogPrimitive from "@radix-ui/react-dialog"
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react"
import { foraDaFaixa } from "@/components/exames-comparativo-table"
import { VisualizadorPdf, type Destaque } from "@/components/visualizador-pdf"
import type { ParametroLido } from "@/types/normalidade"
import { rotuloTipoExame } from "./documento-medico"
import type { Analise, DecisaoMedico, ExamePrevisto, MotivoSemSugestao, NormalidadeExame, SituacaoAso, TipoExame } from "./tipos"
import "./tela-medico.css"

/**
 * Revisão do ASO pelo médico. Reprodução fiel do protótipo
 * `tela-medico-prontuai-v4.html`, sobre o contrato do doc da API de
 * Normalidade e Conduta Sugerida. É o conteúdo do modal aberto pela lista de
 * `/medico` (ver `modal-revisao-aso.tsx`). Enquanto a API não existe, recebe a
 * análise montada do documento aprovado (`documento-medico.ts`), mostra o PDF
 * de verdade no lugar da página simulada do protótipo e registra a decisão só
 * na tela.
 */

// Rótulos para a tela
export const CONDUTA: Record<SituacaoAso, string> = {
  LIBERADO: "Liberado",
  LIBERADO_COM_ENCAMINHAMENTO: "Liberado com encaminhamento",
  RETIDO: "Retido",
  INAPTO: "Inapto",
}
export const TIPO_EXAME: Record<TipoExame, string> = {
  ADMISSIONAL: "Admissional",
  PERIODICO: "Periódico",
  RETORNO_AO_TRABALHO: "Retorno ao trabalho",
  MUDANCA_DE_RISCO: "Mudança de risco",
  DEMISSIONAL: "Demissional",
}
const ATIVIDADE: Record<string, string> = {
  NR_35: "NR-35 · trabalho em altura",
  NR_33: "NR-33 · espaço confinado",
  NR_10: "NR-10 · eletricidade",
}
const CAMPO_FICHA: Record<string, string> = {
  doencas_cronicas_diabetes_mellitus: "Diabetes",
  doencas_cronicas_diabetes_mellitus_uso_medicamento: "Usa medicamento",
  doencas_cronicas_hipertensao: "Hipertensão",
}
const VALOR_FICHA: Record<string, string> = { sim: "Sim", nao: "Não", nao_informado: "não informado" }
const SEM_SUGESTAO: Record<MotivoSemSugestao, string> = {
  CONFIANCA_BAIXA: "A confiança ficou abaixo do limite. Decida a partir dos dados.",
  FORA_DO_PROTOCOLO: "Caso fora do protocolo. Decida a partir dos dados.",
  FALHA_NA_LEITURA: "Não foi possível ler a ficha médica ou buscar os dados do pedido.",
  PEDIDO_DIVERGENTE: "O pedido informado não bate com o documento. Confira a identificação antes de decidir.",
}
// Enquanto a API de conduta não existe, toda análise cai aqui.
const SUGESTAO_INDISPONIVEL =
  "A sugestão de conduta do ProntuAI ainda não está disponível. Decida a partir dos exames e do documento."

/** "Glicose 192 mg/dL", com o valor como saiu no laudo. */
function valorParametro(p: ParametroLido): string {
  const valor = p.valor_texto ?? (p.valor != null ? String(p.valor) : "")
  return `${p.nome} ${valor}${p.unidade && valor ? " " + p.unidade : ""}`.trim()
}

// Nos exames normais, quantos valores aparecem antes do "+N".
const VALORES_NORMAIS = 3

// Exames: o que pede atenção primeiro, normais recolhidos
type TipoItem = "alterado" | "faltante" | "inconclusivo" | "normal"
const SEVERIDADE: Record<TipoItem, number> = { alterado: 0, faltante: 1, inconclusivo: 2, normal: 3 }
interface Item {
  p: ExamePrevisto
  n: NormalidadeExame | undefined
  tipo: TipoItem
}

type NomeIcone = "check" | "x" | "up" | "down" | "help" | "alert" | "file" | "chev" | "spark"

function Icone({ nome }: { nome: NomeIcone }) {
  return (
    <svg className="i" aria-hidden="true">
      <use href={`#i-${nome}`} />
    </svg>
  )
}

function SpriteIcones() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <symbol id="i-check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5" /></symbol>
      <symbol id="i-x" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12" /></symbol>
      <symbol id="i-up" viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7" /></symbol>
      <symbol id="i-down" viewBox="0 0 24 24"><path d="M12 5v14M19 12l-7 7-7-7" /></symbol>
      <symbol id="i-help" viewBox="0 0 24 24"><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01" /></symbol>
      <symbol id="i-alert" viewBox="0 0 24 24">
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
        <path d="M12 9v4M12 17h.01" />
      </symbol>
      <symbol id="i-file" viewBox="0 0 24 24">
        <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
        <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      </symbol>
      <symbol id="i-chev" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6" /></symbol>
      <symbol id="i-spark" viewBox="0 0 24 24"><path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8Z" /></symbol>
    </svg>
  )
}

const agoraIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z")

/** O PDF do documento. `blob` null: não foi possível baixar (arquivado ou fora do ar). */
export interface PdfDocumento {
  blob: Blob | null
  url: string | null
  carregarTexto: () => Promise<import("@/types/localizacao").LinhaTexto[] | null>
}

interface TelaMedicoProps {
  analise: Analise
  /** Nome do paciente, em destaque no cabeçalho (fora do doc da API). */
  paciente?: string | null
  /** null enquanto o PDF baixa. */
  pdf: PdfDocumento | null
  /** O X do cabeçalho e o clique fora do cartão: voltam para a lista. */
  onFechar: () => void
  /** Conduta já registrada nesta análise, para reabrir com o selo "Registrado". */
  decisaoRegistrada?: SituacaoAso | null
  onRegistrar?: (decisao: DecisaoMedico) => void
}

export function TelaMedico({ analise, paciente, pdf, onFechar, decisaoRegistrada = null, onRegistrar }: TelaMedicoProps) {
  const ctx = analise.contexto
  const sug = analise.conduta_sugerida
  const exames = analise.presenca_exames.exames
  const normById: Record<string, NormalidadeExame> = Object.fromEntries(
    analise.normalidade.map((n) => [n.exame_id, n]),
  )

  const itens: Item[] = exames
    .map((p) => {
      const n = normById[p.exame_id]
      const tipo: TipoItem = !p.encontrado ? "faltante" : n ? n.classificacao : "normal"
      return { p, n, tipo }
    })
    .sort((a, b) => SEVERIDADE[a.tipo] - SEVERIDADE[b.tipo])
  const atencao = itens.filter((i) => i.tipo !== "normal")
  const normais = itens.filter((i) => i.tipo === "normal")
  const pendentes = atencao.filter((i) => i.tipo === "faltante" || i.tipo === "inconclusivo").length

  // Documento, recolhido por padrão
  const [docAberto, setDocAberto] = useState(false)
  // O exame da última ida pela "Pág. N". `chave` muda a cada clique, para o
  // visualizador rolar e marcar de novo.
  const [destaque, setDestaque] = useState<(Destaque & { exame: string }) | null>(null)
  const [fixAbertos, setFixAbertos] = useState<Record<string, boolean>>({})
  const [correcoes, setCorrecoes] = useState<Record<string, string>>({})
  const [escolha, setEscolha] = useState<SituacaoAso | null>(null)
  const [obs, setObs] = useState("")
  const [registrado, setRegistrado] = useState<SituacaoAso | null>(decisaoRegistrada)
  // A hora da decisão só anda quando o médico mexe em algo, como no protótipo.
  const [decididoEm, setDecididoEm] = useState("")
  const [toastMsg, setToastMsg] = useState<{ texto: string; ok: boolean; visivel: boolean }>({
    texto: "",
    ok: false,
    visivel: false,
  })

  const docToggleRef = useRef<HTMLButtonElement>(null)
  const docHideRef = useRef<HTMLButtonElement>(null)
  const focoRef = useRef<string | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setDecididoEm(agoraIso())
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    }
  }, [])

  // Foco depois da troca de tela (botões que somem e o select que aparece).
  useEffect(() => {
    const alvo = focoRef.current
    if (!alvo) return
    focoRef.current = null
    if (alvo === "doc-hide") docHideRef.current?.focus()
    else if (alvo === "doc-toggle") docToggleRef.current?.focus()
    else document.getElementById(alvo)?.focus()
  })

  const irPara = (p: ExamePrevisto) => {
    if (!p.localizacao) return
    const localizacao = p.localizacao
    setDestaque((d) => ({ ...localizacao, exame: p.exame_id, chave: (d?.chave ?? 0) + 1 }))
    setDocAberto(true)
  }

  const mostrarToast = (texto: string, ok: boolean) => {
    setToastMsg({ texto, ok, visivel: true })
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToastMsg((t) => ({ ...t, visivel: false })), 2400)
  }

  const buildPayload = (): DecisaoMedico => {
    const exibida = !!sug
    return {
      sugestao_exibida: exibida,
      concordou_com_sugestao: sug && escolha ? escolha === sug.situacao_aso : null,
      conduta_final: { situacao_aso: escolha, observacao: obs.trim() || null },
      normalidade_final: Object.entries(correcoes).map(([exame_id, classificacao]) => ({ exame_id, classificacao })),
      decidido_em: decididoEm,
    }
  }
  const payload = `POST /v1/analises/${analise.analise_id}/decisao\n\n` + JSON.stringify(buildPayload(), null, 2)

  const renderItem = ({ p, n, tipo }: Item) => {
    let ico: ReactNode
    let detail: ReactNode
    if (tipo === "faltante") {
      ico = <span className="ico bad"><Icone nome="x" /></span>
      detail = "Previsto no pedido, não encontrado no documento."
    } else if (tipo === "alterado" && n?.parametros) {
      // Um valor por parâmetro fora da faixa (o hemograma pode ter vários).
      ico = <span className="ico bad"><Icone nome={n.direcao === "abaixo" ? "down" : "up"} /></span>
      detail = n.parametros.filter(foraDaFaixa).map((par) => (
        <div key={par.chave}>
          <span className="val">{valorParametro(par)}</span>{" "}
          <span className="dir">{par.situacao === "alterado" ? "alterado" : par.situacao}</span>
          {par.referencia ? ` · ref. ${par.referencia}` : ""}
        </div>
      ))
    } else if (tipo === "alterado" && n) {
      const abaixo = n.direcao === "abaixo"
      ico = <span className="ico bad"><Icone nome={abaixo ? "down" : "up"} /></span>
      detail = (
        <>
          <span className="val">{n.valor}{n.unidade ? " " + n.unidade : ""}</span>{" "}
          <span className="dir">{abaixo ? "abaixo" : "acima"}</span>
          {n.faixa_referencia ? ` · ref. ${n.faixa_referencia.texto}` : ""}
        </>
      )
    } else if (tipo === "inconclusivo") {
      ico = <span className="ico warn"><Icone nome="help" /></span>
      detail = "Resultado não lido no laudo. Confira no documento."
    } else {
      ico = <span className="ico ok"><Icone nome="check" /></span>
      const lidos = n?.parametros?.filter((par) => par.valor_texto != null || par.valor != null) ?? []
      detail = lidos.length
        ? <span className="val">
            {lidos.slice(0, VALORES_NORMAIS).map(valorParametro).join(" · ")}
            {lidos.length > VALORES_NORMAIS ? ` · +${lidos.length - VALORES_NORMAIS}` : ""}
          </span>
        : n?.parametros
          ? "Sem alteração"
          : !n && analise.contexto_disponivel === false
            ? "Encontrado no documento"
            : n && n.valor
        ? <span className="val">{n.valor}{n.unidade ? " " + n.unidade : ""}</span>
        : "Sem alteração"
    }

    const id = p.exame_id
    const fix = n ? (
      <div className="fix" id={`fix-${id}`}>
        {fixAbertos[id] ? (
          <>
            <label htmlFor={`sel-${id}`} style={{ color: "var(--muted-fg)" }}>Sua leitura:</label>
            <select
              id={`sel-${id}`}
              data-exame={id}
              className={correcoes[id] ? "changed" : undefined}
              value={correcoes[id] ?? ""}
              onChange={(e) => {
                const v = e.target.value
                setCorrecoes((c) => {
                  const nova = { ...c }
                  if (v) nova[id] = v
                  else delete nova[id]
                  return nova
                })
                setDecididoEm(agoraIso())
              }}
            >
              <option value="">Manter ({n.classificacao})</option>
              <option value="normal">Normal</option>
              <option value="alterado">Alterado</option>
            </select>
          </>
        ) : (
          <button
            className="link"
            type="button"
            onClick={() => {
              focoRef.current = `sel-${id}`
              setFixAbertos((f) => ({ ...f, [id]: true }))
            }}
          >
            Corrigir leitura
          </button>
        )}
      </div>
    ) : null

    const page = p.pagina ? (
      <button
        className="btn page-btn"
        type="button"
        aria-label={`Ver ${p.exame} na página ${p.pagina}`}
        onClick={() => irPara(p)}
      >
        <Icone nome="file" />
        Pág. {p.pagina}
      </button>
    ) : null

    const ativo = docAberto && destaque?.exame === id
    return (
      <li key={id} className={ativo ? "issue active" : "issue"} data-pg={p.pagina || ""}>
        {ico}
        <span className="name">{p.exame}</span>
        {page}
        <div className="detail">{detail}</div>
        {fix}
      </li>
    )
  }

  // Trabalhador e ficha
  const kv: [string, ReactNode][] = [
    ["Riscos", ctx.riscos.join(", ") || "Nenhum"],
    [
      "Atividade crítica",
      ctx.atividades_criticas.length
        ? ctx.atividades_criticas.map((a) => (
            <span key={a} className="badge bad"><Icone nome="alert" />{ATIVIDADE[a] || a}</span>
          ))
        : "Nenhuma",
    ],
    [
      "Ficha médica",
      ctx.ficha_medica.map((f) => (
        <span key={f.campo} className="pair">
          <span>{CAMPO_FICHA[f.campo] || f.campo}:</span>{" "}
          <b className={f.valor === "nao_informado" ? "na" : ""}>{VALOR_FICHA[f.valor] || f.valor}</b>
        </span>
      )),
    ],
  ]
  if (ctx.particularidades.length) kv.push(["Regra do cliente", ctx.particularidades.join("; ")])

  // Documento
  const exameDestacado = destaque ? exames.find((p) => p.exame_id === destaque.exame) : undefined

  // Sugestão
  const pct = sug ? Math.round(sug.confianca * 100) : 0

  // Decisão
  const libera = escolha === "LIBERADO" || escolha === "LIBERADO_COM_ENCAMINHAMENTO"
  const footHint = !escolha
    ? "Escolha uma conduta para registrar."
    : !sug
      ? "Decisão sem sugestão do ProntuAI."
      : escolha === sug.situacao_aso
        ? "Você está mantendo a conduta sugerida."
        : "Você está alterando a conduta sugerida."

  return (
    // O espaço em volta do cartão (a margem do `.shell` e a faixa fora dele, em
    // tela larga) faz o papel do fundo do modal: clicar nele fecha.
    <div
      className="tm tm-modal"
      onClick={(e) => {
        const alvo = e.target as HTMLElement
        if (alvo === e.currentTarget || alvo.classList.contains("shell")) onFechar()
      }}
    >
      <SpriteIcones />

      <div className={docAberto ? "shell doc-open" : "shell"}>
        <div className="modal">
          <header className="head">
            <div className="t">
              <div className="title-row">
                <DialogPrimitive.Title asChild>
                  <h1>Revisão do ASO</h1>
                </DialogPrimitive.Title>
                {registrado ? (
                  <span className="badge ok"><Icone nome="check" />Registrado: {CONDUTA[registrado]}</span>
                ) : (
                  <span className="badge warn">Aguardando decisão</span>
                )}
              </div>
              <div className="ctx">
                {/* Empresa e função ainda não chegam ao ProntuAI: no lugar, o paciente. */}
                {[
                  paciente || ctx.empresa ? <b key="b">{paciente || ctx.empresa}</b> : null,
                  paciente && ctx.empresa ? ctx.empresa : null,
                  ctx.funcao,
                  ctx.tipo_exame ? TIPO_EXAME[ctx.tipo_exame as TipoExame] || rotuloTipoExame(ctx.tipo_exame) : null,
                  analise.pedido_exame_id ? `Pedido ${analise.pedido_exame_id}` : null,
                ]
                  .filter(Boolean)
                  .map((parte, i) => (
                    <Fragment key={i}>
                      {i > 0 && " · "}
                      {parte}
                    </Fragment>
                  ))}
              </div>
            </div>
            <div className="tools">
              <button
                ref={docToggleRef}
                className="btn doc-toggle"
                type="button"
                aria-controls="tm-doc"
                aria-expanded={docAberto}
                onClick={() => {
                  focoRef.current = "doc-hide"
                  setDocAberto(true)
                }}
              >
                <Icone nome="file" />
                <span>Ver documento</span>
              </button>
              <button
                className="x"
                type="button"
                aria-label="Fechar"
                onClick={onFechar}
              >
                <Icone nome="x" />
              </button>
            </div>
          </header>

          <div className="body">
            {/* Revisão */}
            <div className="review">
              <section aria-labelledby="h-att">
                <h2 className="eyebrow" id="h-att">
                  Pontos de atenção {atencao.length > 0 && <span className="badge bad">{atencao.length}</span>}
                </h2>
                <ul className="issues">
                  {atencao.length ? (
                    atencao.map(renderItem)
                  ) : (
                    <li className="issue">
                      <span className="ico ok"><Icone nome="check" /></span>
                      <span className="name">Nada fora do esperado</span>
                    </li>
                  )}
                </ul>
                {normais.length > 0 && (
                  <details className="more">
                    <summary>
                      <Icone nome="chev" />
                      <span>{`${normais.length} exame${normais.length > 1 ? "s" : ""} sem alteração`}</span>
                    </summary>
                    <ul className="issues">{normais.map(renderItem)}</ul>
                  </details>
                )}
              </section>

              <section aria-labelledby="h-ctx">
                <h2 className="eyebrow" id="h-ctx">Trabalhador e ficha médica</h2>
                {analise.contexto_disponivel === false ? (
                  <p className="sugg-expl">
                    Riscos, atividade crítica e ficha médica ainda não chegam ao ProntuAI. Consulte o documento.
                  </p>
                ) : (
                  <dl className="kv">
                    {kv.map(([k, v]) => (
                      <Fragment key={k}>
                        <dt>{k}</dt>
                        <dd>{v}</dd>
                      </Fragment>
                    ))}
                  </dl>
                )}
              </section>

              <details className="tech">
                <summary>Ver o que será enviado à API</summary>
                <pre>{payload}</pre>
              </details>
            </div>

            {/* Documento (recolhido por padrão) */}
            <div className="doc" id="tm-doc">
              <div className="doc-head">
                <h2 className="eyebrow">
                  {exameDestacado ? `Documento · ${exameDestacado.exame}` : "Documento"}
                </h2>
                <div className="right">
                  <button
                    ref={docHideRef}
                    className="btn"
                    type="button"
                    onClick={() => {
                      focoRef.current = "doc-toggle"
                      setDocAberto(false)
                    }}
                  >
                    <Icone nome="x" />
                    Ocultar
                  </button>
                </div>
              </div>
              {/* O PDF de verdade, no visualizador da Checagem (com busca e marca-texto). */}
              <div className="viewer pdf">
                {pdf?.url ? (
                  <VisualizadorPdf
                    arquivo={pdf.blob}
                    url={pdf.url}
                    titulo="Documento do ASO"
                    destaque={destaque}
                    carregarTexto={pdf.carregarTexto}
                  />
                ) : (
                  <div className="pdf-msg">
                    {pdf ? "Não foi possível abrir o documento." : "Carregando documento..."}
                  </div>
                )}
              </div>
            </div>

            {/* Decisão */}
            <aside className="side" aria-label="Conduta">
              <div className="side-scroll">
                <div className="sugg">
                  <h2 className="eyebrow"><Icone nome="spark" />Sugestão do ProntuAI</h2>
                  {sug ? (
                    <>
                      <div className={`sugg-val ${sug.situacao_aso}`}>{CONDUTA[sug.situacao_aso]}</div>
                      <div className="conf">
                        <span className="meter" role="img" aria-label={`Confiança ${pct}%`}>
                          <span style={{ width: `${pct}%` }} />
                        </span>
                        <span>
                          Confiança <b>{pct}%</b>
                          {analise.confianca_calibrada ? "" : " · não calibrada"}
                        </span>
                      </div>
                      <p className="sugg-expl">{sug.explicacao}</p>
                      <h3>O que pesou</h3>
                      <ul>
                        {sug.fatores.map((f) => <li key={f}>{f}</li>)}
                      </ul>
                      {sug.regras_cliente.length > 0 && (
                        <>
                          <h3>Regra do cliente aplicada</h3>
                          <ul>
                            {sug.regras_cliente.map((r) => (
                              <li key={`${r.exame_id}-${r.regra}`}>
                                {r.regra} <span className="eff">→ {CONDUTA[r.efeito] || r.efeito}</span>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="sugg-val none">Sem sugestão</div>
                      <p className="sugg-expl">
                        {(analise.motivo_sem_sugestao && SEM_SUGESTAO[analise.motivo_sem_sugestao]) ||
                          SUGESTAO_INDISPONIVEL}
                      </p>
                    </>
                  )}
                </div>
                <div className="decide">
                  <h2 id="h-dec">Sua decisão</h2>
                  <div className="opts" role="radiogroup" aria-labelledby="h-dec">
                    {(Object.entries(CONDUTA) as [SituacaoAso, string][]).map(([k, v]) => (
                      <label key={k} className={escolha === k ? "opt selected" : "opt"} data-k={k}>
                        <input
                          type="radio"
                          name="conduta"
                          value={k}
                          checked={escolha === k}
                          onChange={() => {
                            setEscolha(k)
                            setDecididoEm(agoraIso())
                          }}
                        />
                        <span className="radio" aria-hidden="true" />
                        <span>{v}</span>
                        {sug && sug.situacao_aso === k && (
                          <span className="tag"><Icone nome="spark" />Sugerida</span>
                        )}
                      </label>
                    ))}
                  </div>
                  <div className={libera && pendentes > 0 ? "note show" : "note"} role="alert">
                    {escolha && (
                      <>
                        <Icone nome="alert" />
                        <span>
                          Há {pendentes} pendência{pendentes > 1 ? "s" : ""} no documento. Confira antes de liberar o
                          ASO.
                        </span>
                      </>
                    )}
                  </div>
                  <div className="obs">
                    <label htmlFor="tm-obs">
                      Observação <span>(opcional)</span>
                    </label>
                    <textarea
                      id="tm-obs"
                      placeholder="Encaminhamento, orientação ou motivo da decisão"
                      value={obs}
                      onChange={(e) => {
                        setObs(e.target.value)
                        setDecididoEm(agoraIso())
                      }}
                    />
                  </div>
                </div>
              </div>
              <div className="side-foot">
                <button
                  className="submit"
                  type="button"
                  disabled={!escolha}
                  onClick={() => {
                    if (!escolha) return
                    const agora = agoraIso()
                    setDecididoEm(agora)
                    setRegistrado(escolha)
                    onRegistrar?.({ ...buildPayload(), decidido_em: agora })
                    mostrarToast("Decisão registrada", true)
                  }}
                >
                  Registrar decisão
                </button>
                <div className="foot-hint">{footHint}</div>
              </div>
            </aside>
          </div>
        </div>
      </div>
      <div className={toastMsg.visivel ? "toast show" : "toast"} role="status">
        {toastMsg.ok && <Icone nome="check" />}
        <span>{toastMsg.texto}</span>
      </div>
    </div>
  )
}
