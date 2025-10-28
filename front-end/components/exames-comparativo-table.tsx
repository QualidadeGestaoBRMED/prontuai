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

// Define o tipo para cada item na tabela de comparação, baseado no novo JSON
export type TabelaComparacaoItem = {
  exame: string;
  status: "encontrado" | "faltante" | "parcialmente_encontrado" | "extra_no_ocr";
  justificativa: string;
};

// Define as props do componente, que agora recebe a tabela de comparação
export interface ExamesComparativoTableProps {
  tabela: TabelaComparacaoItem[];
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

// Componente da tabela de comparação de exames
export default function ExamesComparativoTable({ tabela = [] }: ExamesComparativoTableProps) {
  // Ordena os exames: primeiro os "encontrados", depois os "faltantes", depois os "extras"
  const sortedExames = [...tabela].sort((a, b) => {
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
    return getStatusOrder(a.status) - getStatusOrder(b.status);
  });

  return (
    <TooltipProvider>
      <Table className="ml-4 w-max">
        <TableHeader>
          <TableRow className="">
            <TableHead className="w-1/3">Exame Previsto</TableHead><TableHead className="w-1/6 text-center">Status</TableHead><TableHead className="flex pl-32 pt-2.5 text-right">Justificativa</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedExames.map((item, index) => {
            const conf = getConformidade(item.status);
            return (
              <TableRow key={`${item.exame}-${index}`}>
                <TableCell className="font-medium px-4">
                  {item.exame}
                </TableCell><TableCell className={`text-center font-medium ${conf.color}`}>
                  <div className="flex flex-col items-center justify-center gap-1">
                    {conf.icon}
                    <span className="text-xs mt-1">{conf.label}</span>
                  </div>
                </TableCell><TableCell className=" pr-10 pt-4 text-sm text-muted-foreground flex justify-end text-right">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <InfoIcon className="cursor-help size-4" />
                    </TooltipTrigger>
                    <TooltipContent>
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