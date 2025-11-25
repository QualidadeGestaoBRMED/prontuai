"use client";

import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import Image from "next/image";
import { ShieldAlert, Home, Mail, Loader2 } from "lucide-react";
import { Suspense, useState } from "react";

function ErrorContent() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");
  const [isLoadingSupport, setIsLoadingSupport] = useState(false);

  const getErrorMessage = () => {
    switch (error) {
      case "AccessDenied":
        return {
          title: "Acesso Negado",
          description: "Você não tem permissão para acessar esta aplicação.",
          details: "A aplicação é de uso exclusivo da BR MED. Se você acha que isso está errado, entre em contato com o time de On Going para verificar suas permissões de acesso.",
        };
      case "Configuration":
        return {
          title: "Erro de Configuração",
          description: "Houve um problema com a configuração da autenticação.",
          details: "Por favor, entre em contato com o suporte técnico.",
        };
      default:
        return {
          title: "Erro de Autenticação",
          description: "Ocorreu um erro durante o processo de login.",
          details: "Por favor, tente novamente ou entre em contato com o suporte.",
        };
    }
  };

  const errorInfo = getErrorMessage();

  return (
    <div className="min-h-screen bg-sidebar flex items-center justify-center p-4">
      <div className="max-w-4xl w-full">
        
        <div className="text-center mb-8 mt-6">
          <Image
            src="/logo.png"
            alt="ProntuAI Logo"
            width={200}
            height={80}
            className="mx-auto mb-4"
          />
        </div>

        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Conteúdo */}
          <div className="p-8 md:p-10">
            {/* Ilustração em destaque */}
            <div className="flex justify-center mb-6">
              <Image
                src="/404.png"
                alt="Acesso Negado"
                width={500}
                height={375}
                className="object-contain w-full max-w-xl"
                priority
              />
            </div>

            {/* Header com gradiente azul */}
            <div className="text-center mb-6">
              <div className="inline-flex items-center justify-center bg-gradient-to-r from-[#005A6F] to-[#007891] rounded-full p-3 mb-4 shadow-lg">
                <ShieldAlert className="w-8 h-8 text-white" />
              </div>
              <h1 className="text-3xl font-bold text-gray-900 mb-3">
                {errorInfo.title}
              </h1>
              <p className="text-gray-600 text-base">
                {errorInfo.description}
              </p>
            </div>

            {/* Mensagem informativa */}
            <div className="bg-gradient-to-r from-blue-50 to-cyan-50 border-l-4 border-[#005A6F] p-5 rounded-r-lg mb-6">
              <div className="flex items-start">
                <Mail className="w-5 h-5 text-[#005A6F] mt-0.5 mr-3 flex-shrink-0" />
                <div>
                  <p className="text-gray-700 leading-relaxed text-sm">
                    {errorInfo.details}
                  </p>
                </div>
              </div>
            </div>

            {/* Botões de ação */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link href="/login">
                <Button
                  className="
                    w-full sm:w-auto
                    bg-[#005A6F]
                    hover:bg-[#004A5C]
                    text-white
                    shadow-lg
                    transition-all
                    duration-300
                    hover:scale-105
                  "
                >
                  <Home className="w-4 h-4 mr-2" />
                  Voltar ao Login
                </Button>
              </Link>

              <a href="mailto:projetos@grupobrmed.com.br" onClick={() => setIsLoadingSupport(true)}>
                <Button
                  variant="outline"
                  className="
                    w-full sm:w-auto
                    border-2
                    border-[#005A6F]
                    text-[#005A6F]
                    hover:bg-[#005A6F]/10
                    hover:text-[#005A6F]
                    transition-all
                    duration-300
                  "
                  disabled={isLoadingSupport}
                >
                  {isLoadingSupport ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Mail className="w-4 h-4 mr-2" />
                  )}
                  {isLoadingSupport ? "Abrindo email..." : "Contatar Suporte"}
                </Button>
              </a>
            </div>

            {/* Informação técnica (colapsável se necessário) */}
            {error && (
              <div className="mt-6 pt-4 border-t border-gray-200">
                <details className="text-xs text-gray-500">
                  <summary className="cursor-pointer hover:text-gray-700 font-medium">
                    Detalhes técnicos
                  </summary>
                  <div className="mt-2 bg-gray-50 p-3 rounded font-mono">
                    <p>Código de erro: {error}</p>
                  </div>
                </details>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
       
      </div>
    </div>
  );
}

export default function AuthErrorPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-sidebar flex items-center justify-center text-white">Carregando...</div>}>
      <ErrorContent />
    </Suspense>
  );
}
