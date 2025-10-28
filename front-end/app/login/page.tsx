"use client";

import { Button } from "@/components/ui/button";
import { signIn } from "next-auth/react";
import Image from "next/image";
import { RiGoogleFill } from "@remixicon/react";
import Link from "next/link";

export default function LoginPage() {
  return (
    <div className="container relative grid h-screen flex-col items-center justify-center lg:max-w-none lg:grid-cols-2 lg:px-0 bg-[#F3F3F3]">
      <div className="relative hidden h-full flex-col bg-muted p-10 text-white dark:border-r lg:flex">
        <div className="absolute inset-0 bg-sidebar" />
        <div className="relative z-20 flex flex-col items-start text-lg font-medium">
          <Image
            src="/logo.png"
            alt="Logo"
            width={220}
            height={100}
            className="object-contain"
          />

          <h1 className="mt-16 text-4xl font-medium tracking-tight">
            <span className="font-semibold">Prontu<span className="font-bold">AI</span></span> - A Inteligência Artificial da BR MED.
          </h1>
          <h1 className="mt-4 text-xl font-light">Analise seus prontuários de forma automatizada e segura.</h1>
          
      </div>

        
        <div className="relative z-20 mt-auto">
          <blockquote className="space-y-2">
            <p className="text-lg">
              “Esta ferramenta de IA me ajudou a economizar inúmeras horas de
              trabalho me permitiu focar no que realmente importa.&quot;
            </p>
            <footer className="text-sm">Técnica de enfermagem</footer>
          </blockquote>
        </div>
      </div>

      
      <div className="lg:p-8">
        <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
          <div className="flex flex-col space-y-2 text-center">
            <h1 className="text-5xl font-medium tracking-tight m-4">
              Prontu<span className="font-bold text-cyan-800">AI</span>
              <br /> 
            </h1>
            <span className="font-medium text-">A Inteligência Artifical da <span className="font-semibold" >BR MED</span>.</span>
            <p className="text-sm text-muted-foreground mt-4">
              Faça login com sua conta Google Corporativa para continuar.
            </p>
          </div>
          <Button
            onClick={() => signIn("google", { callbackUrl: "/chat" })}
            className="
              w-full max-w-xs mx-auto
              px-4 py-2
              text-sm font-medium text-white
              bg-[#007891] border border-transparent rounded-md shadow-sm
              hover:bg-[#007891]/90
              focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500
              mt-4
              sm:w-full
            "
          >
            <RiGoogleFill className="w-4 h-4 mr-2" />
            Entrar com o Google
          </Button>
          <p className="px-8 text-center text-sm text-muted-foreground">
            Ao clicar em continuar, você concorda com nossos{" "}
            <Link
              href="/"
              className="underline underline-offset-4 hover:text-primary"
            >
              Termos de Serviço
            </Link>{" "}
            e{" "}
            <Link
              href="/"
              className="underline underline-offset-4 hover:text-primary"
            >
              Política de Privacidade
            </Link>
            .
          </p>
        </div>
      </div>
    </div>
  );
}
