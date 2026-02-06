"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import Image from "next/image"
import { useEffect, useRef, useState, type MouseEvent } from "react"
import {
  AlertCircle,
  ArrowRight,
  Bell,
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  FileCheck,
  Shield,
  Target,
  UploadCloud,
  Users,
  XCircle,
} from "lucide-react"

const flowSteps = [
  {
    step: "01",
    title: "Upload seguro",
    description: "Anexe prontuários completos e inicie o processamento do lote.",
    details:
      "Entrada: PDFs com exames e laudos completos. Saída: lote criado com protocolo de rastreio. Checklist: páginas legíveis e sem cortes. Responsável: clínica.",
    icon: UploadCloud,
  },
  {
    step: "02",
    title: "OCR + BRNET",
    description: "Extração automática e comparação com a grade obrigatória.",
    details:
      "Entrada: imagens e textos do PDF. Processo: OCR e comparação com a grade BRNET. Saída: checklist de campos encontrados e ausentes. Responsável: processamento IA.",
    icon: Target,
  },
  {
    step: "03",
    title: "Resultado guiado",
    description: "Status claros com justificativas por item encontrado ou ausente.",
    details:
      "Entrada: checklist com evidências. Saída: aprovado, pendente ou rejeitado. Justificativas: itens faltantes e divergências. Responsável: IA + regras do sistema.",
    icon: CheckCircle2,
  },
  {
    step: "04",
    title: "Checagem humana",
    description: "Revisor aprova ou rejeita e o sistema registra a decisão final.",
    details:
      "Entrada: status e justificativas da IA. Processo: revisão humana e validação. Saída: decisão final registrada. Responsável: time interno BR MED.",
    icon: Shield,
  },
]

type FlowStep = (typeof flowSteps)[number]

const roleCards = [
  {
    title: "Clínica (Enviador)",
    description: "Responsável por enviar documentos.",
    icon: Users,
    access: ["Anexar Prontuário", "Pendentes"],
    points: [
      "Faz upload de PDFs médicos e acompanha o processamento e validação.",
      "Enviador só vê rejeições finais do revisor que precisa corrigir.",
    ],
    important:
      "Em /pendentes aparecem apenas documentos rejeitados (pela IA ou revisor). Documentos aprovados não aparecem.",
  },
  {
    title: "Time interno BR MED (Revisor)",
    description: "Valida documentos processados.",
    icon: Shield,
    access: ["Checagem"],
    points: ["Analisa documentos e toma decisões de aprovar ou rejeitar com justificativa."],
    actions: [
      "Aprovar: documento validado e liberado.",
      "Rejeitar: documento retorna ao enviador com motivo.",
    ],
  },
  {
    title: "Administrador (ADMIN)",
    description: "Gestão e auditoria do fluxo.",
    icon: FileCheck,
    access: ["Anexar Prontuário", "Pendentes", "Checagem", "Histórico", "Insights"],
    points: ["Acesso total a funcionalidades, analytics e configurações."],
  },
]

const statusItems = [
  {
    title: "Aprovado pela IA",
    description: "Documento segue para revisão humana.",
    icon: CheckCircle2,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
  },
  {
    title: "Pendente de revisão",
    description: "IA encontrou pendências e requer conferência.",
    icon: AlertCircle,
    color: "text-amber-600",
    bg: "bg-amber-50",
  },
  {
    title: "Rejeitado",
    description: "Revisor solicitou reenvio com justificativa.",
    icon: XCircle,
    color: "text-rose-600",
    bg: "bg-rose-50",
  },
]

const statusFlow = [
  "A IA valida o documento e aponta o que falta ou está conforme.",
  "O status indica aprovado, pendente ou rejeitado com justificativas.",
  "A decisão final sempre passa por um revisor humano.",
]

const navPrimary = [
  { label: "Visão", href: "#visao" },
  { label: "Objetivo", href: "#objetivo" },
  { label: "Público", href: "#publico" },
  { label: "Valor", href: "#valor" },
  { label: "Fluxo", href: "#fluxo" },
  { label: "Papéis", href: "#papeis" },
  { label: "Fluxo completo", href: "#fluxo-completo" },
  { label: "Comunicação", href: "#comunicacao" },
]

const navSecondary = [
  { label: "Status", href: "#status" },
  { label: "Notificações", href: "#notificacoes" },
  { label: "KPIs", href: "#kpis" },
  { label: "Segurança", href: "#seguranca" },
  { label: "Futuro", href: "#futuro" },
  { label: "Resumo", href: "#resumo" },
  { label: "Boas práticas", href: "#boas-praticas" },
]

const publicoPrincipal = [
  "Equipe administrativa (conferência inicial).",
  "Médicos validadores (revisão clínica).",
  "Clínicas terceirizadas (emissão de ASOs).",
  "Coordenação de Saúde Ocupacional.",
]

