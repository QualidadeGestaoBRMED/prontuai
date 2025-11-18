import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { Providers } from "@/components/providers";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  metadataBase: new URL('https://prontuai.grupobrmed.com.br'),
  title: {
    default: "ProntuAI",
    template: "%s | ProntuAI",
  },
  description: "Sistema inteligente de validação e processamento de documentos médicos com IA",
  applicationName: "ProntuAI",
  icons: {
    icon: "/logo_metadado.png",
    shortcut: "/logo_metadado.png",
    apple: "/logo_metadado.png",
  },
  openGraph: {
    type: "website",
    locale: "pt_BR",
    title: "ProntuAI",
    description: "Sistema inteligente de validação e processamento de documentos médicos",
    siteName: "ProntuAI",
    images: [
      {
        url: "/logo_metadado.png",
        width: 1200,
        height: 630,
        alt: "ProntuAI",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ProntuAI",
    description: "Sistema inteligente de validação e processamento de documentos médicos",
    images: ["/logo_metadado.png"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#005A6F",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/logo_metadado.png" type="image/png" />
        <link rel="shortcut icon" href="/logo_metadado.png" type="image/png" />
        <link rel="apple-touch-icon" href="/logo_metadado.png" />
      </head>
      <body className="font-sans antialiased">
        <Providers>
          {children}
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
