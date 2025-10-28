import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
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
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto p-0 hover:bg-transparent">
          <Avatar className="size-8">
            <AvatarImage
              src="https://raw.githubusercontent.com/origin-space/origin-images/refs/heads/main/exp2/user-02_mlqqqt.png"
              width={32}
              height={32}
              alt="Profile image"
            />
            <AvatarFallback>KK</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="max-w-64 p-2" align="end">
        <DropdownMenuLabel className="flex min-w-0 flex-col py-0 px-1 mb-2">
          <span className="truncate text-sm font-medium text-foreground mb-0.5">
            Enfermeira
          </span>
          <span className="truncate text-xs font-normal text-muted-foreground">
            enfermeira@grupobrmed.com.br
          </span>
        </DropdownMenuLabel>
        <DropdownMenuItem className="gap-3 px-1">
          <RiTimer2Line
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Histórico</span>
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-3 px-1">
          <RiUserLine
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Perfil</span>
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-3 px-1">
          <RiPulseLine
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Alterações</span>
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-3 px-1">
          <RiFindReplaceLine
            size={20}
            className="text-current"
            aria-hidden="true"
          />
          <span>Pesquisas</span>
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-3 px-1">
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
