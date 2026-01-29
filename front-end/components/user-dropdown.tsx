"use client"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useSession, signOut } from "next-auth/react";
import { useMemo } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import {
  RiLogoutCircleLine,
  RiTimer2Line,
  RiUserLine,
  RiFindReplaceLine,
  RiPulseLine,
} from "@remixicon/react";

export default function UserDropdown() {
  const { data: session } = useSession();
  const userName = session?.user?.name || session?.user?.email || "Usuário";
  const userEmail = session?.user?.email || "email@dominio.com";
  const avatarSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="32" fill="#E5E7EB"/><circle cx="32" cy="24" r="12" fill="#9CA3AF"/><path d="M16 52c4-10 28-10 32 0" fill="#9CA3AF"/></svg>`;
  const avatarUrl = `data:image/svg+xml;utf8,${encodeURIComponent(avatarSvg)}`;
  const initials = useMemo(() => {
    const parts = userName.trim().split(" ");
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
    return `${parts[0][0] ?? ""}${parts[parts.length - 1][0] ?? ""}`.toUpperCase();
  }, [userName]);
  const disableActions = true;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto p-0 hover:bg-transparent">
          <Avatar className="size-8">
            <AvatarImage
              src={avatarUrl}
              width={32}
              height={32}
              alt="Profile image"
            />
            <AvatarFallback>{initials}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="max-w-64 p-2" align="end">
        <DropdownMenuLabel className="flex min-w-0 flex-col py-0 px-1 mb-2">
          <span className="truncate text-sm font-medium text-foreground mb-0.5">
            {userName}
          </span>
          <span className="truncate text-xs font-normal text-muted-foreground">
            {userEmail}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuItem className="gap-3 px-1" disabled={disableActions}>
          <RiTimer2Line
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Histórico</span>
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-3 px-1" disabled={disableActions}>
          <RiUserLine
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Perfil</span>
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-3 px-1" disabled={disableActions}>
          <RiPulseLine
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Alterações</span>
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-3 px-1" disabled={disableActions}>
          <RiFindReplaceLine
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Pesquisas</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          className="gap-3 px-1"
          onSelect={(event) => {
            event.preventDefault();
            signOut({ callbackUrl: "/" });
          }}
        >
          <RiLogoutCircleLine
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Sair</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
