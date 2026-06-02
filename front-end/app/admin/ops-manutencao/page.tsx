"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { CalendarClock, RefreshCw, ShieldAlert, Wrench } from "lucide-react"
import { toast } from "sonner"

import { RequireRole } from "@/components/require-role"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { API_ENDPOINTS } from "@/lib/config"
import { authFetch } from "@/lib/auth-fetch"
import type { MaintenanceStatusResponse, MaintenanceWindow } from "@/types/maintenance"

type FormState = {
  title: string
  message: string
  startsAt: string
  endsAt: string
  eta: string
}

const initialFormState = (): FormState => {
  const now = new Date()
  now.setMinutes(now.getMinutes() + 10)
  const later = new Date(now)
  later.setHours(later.getHours() + 1)
  return {
    title: "Manutenção programada",
    message: "O ProntuAI passará por uma manutenção programada para melhorias na plataforma.",
    startsAt: toDatetimeLocal(now),
    endsAt: toDatetimeLocal(later),
    eta: "Previsão de retorno em até 1 hora.",
  }
}

function toDatetimeLocal(date: Date) {
  const offset = date.getTimezoneOffset()
  const localDate = new Date(date.getTime() - offset * 60_000)
  return localDate.toISOString().slice(0, 16)
}

function toIsoFromLocal(value: string) {
  return value ? new Date(value).toISOString() : null
}

function statusLabel(status: MaintenanceWindow["status"]) {
  const labels = {
    scheduled: "Agendada",
    active: "Ativa",
    cancelled: "Cancelada",
    completed: "Finalizada",
  }
  return labels[status]
}

function formatDate(value?: string | null) {
  if (!value) return "-"
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value))
}

