import { NextResponse } from "next/server";
import type { NextFetchEvent, NextRequest } from "next/server";
import { withAuth } from "next-auth/middleware";
import { SESSION_COOKIE_NAME } from "@/lib/session-cookie";
import {
  PAGINA_FERRAMENTAS_DE_STAGING,
  ehRotaDeStaging,
  ferramentasDeStagingAtivas,
} from "@/lib/staging";

const bypassAuth =
  process.env.NODE_ENV !== "production" &&
  process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";

const authMiddleware = withAuth({
  pages: {
    signIn: "/login",
  },
  // O nome do cookie tem de ser o mesmo que o handler do NextAuth escreve;
  // ver `lib/session-cookie.ts`. O `withAuth` só repassa `name` ao getToken.
  cookies: {
    sessionToken: { name: SESSION_COOKIE_NAME },
  },
});

export default function middleware(req: NextRequest, event: NextFetchEvent) {
  // Ferramentas só de staging (`lib/staging.ts`): fora de staging a página não
  // existe, nem para quem está logado. Vem antes do login e do bypass de dev.
  if (
    ehRotaDeStaging(req.nextUrl.pathname, PAGINA_FERRAMENTAS_DE_STAGING) &&
    !ferramentasDeStagingAtivas()
  ) {
    return new NextResponse("Not Found", { status: 404 });
  }
  if (bypassAuth) {
    return NextResponse.next();
  }
  return (authMiddleware as unknown as (request: NextRequest, event: NextFetchEvent) => ReturnType<typeof authMiddleware>)(req, event);
}

export const config = {
  matcher: ["/anexar-prontuario", "/chat", "/checagem", "/filial", "/dashboard", "/insights", "/historico", "/pendentes", "/admin/:path*"],
};
