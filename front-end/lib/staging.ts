/**
 * Ferramentas só de staging no front (STC-981).
 *
 * A página `/admin/staging` e o repasse de `/v1/testes-staging` pelo proxy só
 * existem com `FERRAMENTAS_DE_STAGING=true` nas variáveis do ambiente de staging da
 * Vercel. Em produção a variável não existe: o middleware responde 404 para a
 * página antes do login, a página também responde 404, e o proxy nem chama o
 * back-end — que, por sua vez, só liga as ferramentas com as duas chaves de
 * `back-end/app/staging/__init__.py`.
 *
 * A variável é só de servidor (sem `NEXT_PUBLIC_`): não vai para o JavaScript do
 * navegador. Por isso esta função só serve em middleware, rota de API e
 * componente de servidor.
 */
export const VARIAVEL_FERRAMENTAS_DE_STAGING = "FERRAMENTAS_DE_STAGING"

export const PAGINA_FERRAMENTAS_DE_STAGING = "/admin/staging"

// Caminho do back-end, como chega ao proxy (sem `/api/proxy`).
export const API_FERRAMENTAS_DE_STAGING = "v1/testes-staging"

export function ferramentasDeStagingAtivas(): boolean {
  return (process.env.FERRAMENTAS_DE_STAGING ?? "").trim().toLowerCase() === "true"
}

/** A rota pertence às ferramentas de staging? Compara por segmento, não por prefixo solto. */
export function ehRotaDeStaging(caminho: string, base: string): boolean {
  const limpo = caminho.replace(/^\/+/, "").replace(/\/+$/, "")
  const alvo = base.replace(/^\/+/, "").replace(/\/+$/, "")
  return limpo === alvo || limpo.startsWith(`${alvo}/`)
}
