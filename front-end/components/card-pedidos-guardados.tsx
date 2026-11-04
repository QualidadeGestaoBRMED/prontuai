"use client"

import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { authFetch } from "@/lib/auth-fetch"
import { API_ENDPOINTS } from "@/lib/config"

type Resumo = {
  ligada: boolean
  chave_atualizada_em: string | null
  chave_atualizada_por: string | null
  total_pedidos: number
  ultimo_pedido_em: string | null
}

// O back-end grava em UTC, sem fuso no valor.
function formatarData(valor: string | null) {
  if (!valor) return "—"
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(valor) ? valor : `${valor}Z`).toLocaleString("pt-BR")
}

/**
 * Liga e desliga os pedidos do BR NET guardados para testes.
 *
 * Só existe em staging: fora dele a rota responde 404 e o card não aparece, sem
 * rastro na tela. Se a leitura falhar por outro motivo, ele também some, porque
 * sem saber o estado da chave não há o que oferecer.
 */
export function CardPedidosGuardados() {
  const [resumo, setResumo] = useState<Resumo | null>(null)
  const [salvando, setSalvando] = useState(false)

  useEffect(() => {
    let ativo = true
    authFetch(API_ENDPOINTS.PEDIDOS_GUARDADOS)
      .then(async (resposta) => {
        if (ativo && resposta.ok) setResumo(await resposta.json())
      })
      .catch(() => {
        // Sem o card: ver o comentário acima.
      })
    return () => {
      ativo = false
    }
  }, [])

  if (!resumo) return null

  const trocar = async () => {
    setSalvando(true)
    try {
      const resposta = await authFetch(API_ENDPOINTS.PEDIDOS_GUARDADOS, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ligada: !resumo.ligada }),
      })
      if (!resposta.ok) throw new Error(String(resposta.status))
      const novo: Resumo = await resposta.json()
      setResumo(novo)
      toast.success(novo.ligada ? "Pedidos guardados ligados." : "Pedidos guardados desligados.")
    } catch {
      toast.error("Não foi possível trocar a chave. Nada mudou.")
    } finally {
      setSalvando(false)
    }
  }

  return (
    <Card className="border-slate-800 bg-slate-900 text-slate-50">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Testes em staging: pedidos guardados
          <Badge variant={resumo.ligada ? "default" : "secondary"}>{resumo.ligada ? "Ligada" : "Desligada"}</Badge>
        </CardTitle>
        <CardDescription>
          Ligada, guarda cada pedido do BR NET consultado e usa o guardado quando a API responde que não há expedição em
          aberto. Só vale para pacientes consultados depois de ligar.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <dl className="grid gap-x-8 gap-y-1 text-sm text-slate-300 sm:grid-cols-2">
          <div>
            <dt className="inline text-slate-400">Pedidos guardados: </dt>
            <dd className="inline tabular-nums">{resumo.total_pedidos}</dd>
          </div>
          <div>
            <dt className="inline text-slate-400">Último pedido: </dt>
            <dd className="inline">{formatarData(resumo.ultimo_pedido_em)}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="inline text-slate-400">Chave alterada: </dt>
            <dd className="inline">
              {formatarData(resumo.chave_atualizada_em)}
              {resumo.chave_atualizada_por ? ` por ${resumo.chave_atualizada_por}` : ""}
            </dd>
          </div>
        </dl>
        <Button
          onClick={trocar}
          disabled={salvando}
          variant={resumo.ligada ? "destructive" : "default"}
          className="shrink-0"
        >
          {salvando && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
          {resumo.ligada ? "Desligar" : "Ligar"}
        </Button>
      </CardContent>
    </Card>
  )
}
