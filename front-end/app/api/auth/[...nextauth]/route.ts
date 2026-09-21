import NextAuth, { AuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import { API_ENDPOINTS } from "@/lib/config";
import { SESSION_MAX_AGE, useSecureCookies } from "@/lib/session-cookie";

interface BackendAuthData {
  access_token: string;
  refresh_token: string;
  user: {
    id: string;
    email: string;
    name: string;
    role: "ADMIN" | "MANAGER" | "CURATOR" | "CHECKER" | "SENDER";
    is_active: boolean;
  };
}

interface ExtendedProfile {
  email?: string;
  name?: string;
  backendData?: BackendAuthData;
}

// Indisponibilidade do back-end não é falta de permissão: antes, os dois
// caminhos retornavam `false` e o usuário lia "você não tem permissão para
// acessar esta aplicação" quando o back-end estava fora do ar.
const BACKEND_UNAVAILABLE_URL = "/auth/error?error=BackendUnavailable";

const authOptions: AuthOptions = {
  // `useSecureCookies` explícito: sem ele o NextAuth deduzia o prefixo
  // `__Secure-` da URL inferida do request, e os leitores do cookie deduziam
  // de outro jeito. Ver `lib/session-cookie.ts`.
  useSecureCookies,
  session: {
    strategy: "jwt",
    maxAge: SESSION_MAX_AGE, // 8h
    // `updateAge` precisa ser MENOR que `maxAge`, senão o cookie nunca é
    // reemitido dentro da própria validade e a sessão vira um teto absoluto:
    // o default do NextAuth é 24h, contra as 8h daqui. Com 1h o cookie
    // acompanha o access token do back-end, que também dura ~1h, e a sessão
    // desliza enquanto o usuário estiver ativo.
    updateAge: Number(process.env.NEXTAUTH_SESSION_UPDATE_AGE || 60 * 60),
  },
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
    }),
  ],
  pages: {
    signIn: "/login",
    error: "/auth/error",
  },
  callbacks: {
    async signIn({ profile, account }) {
      if (!profile?.email) {
        console.error("Email não encontrado no profile do Google");
        return false;
      }
      if (!account?.id_token) {
        console.error("id_token não encontrado na resposta do Google");
        return false;
      }

      // Chamar back-end para obter JWT e dados do usuário
      try {
        const response = await fetch(API_ENDPOINTS.AUTH_GOOGLE, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id_token: account.id_token,
            email: profile.email,
            name: profile.name || profile.email.split('@')[0],
            google_id: account?.providerAccountId || 'google-oauth'
          })
        });

        if (!response.ok) {
          const error = await response.text();
          console.error('Auth failed:', response.status, error);
          // 401/403 são decisão do back-end sobre este usuário; 5xx e demais
          // status são falha nossa. Separar os dois evita dizer "você não tem
          // permissão" para quem só pegou o back-end fora do ar.
          if (response.status === 401 || response.status === 403) {
            return false;
          }
          // String de retorno = redirecionamento; é o contrato do callback
          // `signIn` no NextAuth. `false` viraria "AccessDenied".
          return BACKEND_UNAVAILABLE_URL;
        }

        const data = await response.json() as BackendAuthData;

        // Armazenar dados no profile para passar aos callbacks jwt/session
        (profile as ExtendedProfile).backendData = data;

        return true;

      } catch (error) {
        console.error('Auth error:', error);
        return BACKEND_UNAVAILABLE_URL;
      }
    },

    async jwt({ token, profile }) {
      // Primeiro login: adicionar dados do back-end ao token
      const extendedProfile = profile as ExtendedProfile;
      const profilePicture =
        (profile as { picture?: string; image?: string } | null)?.picture ||
        (profile as { picture?: string; image?: string } | null)?.image;
      if (profilePicture) {
        (token as { picture?: string }).picture = profilePicture;
      }
      if (extendedProfile?.backendData) {
        const backendData = extendedProfile.backendData;
        token.accessToken = backendData.access_token;
        token.refreshToken = backendData.refresh_token;
        token.user = {
          ...backendData.user,
          image: profilePicture ?? token.user?.image ?? (token as { picture?: string }).picture,
        };
      } else if (profilePicture && token.user) {
        token.user = {
          ...token.user,
          image: profilePicture,
        };
      } else if (token.user && (token as { picture?: string }).picture && !token.user.image) {
        token.user = {
          ...token.user,
          image: (token as { picture?: string }).picture,
        };
      }
      return token;
    },

    async session({ session, token }) {
      // Não expor accessToken para o cliente; token fica apenas em cookie HttpOnly.
      if (token.user) {
        const tokenUser = token.user as BackendAuthData['user'] & { image?: string };
        const tokenPicture = (token as { picture?: string }).picture;
        session.user = {
          ...session.user,
          ...tokenUser,
          image: tokenUser.image ?? tokenPicture ?? session.user?.image,
        };
      }
      return session;
    }
  },
  secret: process.env.NEXTAUTH_SECRET,
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