const clienteFinal = [
  "Área de RH das empresas clientes que aguardam o ASO liberado.",
  "Admissões.",
  "Periódicos.",
  "Retornos.",
  "Mudanças de função.",
  "Demissões.",
]

const valorGerado = [
  {
    title: "Processamento automático",
    description:
      "OCR avançado extrai texto e identifica exames médicos automaticamente, eliminando digitação manual.",
  },
  {
    title: "Conformidade legal",
    description:
      "Garante aderência à NR-7 e PCMSO, com rastreabilidade completa e segurança jurídica.",
  },
  {
    title: "Revisão humana",
    description:
      "Validadores revisam casos críticos com suporte de IA, mantendo controle médico final.",
  },
]

const resultadosEsperados = [
  "Sistema unificado com automação inteligente.",
  "Redução de 50% no tempo de liberação.",
  "Redução de 70% em devoluções às clínicas.",
  "Visibilidade completa do status de cada ASO.",
  "Padronização de informações recebidas.",
]

const areasEnvolvidas = [
  "Coordenação Médica: responsável pelo processo.",
  "Administrativo: conferência inicial.",
  "Médico: validação clínica.",
  "TI: integração e automação.",
]

const fluxoCompleto = [
  {
    step: "1",
    title: "Envio do documento",
    details: ['Enviador faz upload de PDF na página "Anexar Prontuário".'],
  },
  {
    step: "2",
    title: "Processamento automático",
    details: [
      "OCR extrai texto e identifica CPF, exames e assinaturas.",
      "BRNET consulta exames obrigatórios para o CPF.",
      "IA compara exames encontrados vs. obrigatórios.",
    ],
  },
  {
    step: "3",
    title: "Decisão da IA",
    details: [
      "A IA sugere aprovação ou rejeição com justificativas.",
      "Aprovado pela IA: todos os exames obrigatórios encontrados.",
      "Rejeitado pela IA: faltam exames ou há discrepâncias.",
      "Importante: todos os documentos vão para checagem.",
    ],
  },
  {
    step: "4",
    title: "Todos vão para checagem",
    details: [
      "Todos os documentos processados ficam disponíveis em /checagem.",
      "Todos estão sujeitos à validação do revisor, mesmo os aprovados pela IA.",
    ],
  },
  {
    step: "5",
    title: "Validação humana (revisor)",
    details: [
      "Revisor acessa /checagem, vê a decisão da IA e decide o resultado final.",
      "Aprovar: documento validado definitivamente e arquivado.",
      "Rejeitar: documento volta para /pendentes com motivo.",
    ],
  },
]

const comunicacoes = [
  {
    title: "Anexar Prontuário → Checagem",
    details: [
      "Enviador faz upload em /anexar-prontuario.",
      "Sistema processa (OCR + BRNET + IA).",
      "Documento aparece em /checagem.",
      "Revisor recebe notificação de novo documento.",
    ],
    notifications: [
      'Enviador: "Processamento iniciado".',
      'Enviador: "Concluído".',
      'Revisor: "Novos documentos".',
    ],
  },
  {
    title: "Checagem → Pendentes (quando rejeita)",
    details: [
      "Revisor rejeita documento em /checagem e informa o motivo.",
      "Documento some de /checagem e aparece em /pendentes do enviador.",
      "Enviador pode corrigir e reenviar.",
    ],
    notifications: ['Enviador: "Documento rejeitado: [motivo]".', "Revisor não é notificado."],
  },
  {
    title: "Checagem → Histórico (quando aprova)",
    details: [
      "Revisor aprova documento em /checagem.",
      "Documento sai de /checagem e vai para /historico.",
      "Enviador não vê nada em /pendentes.",
    ],
    notifications: ["Aprovação é silenciosa para o enviador."],
  },
  {
    title: "Pendentes → Anexar Prontuário (reenvio)",
    details: [
      "Enviador vê documento em /pendentes, lê o motivo e corrige.",
      "Reenvia via /anexar-prontuario e o ciclo recomeça.",
    ],
    notifications: [
      'Enviador: "Processamento iniciado".',
      'Revisor: "Novos documentos".',
      "Sistema detecta duplicata e notifica quando aplicável.",
    ],
  },
]

const ecossistema = [
  {
    title: "/anexar-prontuario",
    subtitle: "Ponto de entrada de documentos.",
    receives: "Nenhum (input do usuário da clínica).",
    feeds: "Checagem, Pendentes (se resultado negativo da IA).",
  },
  {
    title: "/checagem",
    subtitle: "Centro de decisão.",
    receives: "Envio de documentos processados.",
    feeds: "Histórico (aprova) ou Pendentes (rejeita).",
  },
  {
    title: "/pendentes",
    subtitle: "Fila de correções.",
    receives: "Envio negativo da IA ou rejeição do revisor.",
    feeds: "Reenvio para Anexar Prontuário.",
  },
]


