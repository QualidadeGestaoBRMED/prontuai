import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  ArrowDown,
  ArrowRight,
  Users,
  Bell,
  Shield,
  Zap,
  Target,
  TrendingDown,
  TrendingUp,
  FileCheck,
  Clock
} from "lucide-react"

export default function DocsPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      {/* Header */}
      <header className="border-b bg-white/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
           
            <div>
              <h1 className="text-2xl font-bold">ProntuAI</h1>
              <p className="text-sm text-muted-foreground">Documentação do Sistema</p>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-6 py-12 max-w-6xl">
        {/* Visão Geral */}
        <section className="mb-16">
          <div className="mb-8">
            <h2 className="text-3xl font-bold mb-2">Visão Geral</h2>
            <p className="text-lg text-muted-foreground mb-6">
              ProntuAI é uma plataforma de validação automatizada de documentos médicos para a BR MED.
              O sistema utiliza OCR e Inteligência Artificial para extrair informações de exames médicos,
              validá-los contra requisitos obrigatórios do sistema BRNET, e fornecer comparação inteligente.
            </p>

            <div className="bg-blue-50 border-l-4 border-l-blue-500 rounded-lg p-6 mb-6">
              <div className="flex items-start gap-3">
                <Target className="h-6 w-6 text-blue-600 shrink-0 mt-1" />
                <div>
                  <h3 className="font-semibold text-blue-900 mb-2">Objetivo Central</h3>
                  <p className="text-sm text-blue-800 mb-3">
                    Digitalizar, automatizar e integrar o processo de conferência, validação e liberação de ASOs,
                    reduzindo o tempo de ciclo e aumentando a confiabilidade operacional e jurídica.
                  </p>
                  <div className="grid md:grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="font-semibold text-blue-900 mb-1">Gatilho de Início:</p>
                      <p className="text-blue-800">Recebimento de documentos médicos (ASO, exames complementares)</p>
                    </div>
                    <div>
                      <p className="font-semibold text-blue-900 mb-1">Conclusão:</p>
                      <p className="text-blue-800">Liberação final do ASO + comunicação automática</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <Card className="mb-6">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-purple-600" />
                  Público-Alvo e Stakeholders
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <h4 className="font-semibold text-sm mb-2">Público Principal:</h4>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li>• Equipe administrativa (conferência inicial)</li>
                      <li>• Médicos validadores (revisão clínica)</li>
                      <li>• Clínicas terceirizadas (emissão de ASOs)</li>
                      <li>• Coordenação de Saúde Ocupacional</li>
                    </ul>
                  </div>
                  <div>
                    <h4 className="font-semibold text-sm mb-2">Cliente Final:</h4>
                    <p className="text-sm text-muted-foreground mb-2">
                      Área de RH das empresas clientes, que aguardam o ASO liberado para efetivar:
                    </p>
                    <div className="flex flex-wrap gap-1">
                      <Badge variant="outline" className="text-xs">Admissões</Badge>
                      <Badge variant="outline" className="text-xs">Periódicos</Badge>
                      <Badge variant="outline" className="text-xs">Retornos</Badge>
                      <Badge variant="outline" className="text-xs">Mudanças de Função</Badge>
                      <Badge variant="outline" className="text-xs">Demissões</Badge>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="mb-6">
            <h3 className="text-xl font-bold mb-4">Valor Gerado pelo Sistema</h3>
            <div className="grid md:grid-cols-3 gap-4">
              <Card>
                <CardHeader>
                  <Zap className="h-8 w-8 text-blue-600 mb-2" />
                  <CardTitle>Processamento Automático</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    OCR avançado extrai texto e identifica exames médicos automaticamente,
                    eliminando digitação manual
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <Shield className="h-8 w-8 text-green-600 mb-2" />
                  <CardTitle>Conformidade Legal</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Garante aderência à NR-7 e PCMSO, com rastreabilidade completa e
                    segurança jurídica
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <Users className="h-8 w-8 text-purple-600 mb-2" />
                  <CardTitle>Revisão Humana</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Validadores revisam casos críticos com suporte de IA, mantendo
                    controle médico final
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <Card className="bg-green-50 border-green-200">
              <CardHeader>
                <CardTitle className="text-green-900 flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  Resultados Esperados
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-sm text-green-800 space-y-2">
                  <li>✅ Sistema unificado com automação inteligente</li>
                  <li>✅ Redução de 50% no tempo de liberação</li>
                  <li>✅ Redução de 70% em devoluções às clínicas</li>
                  <li>✅ Visibilidade completa do status de cada ASO</li>
                  <li>✅ Padronização de informações recebidas</li>
                </ul>
              </CardContent>
            </Card>

            <Card className="bg-amber-50 border-amber-200">
              <CardHeader>
                <CardTitle className="text-amber-900 flex items-center gap-2">
                  <FileCheck className="h-5 w-5" />
                  Áreas Envolvidas
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-sm text-amber-800 space-y-2">
                  <li>• <strong>Coordenação Médica:</strong> responsável pelo processo</li>
                  <li>• <strong>Administrativo:</strong> conferência inicial</li>
                  <li>• <strong>Médico:</strong> validação clínica</li>
                  <li>• <strong>TI:</strong> integração e automação</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-12" />

        {/* Papéis de Usuário */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Papéis de Usuário</h2>

          <div className="space-y-6">
            {/* Enviador */}
            <Card className="border-l-4 border-l-blue-500">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Badge className="bg-blue-500">Enviador</Badge>
                  <CardTitle>Responsável por enviar documentos</CardTitle>
                </div>
                <CardDescription>
                  Faz upload de PDFs médicos e acompanha o processamento e validação
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <h4 className="font-semibold mb-2">Acesso às páginas:</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline">Enviar Exames</Badge>
                      <Badge variant="outline">Pendentes</Badge>
                    </div>
                  </div>

                  <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                    <div className="flex gap-2 items-start">
                      <AlertCircle className="h-5 w-5 text-yellow-600 shrink-0 mt-0.5" />
                      <div>
                        <h5 className="font-semibold text-yellow-900 mb-1">Importante sobre /pendentes</h5>
                        <ul className="text-sm text-yellow-800 space-y-1">
                          <li>✅ <strong>APARECEM:</strong> Apenas documentos rejeitados (pela IA ou Revisor) </li>
                          <li>❌ <strong>NÃO APARECEM:</strong> Documentos aprovados (pela IA ou Revisor)</li>
                          <li>💡 <strong>Resumo:</strong> Enviador só vê rejeições finais do Revisor que precisa corrigir</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Revisor */}
            <Card className="border-l-4 border-l-green-500">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Badge className="bg-green-500">Revisor</Badge>
                  <CardTitle>Valida documentos processados</CardTitle>
                </div>
                <CardDescription>
                  Analisa documentos e toma decisões de aprovar ou rejeitar com justificativas
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <h4 className="font-semibold mb-2">Acesso às páginas:</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline">Checagem</Badge>
                    </div>
                  </div>

                  <div>
                    <h4 className="font-semibold mb-2">Ações disponíveis:</h4>
                    <div className="grid gap-2">
                      <div className="flex items-center gap-2 text-sm">
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                        <span><strong>Aprovar:</strong> Documento validado e liberado</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <XCircle className="h-4 w-4 text-red-600" />
                        <span><strong>Rejeitar:</strong> Documento retorna ao enviador com motivo</span>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Admin */}
            <Card className="border-l-4 border-l-purple-500">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Badge className="bg-purple-500">Admin</Badge>
                  <CardTitle>Gestão completa do sistema</CardTitle>
                </div>
                <CardDescription>
                  Acesso total a todas as funcionalidades incluindo analytics e configurações
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div>
                  <h4 className="font-semibold mb-2">Acesso às páginas:</h4>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">Enviar Exames</Badge>
                    <Badge variant="outline">Pendentes</Badge>
                    <Badge variant="outline">Checagem</Badge>
                    <Badge variant="outline">Histórico</Badge>
                    <Badge variant="outline">Insights</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-12" />

        {/* Fluxo Completo */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Fluxo Completo de um Documento</h2>

          <div className="space-y-4">
            {/* Passo 1 */}
            <Card>
              <CardHeader className="bg-blue-50">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold">1</div>
                  <CardTitle>Envio do Documento</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">
                  <strong>Enviador</strong> faz upload de PDF na página &ldquo;Enviar Exames&rdquo;
                </p>
              </CardContent>
            </Card>

            <div className="flex justify-center">
              <ArrowDown className="h-6 w-6 text-muted-foreground" />
            </div>

            {/* Passo 2 */}
            <Card>
              <CardHeader className="bg-purple-50">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-purple-600 text-white flex items-center justify-center font-bold">2</div>
                  <CardTitle>Processamento Automático</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">OCR</Badge>
                    <span>Extrai texto e identifica CPF, exames e assinaturas</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">BRNET</Badge>
                    <span>Consulta exames obrigatórios para o CPF</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">Validação IA</Badge>
                    <span>Compara exames encontrados vs. obrigatórios</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="flex justify-center">
              <ArrowDown className="h-6 w-6 text-muted-foreground" />
            </div>

            {/* Passo 3 - Decisão da IA */}
            <Card>
              <CardHeader className="bg-amber-50">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-amber-600 text-white flex items-center justify-center font-bold">3</div>
                  <CardTitle>Decisão da IA</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-4">
                  A IA analisa e sugere aprovação ou rejeição, mas TODOS os documentos vão para Checagem
                </p>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="border-2 border-green-300 rounded-lg p-3 bg-green-50">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="h-5 w-5 text-green-600" />
                      <h4 className="font-semibold text-green-900 text-sm">Aprovado pela IA</h4>
                    </div>
                    <p className="text-xs text-green-800">
                      Todos os exames obrigatórios encontrados
                    </p>
                  </div>
                  <div className="border-2 border-yellow-300 rounded-lg p-3 bg-yellow-50">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertCircle className="h-5 w-5 text-yellow-600" />
                      <h4 className="font-semibold text-yellow-900 text-sm">Rejeitado pela IA</h4>
                    </div>
                    <p className="text-xs text-yellow-800">
                      Faltam exames ou há discrepâncias
                    </p>
                  </div>
                </div>
                <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="text-sm font-semibold text-blue-900 mb-1">⚠️ Importante:</p>
                  <p className="text-xs text-blue-800">
                    AMBOS os tipos (aprovados E rejeitados pela IA) seguem para /checagem.
                    A decisão final é do Revisor.
                  </p>
                </div>
              </CardContent>
            </Card>

            <div className="flex justify-center">
              <ArrowDown className="h-6 w-6 text-muted-foreground" />
            </div>

            {/* Passo 4 */}
            <Card>
              <CardHeader className="bg-purple-50">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-purple-600 text-white flex items-center justify-center font-bold">4</div>
                  <CardTitle>TODOS vão para Checagem</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-3">
                  Todos os documentos processados ficam disponíveis em /checagem
                </p>
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                  <p className="text-xs text-yellow-800">
                    📌 Todos os documentos estão sujeitos a validação do Revisor, mesmo que alguns não necessitem de ação (Como os aprovados pela IA).
                  </p>
                </div>
              </CardContent>
            </Card>

            <div className="flex justify-center">
              <ArrowDown className="h-6 w-6 text-muted-foreground" />
            </div>

            {/* Passo 5 */}
            <Card>
              <CardHeader className="bg-green-50">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-green-600 text-white flex items-center justify-center font-bold">5</div>
                  <CardTitle>Validação Humana (Revisor)</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-4">
                  <strong>Revisor</strong> acessa /checagem, vê a decisão da IA como referência, e toma a decisão final
                </p>

                <div className="grid md:grid-cols-2 gap-4">
                  <div className="border rounded-lg p-3 bg-green-50">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                      <h5 className="font-semibold text-sm">Aprovar</h5>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      ✅ Documento validado definitivamente<br />
                      ⚪ Enviador NÃO é notificado<br />
                      📊 Documento arquivado (fim do fluxo)
                    </p>
                  </div>

                  <div className="border rounded-lg p-3 bg-red-50">
                    <div className="flex items-center gap-2 mb-2">
                      <XCircle className="h-4 w-4 text-red-600" />
                      <h5 className="font-semibold text-sm">Rejeitar (com motivo)</h5>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      🔄 Documento vai para /pendentes<br />
                      🔔 Enviador recebe notificação com motivo<br />
                      ♻️ Enviador pode corrigir e reenviar
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-12" />

        {/* Interações Entre Páginas */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Como as Páginas se Comunicam</h2>
          <p className="text-muted-foreground mb-8">
            Entenda como as ações em uma página impactam outras telas e como o sistema de notificações acompanha tudo em paralelo.
          </p>

          <div className="space-y-6">
            {/* Enviar → Checagem */}
            <Card className="border-l-4 border-l-blue-500">
              <CardHeader className="bg-blue-50">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Badge className="bg-blue-500">Enviar Exames</Badge>
                      <ArrowRight className="h-5 w-5" />
                      <Badge className="bg-green-500">Checagem</Badge>
                    </CardTitle>
                    <CardDescription className="mt-2">
                      Todo documento enviado é processado e vai para Checagem
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <h5 className="font-semibold text-sm mb-2">O que acontece:</h5>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li>• Enviador faz upload em /enviar-docs</li>
                      <li>• Sistema processa (OCR + BRNET + IA)</li>
                      <li>• Documento aparece em /checagem</li>
                      <li>• Revisor recebe notificação de novo documento</li>
                    </ul>
                  </div>
                  <div className="bg-blue-50 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <Bell className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
                      <div className="text-xs">
                        <p className="font-semibold text-blue-900 mb-1">Notificações paralelas:</p>
                        <p className="text-blue-800">→ Enviador: &ldquo;Processamento iniciado&rdquo;</p>
                        <p className="text-blue-800">→ Enviador: &ldquo;Concluído&rdquo;</p>
                        <p className="text-blue-800">→ Revisor: &ldquo;Novos documentos&rdquo;</p>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Checagem → Pendentes (Rejeição) */}
            <Card className="border-l-4 border-l-red-500">
              <CardHeader className="bg-red-50">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Badge className="bg-green-500">Checagem</Badge>
                      <ArrowRight className="h-5 w-5" />
                      <Badge className="bg-blue-500">Pendentes</Badge>
                      <span className="text-sm font-normal text-muted-foreground">(Quando REJEITA)</span>
                    </CardTitle>
                    <CardDescription className="mt-2">
                      Revisor rejeita documento → Volta para o Enviador em /pendentes
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <h5 className="font-semibold text-sm mb-2">O que acontece:</h5>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li>• Revisor clica &ldquo;Rejeitar&rdquo; em /checagem</li>
                      <li>• Deve informar o motivo da rejeição</li>
                      <li>• Documento some de /checagem</li>
                      <li>• Documento aparece em /pendentes do Enviador</li>
                      <li>• Enviador pode corrigir e reenviar</li>
                    </ul>
                  </div>
                  <div className="bg-red-50 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <Bell className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                      <div className="text-xs">
                        <p className="font-semibold text-red-900 mb-1">Notificações paralelas:</p>
                        <p className="text-red-800">→ Enviador: &ldquo;Documento rejeitado: [motivo]&rdquo;</p>
                        <p className="text-muted-foreground text-xs mt-2 italic">
                          ⚠️ Revisor NÃO recebe notificação (ele fez a ação)
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Checagem → Arquivo (Aprovação) */}
            <Card className="border-l-4 border-l-green-500">
              <CardHeader className="bg-green-50">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Badge className="bg-green-500">Checagem</Badge>
                      <ArrowRight className="h-5 w-5" />
                      <Badge variant="outline">Histórico</Badge>
                      <span className="text-sm font-normal text-muted-foreground">(Quando APROVA)</span>
                    </CardTitle>
                    <CardDescription className="mt-2">
                      Revisor aprova documento → Arquivado (fim do fluxo)
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <h5 className="font-semibold text-sm mb-2">O que acontece:</h5>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li>• Revisor clica &ldquo;Aprovar&rdquo; em /checagem</li>
                      <li>• Documento some de /checagem</li>
                      <li>• Documento vai para /historico (arquivo)</li>
                      <li>• Enviador NÃO vê nada em /pendentes</li>
                      <li>• Fluxo encerrado com sucesso</li>
                    </ul>
                  </div>
                  <div className="bg-green-50 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <Bell className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
                      <div className="text-xs">
                        <p className="font-semibold text-green-900 mb-1">Notificações paralelas:</p>
                        <p className="text-green-800">→ NINGUÉM é notificado</p>
                        <p className="text-muted-foreground text-xs mt-2 italic">
                          ⚪ Aprovação é silenciosa para o Enviador
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Pendentes → Enviar (Reenvio) */}
            <Card className="border-l-4 border-l-purple-500">
              <CardHeader className="bg-purple-50">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Badge className="bg-blue-500">Pendentes</Badge>
                      <ArrowRight className="h-5 w-5" />
                      <Badge className="bg-blue-500">Enviar Exames</Badge>
                    </CardTitle>
                    <CardDescription className="mt-2">
                      Enviador corrige e reenvia documento rejeitado
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <h5 className="font-semibold text-sm mb-2">O que acontece:</h5>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li>• Enviador vê documento em /pendentes</li>
                      <li>• Lê o motivo da rejeição</li>
                      <li>• Corrige o documento</li>
                      <li>• Reenvia via /enviar-docs</li>
                      <li>• Ciclo recomeça (OCR → Checagem)</li>
                    </ul>
                  </div>
                  <div className="bg-purple-50 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <Bell className="h-4 w-4 text-purple-600 mt-0.5 shrink-0" />
                      <div className="text-xs">
                        <p className="font-semibold text-purple-900 mb-1">Notificações paralelas:</p>
                        <p className="text-purple-800">→ Enviador: &ldquo;Processamento iniciado&rdquo;</p>
                        <p className="text-purple-800">→ Revisor: &ldquo;Novos documentos&rdquo;</p>
                        <p className="text-muted-foreground text-xs mt-2 italic">
                          🔄 Sistema detecta duplicata? Bloqueia e notifica
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Visão Geral das Interações */}
            <Card className="bg-slate-50">
              <CardHeader>
                <CardTitle>Resumo Visual do Ecossistema</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="bg-white rounded-lg p-4 border-2 border-blue-200">
                      <h5 className="font-semibold text-sm mb-2 text-blue-900">📤 /enviar-docs</h5>
                      <p className="text-xs text-muted-foreground mb-2">Ponto de entrada de documentos</p>
                      <div className="text-xs space-y-1">
                        <p>← Recebe de: <Badge variant="outline" className="text-xs">Nenhum</Badge> (input do usuário enviador da clínica)</p>
                        <p>→ Alimenta: <Badge variant="outline" className="text-xs">Checagem</Badge></p>
                        <p>→ Alimenta: <Badge variant="outline" className="text-xs">Pendentes</Badge> (se resultado negativo pela IA)</p>
                      </div>
                    </div>

                    <div className="bg-white rounded-lg p-4 border-2 border-green-200">
                      <h5 className="font-semibold text-sm mb-2 text-green-900">✅ /checagem</h5>
                      <p className="text-xs text-muted-foreground mb-2">Centro de decisão</p>
                      <div className="text-xs space-y-1">
                        <p>← Recebe de: <Badge variant="outline" className="text-xs">Enviar</Badge></p>
                        <p>→ Aprova para: <Badge variant="outline" className="text-xs">Histórico</Badge></p>
                        <p>→ Rejeita para: <Badge variant="outline" className="text-xs">Pendentes</Badge></p>
                      </div>
                    </div>

                    <div className="bg-white rounded-lg p-4 border-2 border-amber-200">
                      <h5 className="font-semibold text-sm mb-2 text-amber-900">⏳ /pendentes</h5>
                      <p className="text-xs text-muted-foreground mb-2">Fila de correções</p>
                      <div className="text-xs space-y-1">
                        <p>← Recebe de: <Badge variant="outline" className="text-xs">Enviar</Badge> (negativo pela IA) ou <Badge variant="outline" className="text-xs">Checagem</Badge> (rejeitado)</p>
                        <p>→ Alimenta: <Badge variant="outline" className="text-xs">Histórico</Badge></p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div className="flex items-start gap-2">
                      <Bell className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" />
                      <div>
                        <h5 className="font-semibold text-blue-900 mb-2">Sistema de Notificações em Paralelo</h5>
                        <p className="text-sm text-blue-800">
                          Enquanto os documentos transitam entre as páginas, o sistema de notificações
                          informa Enviadores e Revisores sobre cada mudança de estado em tempo real.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-12" />

        {/* Dores e Gargalos */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Dores, Gargalos e Pontos de Risco</h2>
          <p className="text-muted-foreground mb-8">
            Problemas identificados no processo manual que o ProntuAI resolve através de automação e padronização.
          </p>

          <div className="grid md:grid-cols-2 gap-6 mb-6">
            {/* Problemas Documentais */}
            <Card className="border-l-4 border-l-red-500">
              <CardHeader className="bg-red-50">
                <CardTitle className="text-red-900 flex items-center gap-2">
                  <XCircle className="h-5 w-5" />
                  Problemas Documentais
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <ul className="text-sm space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="text-red-600 shrink-0">•</span>
                    <span><strong>Falta de padrão:</strong> clínicas enviam documentos com formatos diferentes</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-red-600 shrink-0">•</span>
                    <span><strong>Dados incompletos:</strong> ausência de nome, CPF, data ou assinaturas</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-red-600 shrink-0">•</span>
                    <span><strong>Assinaturas ilegíveis:</strong> carimbos e assinaturas médicas de baixa qualidade</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-red-600 shrink-0">•</span>
                    <span><strong>Versões incorretas:</strong> exames desatualizados enviados por engano</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-red-600 shrink-0">•</span>
                    <span><strong>Terminologia inconsistente:</strong> termos diferentes para o mesmo tipo de exame</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Gargalos Operacionais */}
            <Card className="border-l-4 border-l-orange-500">
              <CardHeader className="bg-orange-50">
                <CardTitle className="text-orange-900 flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  Gargalos Operacionais
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <ul className="text-sm space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="text-orange-600 shrink-0">•</span>
                    <span><strong>Conferência manual:</strong> processo moroso e sujeito a erros humanos</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-orange-600 shrink-0">•</span>
                    <span><strong>Falta de integração:</strong> sistemas isolados exigem retrabalho</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-orange-600 shrink-0">•</span>
                    <span><strong>Validação dupla:</strong> administrativo e médico conferem os mesmos campos</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-orange-600 shrink-0">•</span>
                    <span><strong>Devoluções frequentes:</strong> alto índice de correções necessárias</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-orange-600 shrink-0">•</span>
                    <span><strong>Arquivos não padronizados:</strong> dificuldade em busca e indexação</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>

          {/* Desperdícios Lean */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingDown className="h-5 w-5 text-purple-600" />
                Desperdícios Identificados (MUDAs - Lean)
              </CardTitle>
              <CardDescription>
                Tipos de desperdício que o sistema elimina ou minimiza
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-semibold">Tipo de MUDA</th>
                      <th className="text-left p-3 font-semibold">Exemplo no Processo Manual</th>
                      <th className="text-left p-3 font-semibold">Solução ProntuAI</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Espera</td>
                      <td className="p-3 text-muted-foreground">Tempo entre envio da clínica e conferência</td>
                      <td className="p-3 text-green-700">Processamento automático imediato</td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Movimentação</td>
                      <td className="p-3 text-muted-foreground">Troca manual de arquivos entre e-mails e pastas</td>
                      <td className="p-3 text-green-700">Sistema centralizado com workflow</td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Superprocessamento</td>
                      <td className="p-3 text-muted-foreground">Conferência dupla dos mesmos campos</td>
                      <td className="p-3 text-green-700">IA valida + Revisor confirma casos críticos</td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Defeitos</td>
                      <td className="p-3 text-muted-foreground">Documentos ilegíveis, dados incorretos</td>
                      <td className="p-3 text-green-700">Validação automática com checklist obrigatório</td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Estoque</td>
                      <td className="p-3 text-muted-foreground">Acúmulo de exames aguardando correção</td>
                      <td className="p-3 text-green-700">Notificações imediatas + fila priorizada</td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Talento</td>
                      <td className="p-3 text-muted-foreground">Médicos gastando tempo com checagem manual</td>
                      <td className="p-3 text-green-700">Foco em decisões clínicas complexas</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Riscos */}
          <div className="grid md:grid-cols-2 gap-6">
            <Card className="bg-red-50 border-red-200">
              <CardHeader>
                <CardTitle className="text-red-900 flex items-center gap-2">
                  <AlertCircle className="h-5 w-5" />
                  Pontos de Risco Críticos
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-sm text-red-800 space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">⚠️</span>
                    <span><strong>Não conformidade legal:</strong> ASO sem assinatura válida invalida laudo</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">⚠️</span>
                    <span><strong>Liberação incorreta:</strong> erro pode liberar colaborador inapto</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">⚠️</span>
                    <span><strong>Segurança da informação:</strong> documentos sensíveis sem controle</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">⚠️</span>
                    <span><strong>Retrabalho em massa:</strong> ausência de rastreabilidade</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            <Card className="bg-green-50 border-green-200">
              <CardHeader>
                <CardTitle className="text-green-900 flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  Mitigações Implementadas
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-sm text-green-800 space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">✅</span>
                    <span><strong>Validação automática:</strong> checklist obrigatório de campos críticos</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">✅</span>
                    <span><strong>Dupla validação:</strong> IA sugere + Revisor decide</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">✅</span>
                    <span><strong>Controle de acesso:</strong> perfis específicos + logs de auditoria</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="shrink-0">✅</span>
                    <span><strong>Deduplicação:</strong> hash único por documento previne duplicatas</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-12" />

        {/* Sistema de Notificações */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Sistema de Notificações</h2>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Bell className="h-6 w-6 text-blue-600" />
                <CardTitle>Notificações em Tempo Real</CardTitle>
              </div>
              <CardDescription>
                Sistema mantém todos os usuários informados sobre o andamento dos documentos
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {/* Enviador recebe */}
                <div>
                  <h4 className="font-semibold mb-3 flex items-center gap-2">
                    <Badge className="bg-blue-500">Enviador</Badge>
                    <span>recebe:</span>
                  </h4>
                  <div className="grid gap-2">
                    <div className="flex items-start gap-2 text-sm p-2 rounded bg-slate-50">
                      <Badge variant="outline" className="shrink-0">Início</Badge>
                      <span>&ldquo;Iniciando processamento de 3 documento(s)&rdquo;</span>
                    </div>
                    <div className="flex items-start gap-2 text-sm p-2 rounded bg-green-50">
                      <Badge variant="outline" className="shrink-0">Concluído (limpo)</Badge>
                      <span>&ldquo;Processamento concluído - 3 documentos enviados para revisão&rdquo;</span>
                    </div>
                    <div className="flex items-start gap-2 text-sm p-2 rounded bg-amber-50">
                      <Badge variant="outline" className="shrink-0">Concluído (pendências)</Badge>
                      <span>&ldquo;Processamento concluído - 2 aprovados, 1 com pendências pela IA (todos enviados para revisão)&rdquo;</span>
                    </div>
                    <div className="flex items-start gap-2 text-sm p-2 rounded bg-red-50">
                      <Badge variant="outline" className="shrink-0">Erro</Badge>
                      <span>&ldquo;Erro ao processar documento: timeout OCR&rdquo;</span>
                    </div>
                    <div className="flex items-start gap-2 text-sm p-2 rounded bg-blue-50">
                      <Badge variant="outline" className="shrink-0">Duplicata</Badge>
                      <span>&ldquo;Documento já foi enviado anteriormente em 15/12/2024&rdquo;</span>
                    </div>
                    <div className="flex items-start gap-2 text-sm p-2 rounded bg-red-50">
                      <Badge variant="outline" className="shrink-0">Rejeição Revisor</Badge>
                      <span>&ldquo;Seu documento de João Silva foi rejeitado: Documento ilegível&rdquo;</span>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2 italic">
                    ⚠️ Enviadores NÃO recebem notificação quando o Revisor aprova (fluxo transparente)
                  </p>
                </div>

                {/* Revisor recebe */}
                <div>
                  <h4 className="font-semibold mb-3 flex items-center gap-2">
                    <Badge className="bg-green-500">Revisor</Badge>
                    <span>recebe:</span>
                  </h4>
                  <div className="grid gap-2">
                    <div className="flex items-start gap-2 text-sm p-2 rounded bg-slate-50">
                      <Badge variant="outline" className="shrink-0">Novo</Badge>
                      <span>&ldquo;3 novos documentos aguardando revisão&rdquo;</span>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        <Separator className="my-12" />

        {/* Páginas do Sistema */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Páginas do Sistema</h2>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-3 font-semibold">Página</th>
                  <th className="text-left p-3 font-semibold">Rota</th>
                  <th className="text-left p-3 font-semibold">Acesso</th>
                  <th className="text-left p-3 font-semibold">Descrição</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b hover:bg-slate-50">
                  <td className="p-3 font-medium">Login</td>
                  <td className="p-3"><code className="text-sm bg-slate-100 px-2 py-1 rounded">/login</code></td>
                  <td className="p-3"><Badge variant="outline">Público</Badge></td>
                  <td className="p-3 text-sm text-muted-foreground">Autenticação via Google OAuth</td>
                </tr>
                <tr className="border-b hover:bg-slate-50">
                  <td className="p-3 font-medium">Enviar Exames</td>
                  <td className="p-3"><code className="text-sm bg-slate-100 px-2 py-1 rounded">/enviar-docs</code></td>
                  <td className="p-3">
                    <div className="flex gap-1 flex-wrap">
                      <Badge className="bg-blue-500 text-xs">Enviador</Badge>
                      <Badge className="bg-purple-500 text-xs">Admin</Badge>
                    </div>
                  </td>
                  <td className="p-3 text-sm text-muted-foreground">Upload e processamento de documentos</td>
                </tr>
                <tr className="border-b hover:bg-slate-50">
                  <td className="p-3 font-medium">Pendentes</td>
                  <td className="p-3"><code className="text-sm bg-slate-100 px-2 py-1 rounded">/pendentes</code></td>
                  <td className="p-3">
                    <div className="flex gap-1 flex-wrap">
                      <Badge className="bg-blue-500 text-xs">Enviador</Badge>
                      <Badge className="bg-purple-500 text-xs">Admin</Badge>
                    </div>
                  </td>
                  <td className="p-3 text-sm text-muted-foreground">Documentos rejeitados que precisam de ação</td>
                </tr>
                <tr className="border-b hover:bg-slate-50">
                  <td className="p-3 font-medium">Checagem</td>
                  <td className="p-3"><code className="text-sm bg-slate-100 px-2 py-1 rounded">/checagem</code></td>
                  <td className="p-3">
                    <div className="flex gap-1 flex-wrap">
                      <Badge className="bg-green-500 text-xs">Revisor</Badge>
                      <Badge className="bg-purple-500 text-xs">Admin</Badge>
                    </div>
                  </td>
                  <td className="p-3 text-sm text-muted-foreground">Validação manual com aprovação/rejeição</td>
                </tr>
                <tr className="border-b hover:bg-slate-50">
                  <td className="p-3 font-medium">Histórico</td>
                  <td className="p-3"><code className="text-sm bg-slate-100 px-2 py-1 rounded">/historico</code></td>
                  <td className="p-3">
                    <Badge className="bg-purple-500 text-xs">Admin</Badge>
                  </td>
                  <td className="p-3 text-sm text-muted-foreground">Arquivo completo de processamentos</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <Separator className="my-12" />

        {/* KPIs e Indicadores */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">KPIs e Indicadores de Sucesso</h2>
          <p className="text-muted-foreground mb-8">
            Métricas para acompanhamento de performance e qualidade do processo automatizado.
          </p>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-blue-600" />
                Indicadores Principais
              </CardTitle>
              <CardDescription>
                Fórmulas de cálculo e metas de melhoria para cada indicador
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-semibold">Indicador</th>
                      <th className="text-left p-3 font-semibold">Fórmula / Fonte</th>
                      <th className="text-left p-3 font-semibold">Meta</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Tempo médio de liberação (Lead Time)</td>
                      <td className="p-3 text-muted-foreground"><code className="text-xs bg-slate-100 px-2 py-1 rounded">Data liberação - Data recebimento</code></td>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <TrendingDown className="h-4 w-4 text-green-600" />
                          <span className="text-green-700 font-semibold">↓ Reduzir 50%</span>
                        </div>
                      </td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Taxa de devoluções às clínicas</td>
                      <td className="p-3 text-muted-foreground"><code className="text-xs bg-slate-100 px-2 py-1 rounded">(Devolvidos / Recebidos) × 100</code></td>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <TrendingDown className="h-4 w-4 text-green-600" />
                          <span className="text-green-700 font-semibold">↓ Reduzir 70%</span>
                        </div>
                      </td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Taxa de ASOs aprovados sem pendência</td>
                      <td className="p-3 text-muted-foreground"><code className="text-xs bg-slate-100 px-2 py-1 rounded">(Aprovados direto / Total) × 100</code></td>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <TrendingUp className="h-4 w-4 text-blue-600" />
                          <span className="text-blue-700 font-semibold">↑ Aumentar 40%</span>
                        </div>
                      </td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Tempo médio de resposta da clínica</td>
                      <td className="p-3 text-muted-foreground"><code className="text-xs bg-slate-100 px-2 py-1 rounded">Data reenvio - Data devolução</code></td>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <TrendingDown className="h-4 w-4 text-green-600" />
                          <span className="text-green-700 font-semibold">↓ Reduzir 60%</span>
                        </div>
                      </td>
                    </tr>
                    <tr className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">Percentual de automação de checagem</td>
                      <td className="p-3 text-muted-foreground"><code className="text-xs bg-slate-100 px-2 py-1 rounded">(Processados via OCR / Total) × 100</code></td>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <TrendingUp className="h-4 w-4 text-blue-600" />
                          <span className="text-blue-700 font-semibold">↑ 80% até Fase 2</span>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </section>

        <Separator className="my-12" />

        {/* Governança e LGPD */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Segurança, LGPD e Governança</h2>
          <p className="text-muted-foreground mb-8">
            Práticas de segurança da informação e conformidade com a Lei Geral de Proteção de Dados.
          </p>

          <div className="grid md:grid-cols-2 gap-6 mb-6">
            {/* LGPD */}
            <Card className="border-l-4 border-l-blue-500">
              <CardHeader className="bg-blue-50">
                <CardTitle className="text-blue-900 flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  Conformidade LGPD
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <ul className="text-sm space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="text-blue-600 shrink-0">✓</span>
                    <span><strong>Anonimização parcial:</strong> dados médicos com uso estritamente funcional</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-blue-600 shrink-0">✓</span>
                    <span><strong>Minimização de dados:</strong> coleta apenas informações necessárias</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-blue-600 shrink-0">✓</span>
                    <span><strong>Consentimento:</strong> documentação clara de autorização para processamento</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-blue-600 shrink-0">✓</span>
                    <span><strong>Retenção legal:</strong> backup automático com retenção mínima de 5 anos</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Controle de Acesso */}
            <Card className="border-l-4 border-l-green-500">
              <CardHeader className="bg-green-50">
                <CardTitle className="text-green-900 flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Controle de Acesso
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <ul className="text-sm space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="text-green-600 shrink-0">✓</span>
                    <span><strong>Perfis diferenciados:</strong> Enviador, Revisor, Admin com permissões específicas</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-green-600 shrink-0">✓</span>
                    <span><strong>Autenticação corporativa:</strong> Google OAuth restrito a @grupobrmed.com.br</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-green-600 shrink-0">✓</span>
                    <span><strong>Acesso granular:</strong> permissões específicas por documento e ação</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-green-600 shrink-0">✓</span>
                    <span><strong>Gestão de identidade:</strong> IAM + autenticação MFA (planejado)</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {/* Segurança Técnica */}
            <Card className="border-l-4 border-l-purple-500">
              <CardHeader className="bg-purple-50">
                <CardTitle className="text-purple-900 flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  Segurança Técnica
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <ul className="text-sm space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="text-purple-600 shrink-0">✓</span>
                    <span><strong>Criptografia em trânsito:</strong> HTTPS/TLS para todas as comunicações</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-purple-600 shrink-0">✓</span>
                    <span><strong>Criptografia em repouso:</strong> AES-256 para dados armazenados</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-purple-600 shrink-0">✓</span>
                    <span><strong>Ambientes segregados:</strong> desenvolvimento, homologação e produção separados</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-purple-600 shrink-0">✓</span>
                    <span><strong>Storage seguro:</strong> cloud com controle de acesso e versionamento</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Auditoria */}
            <Card className="border-l-4 border-l-amber-500">
              <CardHeader className="bg-amber-50">
                <CardTitle className="text-amber-900 flex items-center gap-2">
                  <FileCheck className="h-5 w-5" />
                  Logs e Auditoria
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <ul className="text-sm space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="text-amber-600 shrink-0">✓</span>
                    <span><strong>Trilha de auditoria:</strong> registro de quem aprovou, quando e qual ação</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-amber-600 shrink-0">✓</span>
                    <span><strong>Logs automáticos:</strong> todas as operações registradas com timestamp</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-amber-600 shrink-0">✓</span>
                    <span><strong>Versionamento:</strong> histórico completo de alterações em documentos</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-amber-600 shrink-0">✓</span>
                    <span><strong>Backup diário:</strong> retenção mínima de 5 anos conforme exigência legal</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-12" />

        {/* Tecnologias */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold mb-8">Tecnologias Utilizadas</h2>

          <div className="grid md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Front-end</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">Framework</Badge>
                    <span>Next.js 15 (App Router)</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">UI</Badge>
                    <span>React 19 + TypeScript</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">Styling</Badge>
                    <span>Tailwind CSS 4 + shadcn/ui</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">Auth</Badge>
                    <span>NextAuth (Google OAuth)</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Back-end</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">Framework</Badge>
                    <span>FastAPI (Python 3.11+)</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">OCR</Badge>
                    <span>Docling / AWS Textract (futuro)</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">AI/ML</Badge>
                    <span>OpenAI API + FAISS (vector search)</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">Scraping</Badge>
                    <span>Playwright / API (futuro)</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Resumo Executivo */}
        <section className="mb-16">
          <Card className="bg-gradient-to-br from-blue-50 to-purple-50 border-2 border-blue-200">
            <CardHeader>
              <CardTitle className="text-2xl flex items-center gap-2">
                <Target className="h-6 w-6 text-blue-600" />
                Resumo Executivo
              </CardTitle>
              <CardDescription className="text-base">
                Visão consolidada do projeto ProntuAI
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                <div>
                  <h4 className="font-semibold text-lg mb-3 text-blue-900">Situação Atual</h4>
                  <p className="text-sm text-muted-foreground">
                    O processo atual é manual, moroso e vulnerável a falhas documentais, exigindo dupla conferência
                    e intensa comunicação reativa com as clínicas terceirizadas. Alto índice de devoluções e
                    retrabalho impactam diretamente o tempo de liberação de ASOs.
                  </p>
                </div>

                <div>
                  <h4 className="font-semibold text-lg mb-3 text-blue-900">5 Focos Estratégicos de Otimização</h4>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-white rounded-lg p-4 border">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="h-8 w-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-sm">1</div>
                        <h5 className="font-semibold">Automação Operacional</h5>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Implantar OCR/RPA para checagem documental e integração via API, eliminando tarefas manuais repetitivas
                      </p>
                    </div>

                    <div className="bg-white rounded-lg p-4 border">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="h-8 w-8 rounded-full bg-green-100 text-green-700 flex items-center justify-center font-bold text-sm">2</div>
                        <h5 className="font-semibold">Governança e Conformidade</h5>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Criar logs, versionamento e controle de acesso para rastreabilidade e segurança jurídica
                      </p>
                    </div>

                    <div className="bg-white rounded-lg p-4 border">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="h-8 w-8 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-sm">3</div>
                        <h5 className="font-semibold">Padronização e Comunicação</h5>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Checklist obrigatórios, templates padronizados e portal para clínicas reduzem ruídos de comunicação
                      </p>
                    </div>

                    <div className="bg-white rounded-lg p-4 border">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="h-8 w-8 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center font-bold text-sm">4</div>
                        <h5 className="font-semibold">Gestão de Performance</h5>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Monitoramento automatizado via dashboards com KPIs de prazo, produtividade e qualidade
                      </p>
                    </div>

                    <div className="bg-white rounded-lg p-4 border md:col-span-2">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="h-8 w-8 rounded-full bg-red-100 text-red-700 flex items-center justify-center font-bold text-sm">5</div>
                        <h5 className="font-semibold">Eliminação de Desperdícios (Lean)</h5>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Redução de espera, movimentação, superprocessamento, defeitos, estoque e subutilização de talento médico
                      </p>
                    </div>
                  </div>
                </div>

                <div>
                  <h4 className="font-semibold text-lg mb-3 text-blue-900">Benefícios Esperados</h4>
                  <div className="grid md:grid-cols-3 gap-3">
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                      <p className="text-2xl font-bold text-green-700 mb-1">↓ 50%</p>
                      <p className="text-xs text-green-800">Redução no tempo de liberação</p>
                    </div>
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                      <p className="text-2xl font-bold text-green-700 mb-1">↓ 70%</p>
                      <p className="text-xs text-green-800">Redução em devoluções</p>
                    </div>
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                      <p className="text-2xl font-bold text-blue-700 mb-1">↑ 80%</p>
                      <p className="text-xs text-blue-800">Automação de checagem</p>
                    </div>
                  </div>
                </div>

                <div className="bg-blue-100 border border-blue-300 rounded-lg p-4">
                  <p className="text-sm text-blue-900">
                    <strong>Conclusão:</strong> ProntuAI transforma um processo manual vulnerável em um sistema automatizado,
                    rastreável e eficiente, garantindo conformidade legal, segurança ocupacional e agilidade na liberação de ASOs
                    para os clientes da BR MED.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Footer */}
        <footer className="text-center text-sm text-muted-foreground pt-12 border-t">
          <p>ProntuAI - Sistema de Validação de Documentos Médicos</p>
          <p className="mt-1">BR MED | Última atualização: Janeiro 2025 • Versão 1.0</p>
        </footer>
      </div>
    </div>
  )
}
