import NextAuth, { DefaultSession } from "next-auth";
import { JWT } from "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      name: string;
      email: string;
      image?: string;
      role: "ADMIN" | "MANAGER" | "CURATOR" | "CHECKER" | "SENDER";
      is_active: boolean;
    };
  }

  interface User {
    access_token: string;
    user: {
      id: string;
      email: string;
      name: string;
      role: "ADMIN" | "MANAGER" | "CURATOR" | "CHECKER" | "SENDER";
      is_active: boolean;
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    user?: {
      id: string;
      email: string;
      name: string;
      image?: string;
      role: "ADMIN" | "MANAGER" | "CURATOR" | "CHECKER" | "SENDER";
      is_active: boolean;
    };
  }
}