const futuroScore = [
  "Cada revisão, aprovação e fluxo completo gera um score de confiabilidade.",
  "Com histórico suficiente, documentos com score acima de 90 tendem à aprovação automática.",
  "A tendência é reduzir a passagem humana para casos de alto score, mantendo auditoria e amostragem.",
  "Isso libera o time clínico para exceções e decisões complexas, sem perder governança.",
]

const problemasDocumentais = [
  "Falta de padrão: clínicas enviam documentos com formatos diferentes.",
  "Dados incompletos: ausência de nome, CPF, data ou assinaturas.",
  "Assinaturas ilegíveis: carimbos e assinaturas de baixa qualidade.",
  "Versões incorretas: exames desatualizados enviados por engano.",
  "Terminologia inconsistente: termos diferentes para o mesmo exame.",
]

const gargalosOperacionais = [
  "Conferência manual morosa e sujeita a erros humanos.",
  "Falta de integração e retrabalho entre sistemas.",
  "Validação dupla de campos pelo administrativo e médico.",
  "Devoluções frequentes e alto índice de correções.",
  "Arquivos não padronizados dificultando busca e indexação.",
]

const mudas = [
  {
    tipo: "Espera",
    exemplo: "Tempo entre envio da clínica e conferência.",
    solucao: "Processamento automático imediato.",
  },
  {
    tipo: "Movimentação",
    exemplo: "Troca manual de arquivos entre e-mails e pastas.",
    solucao: "Sistema centralizado com workflow.",
  },
  {
    tipo: "Superprocessamento",
    exemplo: "Conferência dupla dos mesmos campos.",
    solucao: "IA valida e revisor confirma casos críticos.",
  },
  {
    tipo: "Defeitos",
    exemplo: "Documentos ilegíveis e dados incorretos.",
    solucao: "Validação automática com checklist obrigatório.",
  },
  {
    tipo: "Estoque",
    exemplo: "Acúmulo de exames aguardando correção.",
    solucao: "Notificações imediatas e fila priorizada.",
  },
  {
    tipo: "Talento",
    exemplo: "Médicos gastando tempo com checagem manual.",
    solucao: "Foco em decisões clínicas complexas.",
  },
]

const riscosCriticos = [
  "Não conformidade legal: ASO sem assinatura válida invalida laudo.",
  "Liberação incorreta: erro pode liberar colaborador inapto.",
  "Segurança da informação: documentos sensíveis sem controle.",
  "Retrabalho em massa: ausência de rastreabilidade.",
]

const mitigacoes = [
  "Validação automática com checklist obrigatório de campos críticos.",
  "Dupla validação: IA sugere e revisor decide.",
  "Controle de acesso com perfis específicos e logs de auditoria.",
  "Deduplicação por hash único para prevenir duplicatas.",
]

const kpis = [
  {
    indicador: "Tempo médio de liberação (Lead Time)",
    formula: "Data liberação - Data recebimento",
    meta: "Reduzir 50%",
  },
  {
    indicador: "Taxa de devoluções às clínicas",
    formula: "(Devolvidos / Recebidos) × 100",
    meta: "Reduzir 70%",
  },
  {
    indicador: "Taxa de ASOs aprovados sem pendência",
    formula: "(Aprovados direto / Total) × 100",
    meta: "Aumentar 40%",
  },
  {
    indicador: "Tempo médio de resposta da clínica",
    formula: "Data reenvio - Data devolução",
    meta: "Reduzir 60%",
  },
  {
    indicador: "Percentual de automação de checagem",
    formula: "(Processados via OCR / Total) × 100",
    meta: "80% até fase 2",
  },
]

const lgpd = [
  "Anonimização parcial com uso estritamente funcional.",
  "Minimização de dados: coleta apenas informações necessárias.",
  "Consentimento com documentação clara de autorização.",
  "Retenção legal com backup automático por no mínimo 5 anos.",
]

const controleAcesso = [
  "Perfis diferenciados: Enviador, Revisor, Admin.",
  "Autenticação corporativa com Google OAuth restrito a @grupobrmed.com.br.",
  "Acesso granular por documento e ação.",
  "Gestão de identidade com IAM e MFA (planejado).",
]

const segurancaTecnica = [
  "Criptografia em trânsito (HTTPS/TLS).",
  "Criptografia em repouso (AES-256).",
  "Ambientes segregados: desenvolvimento, homologação e produção.",
  "Storage seguro com controle de acesso e versionamento.",
]

