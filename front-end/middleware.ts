import { NextResponse } from "next/server";
import type { NextFetchEvent, NextRequest } from "next/server";
import { withAuth } from "next-auth/middleware";

const bypassAuth =
  process.env.NODE_ENV !== "production" &&
  process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";

const authMiddleware = withAuth({
  pages: {
    signIn: "/login",
  },
});

export default function middleware(req: NextRequest, event: NextFetchEvent) {
  if (bypassAuth) {
    return NextResponse.next();
  }
  return (authMiddleware as unknown as (request: NextRequest, event: NextFetchEvent) => ReturnType<typeof authMiddleware>)(req, event);
}

export const config = {
  matcher: ["/anexar-prontuario", "/checagem", "/insights", "/historico", "/pendentes", "/admin/:path*"],
};
