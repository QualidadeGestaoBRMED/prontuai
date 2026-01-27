import { NextResponse } from "next/server";
import { withAuth } from "next-auth/middleware";

const bypassAuth = process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";

const authMiddleware = withAuth({
  pages: {
    signIn: "/login",
  },
});

export default function middleware(req: Request) {
  if (bypassAuth) {
    return NextResponse.next();
  }
  return authMiddleware(req);
}

export const config = {
  matcher: ["/anexar-prontuario", "/checagem", "/insights", "/historico", "/pendentes"],
};
