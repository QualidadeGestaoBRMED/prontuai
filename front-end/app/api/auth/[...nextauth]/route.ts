import NextAuth, { AuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import type { Profile } from "next-auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const authOptions: AuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
    }),
  ],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async signIn({ profile, account }) {
      // Validar domínio
      if (!profile?.email?.endsWith("@grupobrmed.com.br")) {
        console.error("Email não é @grupobrmed.com.br");
        return false;
      }

      // Chamar back-end para obter JWT e dados do usuário
      try {
        const response = await fetch(`${API_URL}/v1/auth/google`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: profile.email,
            name: profile.name || profile.email.split('@')[0],
            google_id: account?.providerAccountId || 'google-oauth'
          })
        });

        if (!response.ok) {
          const error = await response.text();
          console.error('Auth failed:', error);
          return false;
        }

        const data = await response.json();

        // Armazenar dados no profile para passar aos callbacks jwt/session
        (profile as any).backendData = data;

        return true;

      } catch (error) {
        console.error('Auth error:', error);
        return false;
      }
    },

    async jwt({ token, user, account, profile }) {
      // Primeiro login: adicionar dados do back-end ao token
      if (profile && (profile as any).backendData) {
        const backendData = (profile as any).backendData;
        token.accessToken = backendData.access_token;
        token.user = backendData.user;
      }
      return token;
    },

    async session({ session, token }) {
      // Adicionar dados do token à session (acessível no client)
      if (token.accessToken) {
        (session as any).accessToken = token.accessToken;
      }
      if (token.user) {
        session.user = token.user as any;
      }
      return session;
    }
  },
  secret: process.env.NEXTAUTH_SECRET,
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
