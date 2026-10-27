import { CheckIcon, XIcon, InfoIcon, AlertTriangleIcon } from "lucide-react"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { TabelaComparacaoItem } from "@/types/process"
import { cn } from "@/lib/utils"

// Define as props do componente, que agora recebe a tabela de comparação
export interface ExamesComparativoTableProps {
  tabela: TabelaComparacaoItem[];
  /**
   * Mostra o status "Só na lista do ASO" no lugar de "Encontrado" quando o nome
   * do exame só aparece na lista de procedimentos do ASO, sem resultado no PDF.
   * É só exibição: a decisão da IA não muda. A linha de origem fica nas
   * Evidências do modal. Só a tela do revisor liga; a da clínica e o chat
   * seguem como antes. Documento antigo, sem os campos, renderiza igual.
   */
  mostrarEvidencia?: boolean;
  /**
   * Liga o atalho até o PDF, como a lista de registros da Triagem BR NET: a
   * linha do exame é o registro, e clicar nela destaca no documento onde ele
   * aparece. `porExame` diz quantas ocorrências cada exame tem; clicar de novo
   * na mesma linha passa para a próxima. Exame sem ocorrência não é clicável.
   * Sem a prop, a tabela fica como antes (chat, tela da clínica).
   */
  localizar?: {
    porExame: Record<string, number>;
    ativo?: { exame: string; indice: number } | null;
    onLocalizar: (exame: string) => void;
  };
}

// Função auxiliar para obter o ícone e a cor com base no status do exame
function getConformidade(status: TabelaComparacaoItem['status']) {
  switch (status) {
    case "encontrado":
      return { 
        label: "Encontrado", 
        icon: <CheckIcon className="inline-flex stroke-emerald-600" size={16} />, 
        color: "text-emerald-600" 
      };
    case "faltante":
      return { 
        label: "Faltante", 
        icon: <XIcon className="inline-flex stroke-red-600" size={16} />, 
        color: "text-red-600" 
      };
    case "extra_no_ocr":
      return { 
        label: "Extra no OCR", 
        icon: <AlertTriangleIcon className="inline-flex stroke-yellow-500" size={16} />, 
        color: "text-yellow-500" 
      };
    // O status "parcialmente_encontrado" pode ser tratado visualmente aqui se necessário
    default:
      return { label: "-", icon: null, color: "text-muted-foreground" };
  }
}

// Status exibido para o exame encontrado só na lista do ASO. A IA continua
// dando o exame como encontrado; a tela avisa o revisor para conferir no PDF.
const SO_NA_LISTA = {
  label: "Só na lista do ASO",
  icon: <AlertTriangleIcon className="inline-flex stroke-yellow-500" size={16} />,
  color: "text-yellow-500",
};

// Componente da tabela de comparação de exames
/**
 * A ordem em que a tabela mostra os exames: primeiro os "encontrados", depois os
 * "faltantes", depois os "extras". Com a evidência ligada, os "só na lista do ASO"
 * abrem o grupo dos encontrados (continuam encontrados, mas são os que o revisor
 * precisa conferir no PDF). O sort é estável: fora isso, a ordem do back-end se
 * mantém. Exportada para quem precisa seguir a mesma sequência — o botão que
 * passa de exame em exame no PDF.
 */
export function ordenarComparativo(tabela: TabelaComparacaoItem[], mostrarEvidencia = false): TabelaComparacaoItem[] {
  const ehSoLista = (item: TabelaComparacaoItem) =>
    mostrarEvidencia && item.evidencia === "so_lista";
  const getStatusOrder = (status: TabelaComparacaoItem['status']) => {
    switch (status) {
      case "encontrado":
        return 1;
      case "faltante":
        return 2;
      case "extra_no_ocr":
        return 3;
      default:
        return 4;
    }
  };
  return [...tabela].sort((a, b) => {
    const porStatus = getStatusOrder(a.status) - getStatusOrder(b.status);
    if (porStatus !== 0) return porStatus;
    return Number(ehSoLista(b)) - Number(ehSoLista(a));
  });
}

export default function ExamesComparativoTable({ tabela = [], mostrarEvidencia = false, localizar }: ExamesComparativoTableProps) {
  const ehSoLista = (item: TabelaComparacaoItem) =>
    mostrarEvidencia && item.evidencia === "so_lista";
  const sortedExames = ordenarComparativo(tabela, mostrarEvidencia);

  return (
    <TooltipProvider>
      <Table className="w-full">
        <TableHeader>
          <TableRow>
            <TableHead className="w-2/5">Exame Previsto</TableHead>
            <TableHead className="w-1/5 text-center">Status</TableHead>
            <TableHead className="w-2/5 text-left">Justificativa</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedExames.map((item, index) => {
            const conf = ehSoLista(item) ? SO_NA_LISTA : getConformidade(item.status);
            const localizavel = Boolean(localizar?.porExame[item.exame]);
            const selecionado = localizar?.ativo?.exame === item.exame;
            return (
              <TableRow
                key={`${item.exame}-${index}`}
                onClick={localizavel ? () => localizar?.onLocalizar(item.exame) : undefined}
                aria-selected={localizavel ? selecionado : undefined}
                className={cn(
                  localizavel && "cursor-pointer",
                  selecionado && "bg-cyan-50/70 shadow-[inset_2px_0_0_0_var(--primary)] hover:bg-cyan-50/70",
                ) || undefined}
              >
                <TableCell className={cn("font-medium align-top whitespace-normal", selecionado && "text-primary")}>
                  {localizavel ? (
                    // Só para o teclado: o clique é da linha inteira.
                    <button type="button" className="text-left rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30">
                      {item.exame}
                    </button>
                  ) : (
                    item.exame
                  )}
                </TableCell>
                <TableCell className={`text-center font-medium align-top ${conf.color}`}>
                  <div className="flex flex-col items-center justify-center gap-1">
                    {conf.icon}
                    <span className="text-xs mt-1">{conf.label}</span>
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground align-top">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-center gap-2 text-muted-foreground">
                        <InfoIcon className="size-4 cursor-help text-muted-foreground" />
                        <span className="text-xs">Passe o mouse</span>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-md">
                      <p>{item.justificativa}</p>
                    </TooltipContent>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TooltipProvider>
  )
}

export type { TabelaComparacaoItem } from "@/types/process";
