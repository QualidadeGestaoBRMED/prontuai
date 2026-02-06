"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import Image from "next/image"
import { useEffect, useRef, useState, type MouseEvent } from "react"
import { ArrowRight, Cpu, Database, Layers, ServerCog } from "lucide-react"

const navPrimary = [
  { label: "Visão", href: "#visao" },
  { label: "Pipeline", href: "#pipeline" },
  { label: "Stack", href: "#stack" },
  { label: "Integrações", href: "#integracoes" },
  { label: "Config", href: "#config" },
  { label: "Rotas", href: "#rotas" },
]

const navSecondary = [
  { label: "Auth", href: "#auth" },
  { label: "Deploy", href: "#deploy" },
  { label: "Observabilidade", href: "#observabilidade" },
  { label: "Segurança", href: "#seguranca" },
]

const pipelineSteps = [
  {
    title: "Recepção",
    description: "Entrada de PDFs e criação do lote de processamento.",
  },
  {
    title: "OCR",
    description: "Extração de texto, identificação de exames e metadados.",
  },
  {
    title: "BRNET",
    description: "Consulta dos exames obrigatórios por CPF.",
  },
  {
    title: "IA",
    description: "Comparação inteligente e geração de justificativas.",
  },
  {
    title: "Checagem",
    description: "Revisão humana com decisão final registrada.",
  },
]

const stackFront = [
  "Next.js 15 (App Router)",
  "React 19 + TypeScript",
  "Tailwind CSS 4 + shadcn/ui",
  "NextAuth (Google OAuth)",
]

const stackBack = [
  "FastAPI (Python 3.11+)",
  "OpenAI API + FAISS",
  "Docling / AWS Textract (opcional)",
  "Gunicorn + Uvicorn workers",
]

const integracoes = [
  {
    title: "OpenAI",
    description: "Geração de análises, embeddings e validações por IA.",
  },
  {
    title: "BRNET",
    description: "Requisitos obrigatórios por CPF para comparação dos exames.",
  },
  {
    title: "OCR",
    description: "Docling como padrão e Textract como fallback opcional.",
  },
]

const envVars = [
  { key: "OPENAI_API_KEY", description: "Chave da OpenAI para IA e embeddings." },
  { key: "BRMED_USERNAME", description: "Usuário de integração BRMED." },
  { key: "BRMED_PASSWORD", description: "Senha de integração BRMED." },
  { key: "USE_TEXTRACT", description: "Ativa AWS Textract (true/false)." },
  { key: "AWS_ACCESS_KEY_ID", description: "Credencial AWS (Textract)." },
  { key: "AWS_SECRET_ACCESS_KEY", description: "Credencial AWS (Textract)." },
  { key: "AWS_REGION", description: "Região AWS para Textract/S3." },
  { key: "AWS_S3_BUCKET", description: "Bucket usado pelo Textract." },
  { key: "MODELO_GPT", description: "Modelo OpenAI principal (ex.: gpt-4o-mini)." },
  { key: "MODELO_EMBEDDING", description: "Modelo de embedding (ex.: text-embedding-3-large)." },
  { key: "K_VIZINHOS_FAQ", description: "Número de vizinhos no FAQ." },
  { key: "MAX_DISTANCIA_FAQ", description: "Limite de distância para FAQ." },
  { key: "WORKERS", description: "Quantidade de workers do Gunicorn." },
  { key: "JWT_SECRET_KEY", description: "Segredo para tokens JWT." },
  { key: "JWT_ALGORITHM", description: "Algoritmo JWT (ex.: HS256)." },
  { key: "ACCESS_TOKEN_EXPIRE_HOURS", description: "Expiração do token em horas." },
  { key: "DATABASE_URL", description: "URL do banco de dados." },
]

const routes = [
  { path: "/login", description: "Autenticação via Google OAuth." },
  { path: "/docs", description: "Guia de uso do ProntuAI." },
  { path: "/docs-tecnica", description: "Documentação técnica." },
  { path: "/anexar-prontuario", description: "Upload e processamento de documentos." },
  { path: "/pendentes", description: "Documentos rejeitados que precisam de ação." },
  { path: "/checagem", description: "Validação manual com aprovação/rejeição." },
  { path: "/historico", description: "Arquivo completo de processamentos." },
  { path: "/insights", description: "Indicadores e análises operacionais." },
]

const deployNotes = [
  "Serviço backend em Render com runtime Python.",
  "Build: pip install + requirements.txt.",
  "Start: gunicorn main:app com Uvicorn workers.",
  "Região padrão: Oregon.",
]

const authNotes = [
  "Front-end com NextAuth e Google OAuth corporativo.",
  "Backend com JWT para sessões e validações.",
]

const observabilityNotes = [
  "Logs automáticos com timestamp para auditoria.",
  "Histórico de decisões e justificativas por documento.",
  "Trilha de auditoria com usuário, data e ação.",
]