const logsAuditoria = [
  "Trilha de auditoria: quem aprovou, quando e qual ação.",
  "Logs automáticos com timestamp de todas as operações.",
  "Versionamento com histórico completo de alterações.",
  "Backup diário com retenção mínima de 5 anos.",
]


function useInView(threshold = 0.2) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          observer.unobserve(entry.target)
        }
      },
      { threshold }
    )

    observer.observe(node)

    return () => observer.disconnect()
  }, [threshold])

  return { ref, inView }
}

function FlowStepCard({ step, index }: { step: FlowStep; index: number }) {
  const { ref, inView } = useInView(0.2)

  return (
    <div
      ref={ref}
      className={`transition-all duration-500 ease-out hover:-translate-y-1 hover:shadow-lg ${
        inView ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
      }`}
      style={{ transitionDelay: `${index * 120}ms` }}
    >
      <Card className="relative overflow-hidden border border-primary/15 bg-card/90 transition-colors hover:border-secondary/40">
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
        <CardContent className="space-y-3">
          <p className="text-base font-semibold text-foreground">
            Passo {step.step}: {step.title}
          </p>
          <p className="text-sm text-muted-foreground">{step.description}</p>
          <p className="text-sm text-muted-foreground">{step.details}</p>
        </CardContent>
      </Card>
    </div>
  )
}

