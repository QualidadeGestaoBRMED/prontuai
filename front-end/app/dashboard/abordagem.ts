"use client";

/**
 * Status de abordagem das credenciadas de "Quem vale a pena incluir".
 *
 * Mora fora de `useDadosDashboard` de propósito: os indicadores saem de um cache
 * recalculado uma vez por dia, e o status tem de valer na hora para o time
 * inteiro — quem marca vê gravado, e quem abre o painel depois vê o que foi
 * marcado. A chave é o rótulo do BRNET (`LinhaForaProntuai.credenciado`), o mesmo
 * que o back-end usa: a API de monitoramento não manda id nem CNPJ.
 */
import { useCallback, useEffect, useState } from "react";

import { authFetch } from "@/lib/auth-fetch";
import { API_ENDPOINTS } from "@/lib/config";

export type StatusAbordagem = "NAO_ABORDADA" | "EM_CONTATO" | "AGUARDANDO_RETORNO" | "ACEITOU" | "RECUSOU";

export interface Abordagem {
  credenciado: string;
  status: StatusAbordagem;
  motivo: string | null;
  atualizado_por_email: string | null;
  atualizado_por_nome: string | null;
  /** ISO em UTC; o back-end grava sem fuso. */
  atualizado_em: string;
}

/** Na ordem da conversa, que é também a ordem da coluna quando se ordena por ela. */
export const STATUS_ABORDAGEM: { valor: StatusAbordagem; rotulo: string; cor: string; fundo: string }[] = [
  { valor: "NAO_ABORDADA", rotulo: "Não abordada", cor: "#767A7B", fundo: "#F3F3F3" },
  { valor: "EM_CONTATO", rotulo: "Em contato", cor: "#007891", fundo: "#E6F4F4" },
  { valor: "AGUARDANDO_RETORNO", rotulo: "Aguardando retorno", cor: "#8A5A0B", fundo: "#FBF5EA" },
  { valor: "ACEITOU", rotulo: "Aceitou / em cadastro", cor: "#2E7D4F", fundo: "#E7F4EC" },
  { valor: "RECUSOU", rotulo: "Recusou", cor: "#B4453A", fundo: "#FBECEA" },
];

export const infoStatus = (s: StatusAbordagem) =>
  STATUS_ABORDAGEM.find((x) => x.valor === s) ?? STATUS_ABORDAGEM[0];

export const ordemStatus = (s: StatusAbordagem) => STATUS_ABORDAGEM.findIndex((x) => x.valor === s);

/** "por Ana Souza · 22/10/2026 15:04", no fuso de quem lê. */
export function autorEData(a: Abordagem | undefined | null): string {
  if (!a) return "";
  const iso = /Z$|[+-]\d\d:\d\d$/.test(a.atualizado_em) ? a.atualizado_em : `${a.atualizado_em}Z`;
  const quando = new Date(iso);
  const data = Number.isNaN(quando.getTime())
    ? ""
    : quando.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const quem = a.atualizado_por_nome || (a.atualizado_por_email ?? "").split("@")[0];
  return [quem && `por ${quem}`, data].filter(Boolean).join(" · ");
}

/** A mensagem que o back-end devolveu, sem o prefixo técnico do Pydantic. */
async function mensagemDeErro(resposta: Response): Promise<string> {
  const corpo = await resposta.json().catch(() => null);
  const detalhe = corpo?.detail;
  if (typeof detalhe === "string") return detalhe;
  if (Array.isArray(detalhe) && detalhe[0]?.msg) return String(detalhe[0].msg).replace(/^Value error, /, "");
  return `Não foi possível salvar (HTTP ${resposta.status}).`;
}

export function useAbordagens() {
  const [porCredenciado, setPorCredenciado] = useState<Map<string, Abordagem>>(new Map());
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    authFetch(API_ENDPOINTS.DASHBOARD_ABORDAGENS)
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error(await mensagemDeErro(resposta));
        return (await resposta.json()) as Abordagem[];
      })
      .then((lista) => {
        if (!cancelado) setPorCredenciado(new Map(lista.map((a) => [a.credenciado, a])));
      })
      .catch((e: unknown) => {
        if (!cancelado) setErro(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelado = true;
    };
  }, []);

  /** Grava e só então troca na tela: o que aparece é sempre o que ficou no banco. */
  const salvar = useCallback(async (credenciado: string, status: StatusAbordagem, motivo?: string | null) => {
    const resposta = await authFetch(API_ENDPOINTS.DASHBOARD_ABORDAGENS, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credenciado, status, motivo: motivo ?? null }),
    });
    if (!resposta.ok) throw new Error(await mensagemDeErro(resposta));
    const salvo = (await resposta.json()) as Abordagem;
    setPorCredenciado((atual) => new Map(atual).set(salvo.credenciado, salvo));
    return salvo;
  }, []);

  return { porCredenciado, erro, salvar };
}