function OpsManutencaoContent() {
  const [form, setForm] = useState<FormState>(() => initialFormState())
  const [windows, setWindows] = useState<MaintenanceWindow[]>([])
  const [publicStatus, setPublicStatus] = useState<MaintenanceStatusResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const activeWindow = useMemo(
    () => windows.find((item) => item.status === "active" || item.status === "scheduled"),
    [windows],
  )

  const load = useCallback(async () => {
    try {
      const [statusResponse, windowsResponse] = await Promise.all([
        fetch(API_ENDPOINTS.MAINTENANCE_STATUS, { cache: "no-store" }),
        authFetch(API_ENDPOINTS.MAINTENANCE_WINDOWS, { cache: "no-store" }),
      ])
      if (statusResponse.ok) {
        setPublicStatus((await statusResponse.json()) as MaintenanceStatusResponse)
      }
      if (windowsResponse.ok) {
        setWindows((await windowsResponse.json()) as MaintenanceWindow[])
      }
    } catch {
      toast.error("Não foi possível carregar o estado de manutenção.")
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const createWindow = async () => {
    setLoading(true)
    try {
      const response = await authFetch(API_ENDPOINTS.MAINTENANCE_WINDOWS, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.title,
          message: form.message,
          starts_at: toIsoFromLocal(form.startsAt),
          ends_at: toIsoFromLocal(form.endsAt),
          eta: form.eta || null,
        }),
      })
      if (!response.ok) {
        const detail = await response.text().catch(() => "Erro ao agendar manutenção.")
        throw new Error(detail)
      }
      toast.success("Manutenção agendada.")
      setForm(initialFormState())
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Erro ao agendar manutenção.")
    } finally {
      setLoading(false)
    }
  }

  const runAction = async (id: string, action: "activate" | "cancel" | "complete") => {
    const endpoints = {
      activate: API_ENDPOINTS.MAINTENANCE_ACTIVATE,
      cancel: API_ENDPOINTS.MAINTENANCE_CANCEL,
      complete: API_ENDPOINTS.MAINTENANCE_COMPLETE,
    }
    setLoading(true)
    try {
      const response = await authFetch(endpoints[action](id), { method: "POST" })
      if (!response.ok) {
        const detail = await response.text().catch(() => "Erro ao atualizar manutenção.")
        throw new Error(detail)
      }
      const messages = {
        activate: "Manutenção ativada.",
        cancel: "Manutenção cancelada.",
        complete: "Manutenção finalizada.",
      }
      toast.success(messages[action])
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Erro ao atualizar manutenção.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-10 text-slate-50">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-sm text-amber-200">
              <ShieldAlert className="size-4" aria-hidden="true" />
              Rota operacional oculta
            </div>
            <h1 className="text-3xl font-bold tracking-tight">Manutenção do ProntuAI</h1>
            <p className="mt-2 max-w-2xl text-slate-400">
              Use esta tela para agendar aviso prévio, ativar o bloqueio e desfazer/finalizar quando não for mais necessário.
            </p>
          </div>
          <Button type="button" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className="size-4" aria-hidden="true" />
            Atualizar
          </Button>
        </div>

        <Card className="border-slate-800 bg-slate-900 text-slate-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wrench className="size-5 text-amber-300" aria-hidden="true" />
              Estado público atual
            </CardTitle>
            <CardDescription>
              É isso que todos os navegadores recebem em <code>/api/maintenance-status</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <Badge className="bg-amber-200 text-amber-950 hover:bg-amber-200">
              {publicStatus?.status || "none"}
            </Badge>
            <span className="text-sm text-slate-300">{publicStatus?.message || "Sem manutenção ativa ou agendada."}</span>
            {publicStatus?.eta && <span className="text-sm text-amber-200">{publicStatus.eta}</span>}
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
          <Card className="border-slate-800 bg-slate-900 text-slate-50">
            <CardHeader>
              <CardTitle>Agendar manutenção</CardTitle>
              <CardDescription>Cria uma nova janela em estado agendado.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Título</Label>
                <Input id="title" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="message">Mensagem</Label>
                <Textarea id="message" value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} />
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="startsAt">Início</Label>
                  <Input id="startsAt" type="datetime-local" value={form.startsAt} onChange={(event) => setForm({ ...form, startsAt: event.target.value })} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="endsAt">Fim previsto</Label>
                  <Input id="endsAt" type="datetime-local" value={form.endsAt} onChange={(event) => setForm({ ...form, endsAt: event.target.value })} />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="eta">Texto de previsão</Label>
                <Input id="eta" value={form.eta} onChange={(event) => setForm({ ...form, eta: event.target.value })} />
              </div>
            </CardContent>
            <CardFooter>
              <Button type="button" disabled={loading} onClick={createWindow}>
                <CalendarClock className="size-4" aria-hidden="true" />
                Agendar
              </Button>
            </CardFooter>
          </Card>

          <Card className="border-slate-800 bg-slate-900 text-slate-50">
            <CardHeader>
              <CardTitle>Janelas recentes</CardTitle>
              <CardDescription>Ative, cancele ou finalize sem deploy.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {windows.length === 0 ? (
                <p className="text-sm text-slate-400">Nenhuma janela cadastrada.</p>
              ) : (
                windows.map((item) => (
                  <div key={item.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="border-slate-700 text-slate-200">
                            {statusLabel(item.status)}
                          </Badge>
                          <h2 className="truncate font-semibold">{item.title}</h2>
                        </div>
                        <p className="mt-2 text-sm text-slate-400">{item.message}</p>
                        <p className="mt-2 text-xs text-slate-500">
                          {formatDate(item.starts_at)} até {formatDate(item.ends_at)}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        {item.status === "scheduled" && (
                          <Button type="button" size="sm" disabled={loading} onClick={() => runAction(item.id, "activate")}>
                            Ativar agora
                          </Button>
                        )}
                        {(item.status === "scheduled" || item.status === "active") && (
                          <Button type="button" size="sm" variant="outline" disabled={loading} onClick={() => runAction(item.id, "cancel")}>
                            Cancelar
                          </Button>
                        )}
                        {item.status === "active" && (
                          <Button type="button" size="sm" variant="secondary" disabled={loading} onClick={() => runAction(item.id, "complete")}>
                            Finalizar
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        {activeWindow && (
          <p className="text-xs text-slate-500">
            Janela operacional atual: <span className="text-slate-300">{activeWindow.id}</span>
          </p>
        )}
      </div>
    </main>
  )
}

export default function OpsManutencaoPage() {
  return (
    <RequireRole allowedRoles={["ADMIN"]}>
      <OpsManutencaoContent />
    </RequireRole>
  )
}
