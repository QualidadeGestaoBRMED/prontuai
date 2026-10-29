import { useEffect, useRef } from "react"
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
import { PessoaNoLaudo, TabelaComparacaoItem } from "@/types/process"
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
   *
   * Liga também o status "Laudo de outra pessoa": o laudo do exame traz nome e
   * CPF de quem não é o paciente do pedido (STC-947). Vale para encontrado e
   * extra; o motivo, com o nome e o CPF mascarado, fica no tooltip da
   * justificativa ("Passe o mouse").
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
  /**
   * Para a tabela dos exames além do previsto no BRNET: o cabeçalho da primeira
   * coluna e o status no lugar de "Extra no OCR". Sem eles, fica como antes.
   */
  rotuloColunaExame?: string;
  rotuloExtra?: string;
}

// Função auxiliar para obter o ícone e a cor com base no status do exame
function getConformidade(status: TabelaComparacaoItem['status'], rotuloExtra = "Extra no OCR") {
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
        label: rotuloExtra, 
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

// Status exibido para o exame cujo laudo traz nome e CPF de outra pessoa. É
// aviso, como o "Só na lista do ASO": a IA não muda a decisão, o revisor confere.
const OUTRA_PESSOA = {
  label: "Laudo de outra pessoa",
  icon: <AlertTriangleIcon className="inline-flex stroke-yellow-500" size={16} />,
  color: "text-yellow-500",
};

function descreverPessoa(pessoa: PessoaNoLaudo): string {
  return `${pessoa.nome} (CPF ${pessoa.cpf}${pessoa.pagina ? `, página ${pessoa.pagina}` : ""})`;
}

// O motivo do aviso, com quem é a outra pessoa.
export function motivoOutraPessoa(pessoas: PessoaNoLaudo[]): string {
  return (
    `O laudo traz nome e CPF de quem não é o paciente do pedido: ${pessoas.map(descreverPessoa).join("; ")}. ` +
    "Confira se o laudo é de outro colaborador."
  );
}

// Componente da tabela de comparação de exames
/**
 * A ordem em que a tabela mostra os exames: primeiro os "encontrados", depois os
 * "faltantes", depois os "extras". Com a evidência ligada, o laudo de outra
 * pessoa e depois os "só na lista do ASO" abrem o seu grupo (o status não muda,
 * mas são os que o revisor precisa conferir no PDF). O sort é estável: fora isso, a ordem do back-end se
 * mantém. Exportada para quem precisa seguir a mesma sequência — o botão que
 * passa de exame em exame no PDF.
 */
export function ordenarComparativo(tabela: TabelaComparacaoItem[], mostrarEvidencia = false): TabelaComparacaoItem[] {
  const ehSoLista = (item: TabelaComparacaoItem) =>
    mostrarEvidencia && item.evidencia === "so_lista";
  const ehOutraPessoa = (item: TabelaComparacaoItem) =>
    mostrarEvidencia && Boolean(item.outra_pessoa?.length);
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
    const porOutraPessoa = Number(ehOutraPessoa(b)) - Number(ehOutraPessoa(a));
    if (porOutraPessoa !== 0) return porOutraPessoa;
    return Number(ehSoLista(b)) - Number(ehSoLista(a));
  });
}

export default function ExamesComparativoTable({
  tabela = [],
  mostrarEvidencia = false,
  localizar,
  rotuloColunaExame = "Exame Previsto",
  rotuloExtra,
}: ExamesComparativoTableProps) {
  const ehSoLista = (item: TabelaComparacaoItem) =>
    mostrarEvidencia && item.evidencia === "so_lista";
  const sortedExames = ordenarComparativo(tabela, mostrarEvidencia);

  // Quem passa de exame em exame pelo botão do PDF não está olhando a lista: ela
  // rola junto, para a linha do exame em foco ficar à vista.
  const corpo = useRef<HTMLTableSectionElement>(null);
  const exameAtivo = localizar?.ativo?.exame;
  useEffect(() => {
    if (!exameAtivo) return;
    corpo.current
      ?.querySelector('tr[aria-selected="true"]')
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [exameAtivo]);

  return (
    <TooltipProvider>
      <Table className="w-full">
        <TableHeader>
          <TableRow>
            <TableHead className="w-2/5">{rotuloColunaExame}</TableHead>
            <TableHead className="w-1/5 text-center">Status</TableHead>
            <TableHead className="w-2/5 text-left">Justificativa</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody ref={corpo}>
          {sortedExames.map((item, index) => {
            const outrasPessoas = mostrarEvidencia ? item.outra_pessoa ?? [] : [];
            const conf = outrasPessoas.length
              ? OUTRA_PESSOA
              : ehSoLista(item)
                ? SO_NA_LISTA
                : getConformidade(item.status, rotuloExtra);
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
                    <TooltipContent className="max-w-md space-y-2">
                      {outrasPessoas.length > 0 && <p>{motivoOutraPessoa(outrasPessoas)}</p>}
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