export default function DocsPage() {
  const fluxoCompletoRef = useRef<HTMLDivElement | null>(null)
  const headerRef = useRef<HTMLElement | null>(null)
  const [headerHidden, setHeaderHidden] = useState(false)
  const [showToTop, setShowToTop] = useState(false)

  const scrollFluxoCompleto = (direction: 1 | -1) => {
    if (!fluxoCompletoRef.current) return
    fluxoCompletoRef.current.scrollBy({
      left: 320 * direction,
      behavior: "smooth",
    })
  }
  const sectionHighlight =
    "scroll-mt-24 transition-all duration-[1700ms] ease-out data-[highlight=true]:rounded-2xl data-[highlight=true]:bg-secondary/4 data-[highlight=true]:shadow-[0_18px_40px_-30px_rgba(0,120,145,0.35)]"

  const handleNavClick = (href: string) => (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    const target = document.querySelector(href)
    if (!target) return
    target.scrollIntoView({ behavior: "smooth", block: "center" })
    if (target instanceof HTMLElement) {
      target.dataset.highlight = "true"
      window.setTimeout(() => {
        target.dataset.highlight = "false"
      }, 2200)
    }
    if (window.history.replaceState) {
      window.history.replaceState(null, "", href)
    }
  }

  useEffect(() => {
    const node = headerRef.current
    if (!node) return
    const observer = new IntersectionObserver(
      ([entry]) => setHeaderHidden(!entry.isIntersecting),
      { threshold: 0.1 }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const onScroll = () => {
      setShowToTop(window.scrollY > 400)
    }
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <div className="min-h-screen bg-[#EEF1F4] text-foreground">
      <div className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -right-36 -top-36 h-96 w-96 rounded-full bg-[radial-gradient(circle_at_center,rgba(0,120,145,0.28),transparent_65%)]" />
          <div className="absolute -left-24 top-28 h-80 w-80 rounded-full bg-[radial-gradient(circle_at_center,rgba(25,59,79,0.2),transparent_65%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(0,120,145,0.08),rgba(25,59,79,0.08),rgba(0,120,145,0.04))]" />
        </div>

        <header
          ref={headerRef}
          className="relative border-b border-primary/10 bg-gradient-to-r from-primary via-[#0f566f] to-secondary text-white"
        >
          <div className="mx-auto w-full max-w-[90rem] px-4 py-8 sm:px-6">
            <div className="grid items-center gap-10 lg:gap-14 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
              <div className="flex items-center gap-5 lg:-ml-12">
                <div className="relative h-12 w-36">
                  <Image src="/logo.png" alt="ProntuAI" fill className="object-contain" priority />
                </div>
                <Badge className="ml-1 border border-white/30 bg-white/10 text-white">Guia de uso</Badge>
              </div>
              <div className="flex justify-start lg:justify-end">
                <a
                  href="/login"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-md bg-white/15 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-white/25"
                >
                  Acessar ProntuAI
                  <ArrowRight className="size-4" />
                </a>
              </div>
            </div>
          </div>
        </header>
      </div>

      <main className="mx-auto w-full max-w-[90rem] px-4 py-12 sm:px-6">
        <div className="grid items-start gap-10 lg:gap-14 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
          <aside
            className={`min-w-0 space-y-4 lg:sticky lg:h-fit lg:-ml-12 ${
              headerHidden ? "lg:top-1/2 lg:-translate-y-1/2" : "lg:top-24"
            }`}
          >
            <div className="rounded-xl border border-primary/15 bg-card/90 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Seções principais
              </p>
              <nav className="mt-3 flex flex-col gap-2 text-sm">
                {navPrimary.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    className="rounded-lg border border-transparent px-2 py-1 text-muted-foreground transition-colors hover:border-primary/20 hover:bg-primary/5 hover:text-foreground"
                    onClick={handleNavClick(item.href)}
                  >
                    {item.label}
                  </a>
                ))}
              </nav>
            </div>
            <div className="rounded-xl border border-primary/15 bg-card/90 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Qualidade e governança
              </p>
              <nav className="mt-3 flex flex-col gap-2 text-sm">
                {navSecondary.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    className="rounded-lg border border-transparent px-2 py-1 text-muted-foreground transition-colors hover:border-primary/20 hover:bg-primary/5 hover:text-foreground"
                    onClick={handleNavClick(item.href)}
                  >
                    {item.label}
                  </a>
                ))}
              </nav>
            </div>
            <div className="rounded-xl border border-primary/15 bg-card/90 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Documentação técnica
              </p>
              <a
                href="/docs-tecnica"
                className="mt-3 flex w-full items-start justify-between gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-primary/10"
              >
                <span className="break-words text-left">Acessar documentação técnica</span>
                <ArrowRight className="size-4 shrink-0 text-secondary" />
              </a>
            </div>
          </aside>

          <div className="min-w-0 flex flex-col gap-20">
            <section className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:gap-12">
              <div className="space-y-5">

                <Badge variant="secondary" className="w-fit bg-secondary/15 text-secondary">
                  Qualidade e Gestão
                </Badge>
                <div className="space-y-3">
                  <h1 className="text-3xl font-semibold text-foreground md:text-4xl">
                    Guia de Uso Prontu<span className="font-bold text-cyan-800">AI</span>
                  </h1>
                  <p className="text-sm text-muted-foreground md:text-base">
                    Este guia tem o objetivo de explicar o sistema, seu fluxo e como cada área
                    participa do processo de validação dos documentos médicos.
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <span className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
                    OCR + comparação BRNET
                  </span>
                  <span className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
                    Status rastreáveis
                  </span>
                  <span className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
                    Checagem humana
                  </span>
                </div>
              </div>

              <Card className="relative overflow-hidden border border-primary/15 bg-card/90 shadow-[0_16px_40px_-32px_rgba(15,86,111,0.7)]">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <BookOpen className="size-4 text-secondary" />
                    Início rápido
                  </CardTitle>
                  <CardDescription>
                    Visão geral para times operacionais e auditoria.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <div className="rounded-lg border border-primary/10 bg-primary/5 p-3">
                    <p className="text-xs font-semibold text-foreground">Entrada</p>
                    <p className="text-xs text-muted-foreground">Upload de prontuários e anexos</p>
                  </div>
                  <div className="rounded-lg border border-primary/10 bg-primary/5 p-3">
                    <p className="text-xs font-semibold text-foreground">Saída</p>
                    <p className="text-xs text-muted-foreground">Status, detalhes e decisão final</p>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <ArrowRight className="size-4 text-secondary" />
                    Atualizado para OCR, comparação BRNET e checagem humana.
                  </div>
                </CardContent>
              </Card>
            </section>


            <section id="visao" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
              <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Visão geral
              </Badge>
            <h2 className="text-2xl font-semibold text-foreground">ProntuAI em contexto</h2>
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>
                ProntuAI é uma plataforma de validação automatizada de documentos médicos para a BR
                MED. O sistema utiliza OCR e Inteligência Artificial para extrair informações de
                exames médicos, validá-los contra requisitos obrigatórios do sistema BRNET, e
                fornecer comparação inteligente.
              </p>
            </CardContent>
          </Card>
        </section>


        <section id="objetivo" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
              <Badge variant="outline" className="text-xs px-3 py-1 font-bold uppercase tracking-[0.08em] text-secondary">
                Objetivo central
              </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Digitalização e confiabilidade</h2>
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Objetivo central</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                Digitalizar, automatizar e integrar o processo de conferência, validação e
                liberação de ASOs, reduzindo o tempo de ciclo e aumentando a confiabilidade
                operacional e jurídica.
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="text-base">Gatilho de início</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                Recebimento de documentos médicos (ASO, exames complementares).
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Conclusão</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                Liberação final do ASO com comunicação automática.
              </CardContent>
            </Card>
          </div>
        </section>


        <section id="publico" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
              <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Público-alvo e stakeholders
              </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Quem participa do fluxo</h2>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Público principal</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {publicoPrincipal.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="text-base">Cliente final</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {clienteFinal.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
          </div>
        </section>


        <section id="valor" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
              <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary px-3 py-1">
                Valor gerado
              </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Benefícios operacionais</h2>
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            {valorGerado.map((item) => (
              <Card key={item.title} className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardHeader>
                  <CardTitle className="text-base">{item.title}</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">{item.description}</CardContent>
              </Card>
            ))}
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
            <CardHeader>
              <CardTitle className="text-base">Resultados esperados</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              {resultadosEsperados.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </CardContent>
          </Card>
        </section>


        <section id="areas" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
              <Badge variant="outline" className="text-xs px-3 py-1 font-bold uppercase tracking-[0.08em] text-secondary">
                Áreas envolvidas
              </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Responsabilidades internas</h2>
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              {areasEnvolvidas.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </CardContent>
          </Card>
        </section>


        <section id="fluxo" className={`space-y-8 ${sectionHighlight}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-4">
              <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Fluxo end-to-end
              </Badge>
              <h2 className="text-2xl font-semibold text-foreground">Fluxo principal</h2>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Target className="size-4 text-secondary" />
              OCR, comparação automática e revisão humana em um único ciclo.
            </div>
          </div>

          <div className="space-y-4">
            {flowSteps.map((step, index) => {
              return (
                <FlowStepCard key={step.step} step={step} index={index} />
              )
            })}
          </div>
        </section>


        <section id="fluxo-completo" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
            <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
              Fluxo completo de um documento
            </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Do envio à liberação final</h2>
          </div>
          <div className="relative">
            <div
              ref={fluxoCompletoRef}
              className="flex gap-4 overflow-x-auto px-8 pb-2 snap-x snap-mandatory [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            >
            {fluxoCompleto.map((item) => (
              <Card
                key={item.step}
                className="relative min-w-[260px] max-w-[320px] flex-1 snap-start overflow-hidden border border-primary/15 bg-card/90"
              >
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardHeader>
                  <CardTitle className="text-base">
                    Passo {item.step}: {item.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {item.details.map((detail) => (
                    <p key={detail}>{detail}</p>
                  ))}
                </CardContent>
              </Card>
            ))}
            </div>
            <button
              type="button"
              onClick={() => scrollFluxoCompleto(-1)}
              className="absolute left-0 top-1/2 inline-flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-primary/15 bg-primary/5 p-2 text-primary shadow-sm transition-colors hover:bg-primary/10"
              aria-label="Ver anterior"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => scrollFluxoCompleto(1)}
              className="absolute right-0 top-1/2 inline-flex translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-primary/15 bg-primary/5 p-2 text-primary shadow-sm transition-colors hover:bg-primary/10"
              aria-label="Ver próximo"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </section>


        <section id="papeis" className={`space-y-6 ${sectionHighlight}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-2xl font-semibold">Papéis e acessos</h2>
            <Badge variant="outline" className="text-xs">
              ADMIN · TIME INTERNO · CLÍNICA
            </Badge>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            {roleCards.map((role) => {
              const Icon = role.icon
              return (
                <Card
                  key={role.title}
                  className="relative overflow-hidden border border-primary/15 bg-card/90"
                >
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Icon className="size-5 text-secondary" />
                      {role.title}
                    </CardTitle>
                    <CardDescription>{role.description}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    <p className="text-xs font-semibold uppercase tracking-wide text-foreground/80">
                      Acesso às páginas
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {role.access.map((badge) => (
                        <Badge key={badge} variant="outline" className="border-primary/20 text-foreground">
                          {badge}
                        </Badge>
                      ))}
                    </div>
                    <div className="space-y-1 text-xs text-muted-foreground">
                      {role.points.map((item) => (
                        <p key={item}>{item}</p>
                      ))}
                    </div>
                    {role.actions ? (
                      <div className="space-y-1 text-xs text-muted-foreground">
                        <p className="text-xs font-semibold uppercase tracking-wide text-foreground/80">
                          Ações disponíveis
                        </p>
                        {role.actions.map((item) => (
                          <p key={item}>{item}</p>
                        ))}
                      </div>
                    ) : null}
                    {role.important ? (
                      <div className="rounded-lg border border-primary/10 bg-primary/5 p-3 text-xs text-muted-foreground">
                        {role.important}
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </section>


        <section id="status" className={`space-y-6 ${sectionHighlight}`}>
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-4">
              <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Status do documento
              </Badge>
              <h2 className="text-2xl font-semibold text-foreground">Decisão guiada e revisão humana</h2>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <AlertCircle className="size-5 text-secondary" />
                  Interpretação padrão dos resultados
                </CardTitle>
                <CardDescription>IA indica, humano decide.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                {statusItems.map((item) => {
                  const Icon = item.icon
                  return (
                    <div
                      key={item.title}
                      className={`flex items-start gap-3 rounded-lg border border-primary/10 ${item.bg} p-3`}
                    >
                      <Icon className={`mt-0.5 size-4 ${item.color}`} />
                      <div>
                        <p className="text-xs font-semibold text-foreground">{item.title}</p>
                        <p className="text-xs text-muted-foreground">{item.description}</p>
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>

            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <CheckCircle2 className="size-5 text-secondary" />
                  Fluxo de decisão
                </CardTitle>
                <CardDescription>Transparente para auditoria e operação.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {statusFlow.map((item) => (
                  <div key={item} className="flex items-start gap-2">
                    <ArrowRight className="mt-0.5 size-4 text-secondary" />
                    <p className="text-sm text-muted-foreground">{item}</p>
                  </div>
                ))}
                <div className="rounded-lg border border-primary/10 bg-primary/5 p-3 text-xs text-muted-foreground">
                  As justificativas ficam registradas para consulta e revisão posterior.
                </div>
              </CardContent>
            </Card>
          </div>
        </section>


        <section id="comunicacao" className={`space-y-8 ${sectionHighlight}`}>
          <div className="space-y-4">
            <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
              Comunicação entre páginas
            </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Como as telas se conectam</h2>
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardContent className="space-y-6 text-sm text-muted-foreground">
              {comunicacoes.map((item, index) => (
                <div
                  key={item.title}
                  className={`space-y-2 ${index === 0 ? "" : "border-t border-primary/10 pt-4"}`}
                >
                  <p className="text-sm font-semibold text-foreground">{item.title}</p>
                  <p>{item.details.join(" ")}</p>
                  <p>
                    <span className="font-semibold text-foreground">Notificações paralelas:</span>{" "}
                    {item.notifications.join(" ")}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>


        <section id="notificacoes" className={`space-y-6 ${sectionHighlight}`}>
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-4">
              <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                Notificações
              </Badge>
              <h2 className="text-2xl font-semibold text-foreground">Acompanhamento em tempo real</h2>
            </div>
          </div>
          <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Bell className="size-5 text-secondary" />
                  Central única de avisos
                </CardTitle>
                <CardDescription>Processamento, revisões e conclusões.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>
                  O sino de notificações concentra avisos de processamento, revisões e conclusões. O
                  progresso dos lotes aparece no topo enquanto o processamento está ativo.
                </p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <ArrowRight className="size-4 text-secondary" />
                  Clique nas notificações para abrir detalhes e ir direto ao documento.
                </div>
                <div className="rounded-lg border border-primary/10 bg-primary/5 p-3 text-xs text-muted-foreground">
                  Regra prática: cada mudança de estado gera uma notificação com data, origem e
                  destino do documento.
                </div>
              </CardContent>
            </Card>

            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Exemplos visuais</CardTitle>
                <CardDescription>Formato padrão das mensagens.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <div className="rounded-lg border border-primary/10 bg-primary/5 p-3">
                  <p className="text-xs font-semibold text-foreground">Enviador</p>
                  <div className="mt-2 space-y-2 text-xs text-muted-foreground">
                    <p className="rounded-md border border-primary/10 bg-white/80 px-3 py-2">
                      Processamento iniciado · 3 documentos
                    </p>
                    <p className="rounded-md border border-primary/10 bg-white/80 px-3 py-2">
                      Concluído · 2 aprovados, 1 com pendências (todos enviados para revisão)
                    </p>
                    <p className="rounded-md border border-primary/10 bg-white/80 px-3 py-2">
                      Documento rejeitado · Motivo: exame ilegível
                    </p>
                  </div>
                </div>
                <div className="rounded-lg border border-primary/10 bg-primary/5 p-3">
                  <p className="text-xs font-semibold text-foreground">Revisor</p>
                  <div className="mt-2 space-y-2 text-xs text-muted-foreground">
                    <p className="rounded-md border border-primary/10 bg-white/80 px-3 py-2">
                      Novos documentos aguardando revisão
                    </p>
                    <p className="rounded-md border border-primary/10 bg-white/80 px-3 py-2">
                      Lote atualizado · 5 documentos em checagem
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>


        <section id="riscos" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
            <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
              Dores e gargalos
            </Badge>
            <h2 className="text-2xl font-semibold text-foreground">
              Problemas resolvidos pelo ProntuAI
            </h2>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Problemas documentais</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {problemasDocumentais.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="text-base">Gargalos operacionais</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {gargalosOperacionais.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardHeader>
              <CardTitle className="text-base">Desperdícios identificados (MUDAs)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <div className="hidden grid-cols-[0.9fr_1.5fr_1.5fr] gap-3 text-xs font-semibold uppercase tracking-wide text-foreground/70 md:grid">
                <span>Tipo</span>
                <span>Exemplo</span>
                <span>Solução ProntuAI</span>
              </div>
              <div className="space-y-3">
                {mudas.map((item) => (
                  <div
                    key={item.tipo}
                    className="grid gap-2 rounded-lg border border-primary/10 bg-primary/5 p-3 md:grid-cols-[0.9fr_1.5fr_1.5fr]"
                  >
                    <p className="text-sm font-semibold text-foreground">{item.tipo}</p>
                    <p className="text-sm text-muted-foreground">{item.exemplo}</p>
                    <p className="text-sm text-muted-foreground">{item.solucao}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="text-base">Pontos de risco críticos</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {riscosCriticos.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Mitigações implementadas</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {mitigacoes.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
          </div>
        </section>


        <section id="kpis" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
            <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
              KPIs e indicadores
            </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Métricas de sucesso</h2>
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <div className="hidden grid-cols-[1.4fr_1.2fr_0.6fr] gap-3 text-xs font-semibold uppercase tracking-wide text-foreground/70 md:grid">
                <span>Indicador</span>
                <span>Fórmula / Fonte</span>
                <span>Meta</span>
              </div>
              <div className="space-y-3">
                {kpis.map((item) => (
                  <div
                    key={item.indicador}
                    className="grid gap-2 rounded-lg border border-primary/10 bg-primary/5 p-3 md:grid-cols-[1.4fr_1.2fr_0.6fr]"
                  >
                    <p className="text-sm font-semibold text-foreground">{item.indicador}</p>
                    <p className="text-sm text-muted-foreground">{item.formula}</p>
                    <p className="text-sm text-muted-foreground">{item.meta}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </section>


        <section id="seguranca" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
            <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
              Segurança, LGPD e governança
            </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Conformidade e proteção</h2>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Conformidade LGPD</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {lgpd.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="text-base">Controle de acesso</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {controleAcesso.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
              <CardHeader>
                <CardTitle className="text-base">Segurança técnica</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {segurancaTecnica.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
            <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
              <CardHeader>
                <CardTitle className="text-base">Logs e auditoria</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {logsAuditoria.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </CardContent>
            </Card>
          </div>
        </section>


        <section id="futuro" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
            <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
              Pra onde estamos caminhando
            </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Score de confiabilidade</h2>
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              {futuroScore.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </CardContent>
          </Card>
        </section>


        <section id="boas-praticas" className={`space-y-6 ${sectionHighlight}`}>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardHeader>
              <CardTitle className="text-base">Boas práticas de envio</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>Prefira PDFs legíveis, com todas as páginas do exame.</p>
              <p>Evite fotos cortadas ou páginas rotacionadas.</p>
              <p>Se houver laudo e exames separados, envie todos no mesmo lote.</p>
            </CardContent>
          </Card>
        </section>


        <section id="resumo" className={`space-y-6 ${sectionHighlight}`}>
          <div className="space-y-4">
            <Badge variant="outline" className="px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-secondary">
              Resumo executivo
            </Badge>
            <h2 className="text-2xl font-semibold text-foreground">Visão consolidada</h2>
          </div>
          <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
            <CardHeader>
              <CardTitle className="text-base">Situação atual</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              O processo atual é manual, moroso e vulnerável a falhas documentais, exigindo dupla
              conferência e intensa comunicação reativa com clínicas terceirizadas. O alto índice de
              devoluções e retrabalho impacta diretamente o tempo de liberação de ASOs.
            </CardContent>
          </Card>
          <Card className="relative overflow-hidden border border-primary/15 bg-primary/5">
            <div className="absolute left-0 top-0 h-full w-1 bg-secondary" />
            <CardContent className="text-sm text-foreground">
              ProntuAI transforma um processo manual vulnerável em um sistema automatizado,
              rastreável e eficiente, garantindo conformidade legal, segurança ocupacional e
              agilidade na liberação de ASOs para os clientes da BR MED.
            </CardContent>
          </Card>
        </section>

          </div>
        </div>
      </main>
      <footer className="border-t border-primary/10 bg-gradient-to-r from-primary via-[#0f566f] to-secondary text-white">
        <div className="mx-auto flex w-full max-w-[90rem] flex-wrap items-center justify-between gap-4 px-4 py-6 sm:px-6">
          <div className="flex items-center gap-3">
        
            <span className="text-xs uppercase tracking-[0.2em] text-white/70">Guia de Uso</span>
          </div>
          <div className="text-xs text-white/70">
            Prontu<span className="text-cyan-200">AI</span> · BR MED
          </div>
        </div>
      </footer>
      <button
        type="button"
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        className={`fixed bottom-6 right-6 z-50 inline-flex items-center justify-center rounded-full border border-primary/20 bg-teal-50 p-3 text-primary shadow-lg transition-all hover:bg-white ${
          showToTop ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        aria-label="Voltar ao topo"
      >
        <ChevronUp className="size-5" />
      </button>
    </div>
  )
}
