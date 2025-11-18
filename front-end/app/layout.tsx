import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { Providers } from "@/components/providers";
import type { Metadata } from "next";

export const metadata: Metadata = {
  metadataBase: new URL('https://prontuai.grupobrmed.com.br'),
  title: {
    default: "ProntuAI",
    template: "%s | ProntuAI",
  },
  description: "Sistema inteligente de validação e processamento de documentos médicos com IA",
  applicationName: "ProntuAI",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/logo.png", sizes: "192x192", type: "image/png" },
    ],
  },
  themeColor: "#005A6F",
  openGraph: {
    type: "website",
    locale: "pt_BR",
    title: "ProntuAI",
    description: "Sistema inteligente de validação e processamento de documentos médicos",
    siteName: "ProntuAI",
    images: [{ url: "/logo.png" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <Providers>
          {children}
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
