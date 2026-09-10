"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { authFetch } from "@/lib/auth-fetch";
import { API_ENDPOINTS } from "@/lib/config";

import type { DadosDashboard } from "./tipos";

/**
 * Resposta de `GET /v1/dashboard/indicadores`. As séries saem do banco do
 * ambiente em que o back-end está rodando (dev, staging ou produção) e
 * `expedicoes_dia` sai de um arquivo no disco do servidor — nada aqui vem de
 * dado commitado.
 */
type RespostaIndicadores = DadosDashboard & {
  /** APP_ENV do back-end. */
  ambiente?: string;
  /** Quando a consulta rodou, ISO com fuso. */
  gerado_em?: string;
  /** Quando a rotina diária roda de novo, ISO com fuso. */
  proxima_atualizacao?: string;
};

export interface EstadoDashboard {
  dados: DadosDashboard | null;
  ambiente: string | null;
  /** Quando os números foram calculados no banco. */
  geradoEm: Date | null;
  /** Quando a rotina diária roda de novo. */
  proximaAtualizacao: Date | null;
  /** Primeira carga: ainda não há nada para mostrar. */
  carregando: boolean;
  /** Recálculo com dado antigo na tela — o botão "Atualizar". */
  atualizando: boolean;
  erro: string | null;
  /**
   * `forcar` manda o back-end ignorar o cache do dia e varrer o banco de novo.
   * É o que o botão da tela usa; sem ele, a resposta vem do cálculo das 7h.
   */
  recarregar: (forcar?: boolean) => void;
}

function comoData(iso?: string): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function useDadosDashboard(): EstadoDashboard {
  const [dados, setDados] = useState<DadosDashboard | null>(null);
  const [ambiente, setAmbiente] = useState<string | null>(null);
  const [geradoEm, setGeradoEm] = useState<Date | null>(null);
  const [proximaAtualizacao, setProximaAtualizacao] = useState<Date | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pedido, setPedido] = useState({ n: 0, forcar: false });

  // Evita disparar dois recálculos pesados por duplo clique no botão.
  const emVoo = useRef(false);

  const recarregar = useCallback((forcar = false) => {
    if (emVoo.current) return;
    setPedido((p) => ({ n: p.n + 1, forcar }));
  }, []);

  useEffect(() => {
    let cancelado = false;
    emVoo.current = true;
    setErro(null);
    if (pedido.forcar) setAtualizando(true);

    const url = pedido.forcar
      ? `${API_ENDPOINTS.DASHBOARD_INDICADORES}?forcar=true`
      : API_ENDPOINTS.DASHBOARD_INDICADORES;

    authFetch(url)
      .then(async (resposta) => {
        if (!resposta.ok) {
          const corpo = await resposta.text().catch(() => "");
          throw new Error(corpo || `HTTP ${resposta.status}`);
        }
        return (await resposta.json()) as RespostaIndicadores;
      })
      .then((corpo) => {
        if (cancelado) return;
        // `expedicoes_dia` pode vir vazio (servidor sem a extração do BRNET);
        // nesse caso o KPI de cobertura cai no total absoluto, que é o
        // comportamento correto — ver `metricas.ts`.
        setDados({ ...corpo, expedicoes_dia: corpo.expedicoes_dia ?? {} });
        setAmbiente(corpo.ambiente ?? null);
        setGeradoEm(comoData(corpo.gerado_em));
        setProximaAtualizacao(comoData(corpo.proxima_atualizacao));
      })
      .catch((e: unknown) => {
        if (cancelado) return;
        setErro(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        emVoo.current = false;
        if (cancelado) return;
        setCarregando(false);
        setAtualizando(false);
      });

    return () => {
      cancelado = true;
    };
  }, [pedido]);

  return {
    dados,
    ambiente,
    geradoEm,
    proximaAtualizacao,
    carregando,
    atualizando,
    erro,
    recarregar,
  };
}