const securityNotes = [
  "Criptografia em trânsito (HTTPS/TLS).",
  "Criptografia em repouso (AES-256).",
  "Acesso granular por perfis e ações.",
  "Retenção e backup conforme requisitos legais.",
]

export default function DocsTecnicaPage() {
  const headerRef = useRef<HTMLElement | null>(null)
  const [headerHidden, setHeaderHidden] = useState(false)
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
              <div className="flex items-center gap-5 xl:-ml-12">
                <div className="relative h-12 w-36">
                  <Image src="/logo.png" alt="ProntuAI" fill className="object-contain" priority />
                </div>
                <Badge className="ml-1 border border-white/30 bg-white/10 text-white">Documentação técnica</Badge>
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
            className={`min-w-0 space-y-4 lg:sticky lg:h-fit xl:-ml-12 ${
              headerHidden ? "lg:top-1/2 lg:-translate-y-1/2" : "lg:top-24"
            }`}
          >
            <div className="rounded-xl border border-primary/15 bg-card/90 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">Seções principais</p>
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
              <p className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">Qualidade e governança</p>
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
          </aside>

          <div className="min-w-0 flex flex-col gap-20">
            <section className={`space-y-6 ${sectionHighlight}`} id="visao">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Visão técnica
                </Badge>
                <h1 className="text-3xl font-semibold text-foreground md:text-4xl">
                  Documentação técnica do Prontu<span className="font-bold text-cyan-800">AI</span> | (EM CONSTRUÇÃO)
                </h1>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <p>
                    Este guia técnico descreve a arquitetura, integrações e configurações do ProntuAI,
                    servindo como referência para desenvolvimento, suporte e operação.
                  </p>
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="pipeline">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Pipeline técnico
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Fluxo de processamento</h2>
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                {pipelineSteps.map((step) => (
                  <Card key={step.title} className="relative overflow-hidden border border-primary/15 bg-card/90">
                    <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Layers className="size-4 text-secondary" />
                        {step.title}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">{step.description}</CardContent>
                  </Card>
                ))}
              </div>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="stack">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Stack principal
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Tecnologias</h2>
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Cpu className="size-4 text-secondary" />
                      Front-end
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    {stackFront.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </CardContent>
                </Card>
                <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ServerCog className="size-4 text-secondary" />
                      Back-end
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    {stackBack.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </CardContent>
                </Card>
              </div>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="integracoes">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Integrações
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Serviços externos</h2>
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                {integracoes.map((item) => (
                  <Card key={item.title} className="relative overflow-hidden border border-primary/15 bg-card/90">
                    <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Database className="size-4 text-secondary" />
                        {item.title}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">{item.description}</CardContent>
                  </Card>
                ))}
              </div>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="config">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Configurações
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Variáveis de ambiente</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  {envVars.map((item, index) => (
                    <div
                      key={item.key}
                      className={`space-y-1 ${index === 0 ? "" : "border-t border-primary/10 pt-3"}`}
                    >
                      <p className="text-sm font-semibold text-foreground">{item.key}</p>
                      <p>{item.description}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="rotas">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Rotas
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Mapa de navegação</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  {routes.map((item, index) => (
                    <div
                      key={item.path}
                      className={`space-y-1 ${index === 0 ? "" : "border-t border-primary/10 pt-3"}`}
                    >
                      <p className="text-sm font-semibold text-foreground">{item.path}</p>
                      <p>{item.description}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="auth">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Auth
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Autenticação e autorização</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {authNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="deploy">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Deploy
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Deploy e runtime</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {deployNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="observabilidade">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Observabilidade
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Logs e auditoria</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-secondary to-primary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {observabilityNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>

            <section className={`space-y-6 ${sectionHighlight}`} id="seguranca">
              <div className="space-y-4">
                <Badge variant="outline" className="text-xs font-bold uppercase tracking-[0.08em] text-secondary">
                  Segurança
                </Badge>
                <h2 className="text-2xl font-semibold text-foreground">Boas práticas</h2>
              </div>
              <Card className="relative overflow-hidden border border-primary/15 bg-card/90">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-secondary via-primary to-secondary" />
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {securityNotes.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </CardContent>
              </Card>
            </section>
          </div>
        </div>
      </main>

      <footer className="border-t border-primary/10 bg-gradient-to-r from-primary via-[#0f566f] to-secondary text-white">
        <div className="mx-auto flex w-full max-w-[90rem] flex-wrap items-center justify-between gap-4 px-4 py-6 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="relative h-8 w-24">
              <Image src="/logo.png" alt="ProntuAI" fill className="object-contain" />
            </div>
            <span className="text-xs uppercase tracking-[0.2em] text-white/70">Documentação técnica</span>
          </div>
          <div className="text-xs text-white/70">Prontu<span className="text-cyan-200">AI</span> · BR MED</div>
        </div>
      </footer>
    </div>
  )
}
