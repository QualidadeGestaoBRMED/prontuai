/**
 * Fonte única do cookie de sessão do NextAuth.
 *
 * Quem escreve o cookie (o handler do NextAuth) e quem o lê (`getToken` no
 * proxy, no middleware e na rota de refresh) derivavam o prefixo `__Secure-`
 * de formas diferentes: o handler olha a URL base inferida do request, o
 * `getToken` olha `NEXTAUTH_URL` e a variável `VERCEL`. Sem `NEXTAUTH_URL`
 * definida — o caso do deploy por docker-compose na VPS, com o HTTPS
 * terminando no nginx — os dois discordavam e nenhuma requisição autenticada
 * passava, porque o leitor procurava um cookie com outro nome.
 *
 * Agora o valor é calculado uma vez aqui: `authOptions.useSecureCookies` manda
 * o NextAuth escrever com este prefixo, e todo leitor passa `cookieName` e
 * `secureCookie` vindos deste módulo. Trocar a regra é mudar uma linha só.
 */
export const useSecureCookies =
  process.env.NEXTAUTH_URL?.startsWith("https://") ??
  (!!process.env.VERCEL || process.env.NODE_ENV === "production")

export const SESSION_COOKIE_NAME = useSecureCookies
  ? "__Secure-next-auth.session-token"
  : "next-auth.session-token"

/** Duração do cookie de sessão. Ver o comentário de `maxAge` em authOptions. */
export const SESSION_MAX_AGE = Number(
  process.env.NEXTAUTH_SESSION_MAX_AGE || 60 * 60 * 8
)

/** Opções de `getToken` para que todo leitor use o mesmo cookie. */
export const sessionTokenParams = {
  cookieName: SESSION_COOKIE_NAME,
  secureCookie: useSecureCookies,
  secret: process.env.NEXTAUTH_SECRET,
}
