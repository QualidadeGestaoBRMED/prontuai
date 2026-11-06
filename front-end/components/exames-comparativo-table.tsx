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
import { DataAntiga, PessoaNoLaudo, TabelaComparacaoItem } from "@/types/process"
import { ParametroLido, SituacaoParametro } from "@/types/normalidade"
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
   * CPF de quem não é o paciente do pedido (STC-947). Só com o nome diferente,
   * sem CPF, o status é o mais fraco "Nome diferente no laudo". Vale para
   * encontrado e extra; o motivo, com o nome e o CPF mascarado, fica no tooltip
   * da justificativa ("Passe o mouse").
   */
  mostrarEvidencia?: boolean;
  /**
   * Liga a coluna "Normalidade": os valores lidos no laudo para cada exame, por
   * nome do exame. Sem a prop, a tabela fica como antes (chat, tela da clínica).
   * `carregando` mostra a coluna vazia enquanto a leitura não chega.
   */
  normalidade?: { carregando: boolean; porExame: Record<string, ParametroLido[]> };
  /**
   * Liga o atalho até o PDF, como a lista de registros da Triagem BR NET: a
   * linha do exame é o registro, e clicar nela destaca no documento onde ele
   * aparece. `porExame` diz quantas ocorrências cada exame tem; clicar de novo
   * na mesma linha passa para a próxima. Exame sem ocorrência não é clicável.
   * Com `onLocalizarValor`, o valor lido na coluna Normalidade leva ao número
   * no laudo. Sem a prop, a tabela fica como antes (chat, tela da clínica).
   */
  localizar?: {
    porExame: Record<string, number>;
    /** O destaque na tela: um exame (e a ocorrência) ou um valor dele. */
    ativo?: { exame: string; indice: number; parametro?: string } | null;
    onLocalizar: (exame: string) => void;
    onLocalizarValor?: (exame: string, parametro: ParametroLido) => void;
  };
  /**
   * Para a tabela dos exames além do previsto no BRNET: o cabeçalho da primeira
   * coluna e o status no lugar de "Extra no OCR". Sem eles, fica como antes.
   */
  rotuloColunaExame?: string;
  rotuloExtra?: string;
}

const SITUACAO: Record<SituacaoParametro, { label: string; className: string }> = {
  acima: { label: "▲ Acima", className: "bg-red-100 text-red-700 border-red-300" },
  abaixo: { label: "▼ Abaixo", className: "bg-amber-100 text-amber-700 border-amber-300" },
  alterado: { label: "Alterado", className: "bg-red-100 text-red-700 border-red-300" },
  normal: { label: "Normal", className: "bg-emerald-100 text-emerald-700 border-emerald-300" },
  sem_resultado: { label: "Não lido", className: "bg-slate-100 text-slate-600 border-slate-300" },
  sem_referencia: { label: "Sem referência", className: "bg-slate-100 text-slate-600 border-slate-300" },
};

export const foraDaFaixa = (p: ParametroLido) =>
  p.situacao === "acima" || p.situacao === "abaixo" || p.situacao === "alterado";

function CelulaNormalidade({ item, parametros, carregando, onLocalizar, ativo }: {
  item: TabelaComparacaoItem; parametros?: ParametroLido[]; carregando: boolean;
  /** Leva ao valor no PDF. Sem ela, ou sem posição do valor, o valor é texto. */
  onLocalizar?: (parametro: ParametroLido) => void;
  /** `chave` do parâmetro destacado no PDF agora. */
  ativo?: string | null;
}) {
  if (item.status === "faltante") return <span className="text-muted-foreground">—</span>;
  if (carregando) return <span className="text-xs text-muted-foreground">Lendo…</span>;
  if (!parametros?.length) return <span className="text-xs text-muted-foreground">Não se aplica</span>;
  return (
    <div className="flex flex-col gap-1.5">
      {parametros.map((p) => {
        const sit = SITUACAO[p.situacao];
        return (
          <div key={p.chave} className="text-xs leading-tight">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground">{p.nome}</span>
              {p.valor_texto && (p.localizacao && onLocalizar ? (
                <button
                  type="button"
                  onClick={(e) => {
                    // O valor tem destaque próprio; não deixa a linha tratar o clique.
                    e.stopPropagation()
                    onLocalizar(p)
                  }}
                  title="Ver o valor no documento"
                  className={cn(
                    "rounded-sm px-0.5 font-semibold underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                    // Mesmo marca-texto do trecho no PDF.
                    ativo === p.chave ? "bg-yellow-300/80 text-foreground" : "text-foreground hover:text-primary",
                  )}
                >
                  {p.valor_texto}{p.unidade ? ` ${p.unidade}` : ""}
                </button>
              ) : (
                <span className="font-semibold text-foreground">
                  {p.valor_texto}{p.unidade ? ` ${p.unidade}` : ""}
                </span>
              ))}
              <span className={`rounded border px-1.5 py-px text-[11px] font-medium ${sit.className}`}>{sit.label}</span>
            </div>
            <div className="text-[11px] text-muted-foreground">
              {p.situacao === "sem_resultado"
                ? "Valor não encontrado no PDF"
                : p.situacao === "sem_referencia"
                  ? "Faixa de referência não identificada no laudo"
                  : `Ref. do laudo: ${p.referencia}`}
            </div>
          </div>
        );
      })}
    </div>
  );
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

// O mesmo aviso quando só o nome é diferente, sem CPF para confirmar: pode ser
// laudo de outro colaborador, ou nome escrito à mão que o OCR leu mal.
const NOME_DIFERENTE = {
  ...OUTRA_PESSOA,
  label: "Nome diferente no laudo",
};

// Status exibido para o exame cuja coleta é muito anterior ao ASO. A IA rejeita o
// documento por isso (STC-991); o revisor libera quando o cliente autorizou.
const DATA_ANTIGA = {
  label: "Data antiga",
  icon: <AlertTriangleIcon className="inline-flex stroke-yellow-500" size={16} />,
  color: "text-yellow-500",
};

// De onde vem o aviso, com as duas datas.
export function motivoDataAntiga(data: DataAntiga): string {
  const referencia = data.referencia === "aso" ? `do ASO (${data.data_referencia})` : "da análise do documento";
  return `Coleta em ${data.data_exame}, ${data.dias} dias antes ${referencia}. Libere só se o cliente autorizou o exame antigo.`;
}

export function temCpf(pessoa: PessoaNoLaudo): boolean {
  return Boolean(pessoa.cpf);
}

function descreverPessoa(pessoa: PessoaNoLaudo): string {
  const detalhes = [pessoa.cpf && `CPF ${pessoa.cpf}`, pessoa.pagina && `página ${pessoa.pagina}`].filter(Boolean);
  return detalhes.length ? `${pessoa.nome} (${detalhes.join(", ")})` : pessoa.nome;
}

// O motivo do aviso, com quem é a outra pessoa.
export function motivoOutraPessoa(pessoas: PessoaNoLaudo[]): string {
  const comCpf = pessoas.filter(temCpf);
  const soNome = pessoas.filter((p) => !temCpf(p));
  const frases = [];
  if (comCpf.length) {
    frases.push(
      `O laudo traz nome e CPF de quem não é o paciente do pedido: ${comCpf.map(descreverPessoa).join("; ")}. ` +
        "Confira se o laudo é de outro colaborador.",
    );
  }
  if (soNome.length) {
    frases.push(
      `O laudo traz um nome diferente do paciente do pedido, sem CPF para confirmar: ${soNome.map(descreverPessoa).join("; ")}. ` +
        "Pode ser laudo de outro colaborador ou o nome mal lido pelo OCR; confira no PDF.",
    );
  }
  return frases.join(" ");
}

// Componente da tabela de comparação de exames
/**
 * A ordem em que a tabela mostra os exames: primeiro os "encontrados", depois os
 * "faltantes", depois os "extras". Com a evidência ligada, o laudo de outra
 * pessoa e depois os "só na lista do ASO" abrem o seu grupo (o status não muda,
 * mas são os que o revisor precisa conferir no PDF); com a normalidade, os de
 * valor fora da faixa vêm logo depois. O sort é estável: fora isso, a ordem do
 * back-end se mantém. Exportada para quem precisa seguir a mesma sequência — o
 * botão que passa de exame em exame no PDF.
 */
export function ordenarComparativo(
  tabela: TabelaComparacaoItem[],
  mostrarEvidencia = false,
  normalidade?: Record<string, ParametroLido[]>,
): TabelaComparacaoItem[] {
  const ehSoLista = (item: TabelaComparacaoItem) =>
    mostrarEvidencia && item.evidencia === "so_lista";
  const temAlterado = (item: TabelaComparacaoItem) =>
    Boolean(normalidade?.[item.exame]?.some(foraDaFaixa));
  const ehDataAntiga = (item: TabelaComparacaoItem) => mostrarEvidencia && Boolean(item.data_antiga);
  // Nome e CPF de outra pessoa primeiro, depois só o nome.
  const pesoOutraPessoa = (item: TabelaComparacaoItem) =>
    !mostrarEvidencia || !item.outra_pessoa?.length ? 0 : item.outra_pessoa.some(temCpf) ? 2 : 1;
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
    const porOutraPessoa = pesoOutraPessoa(b) - pesoOutraPessoa(a);
    if (porOutraPessoa !== 0) return porOutraPessoa;
    const porSoLista = Number(ehSoLista(b)) - Number(ehSoLista(a));
    if (porSoLista !== 0) return porSoLista;
    return (Number(ehDataAntiga(b)) - Number(ehDataAntiga(a))) || (Number(temAlterado(b)) - Number(temAlterado(a)));
  });
}

export default function ExamesComparativoTable({
  tabela = [],
  mostrarEvidencia = false,
  normalidade,
  localizar,
  rotuloColunaExame = "Exame Previsto",
  rotuloExtra,
}: ExamesComparativoTableProps) {
  const ehSoLista = (item: TabelaComparacaoItem) =>
    mostrarEvidencia && item.evidencia === "so_lista";
  const temAlterado = (item: TabelaComparacaoItem) =>
    Boolean(normalidade?.porExame[item.exame]?.some(foraDaFaixa));
  const sortedExames = ordenarComparativo(tabela, mostrarEvidencia, normalidade?.porExame);

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
            <TableHead className={normalidade ? "w-[30%]" : "w-2/5"}>{rotuloColunaExame}</TableHead>
            <TableHead className={normalidade ? "w-[15%] text-center" : "w-1/5 text-center"}>Status</TableHead>
            {normalidade && <TableHead className="w-[38%] text-left">Normalidade</TableHead>}
            <TableHead className={normalidade ? "w-[17%] text-left" : "w-2/5 text-left"}>Justificativa</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody ref={corpo}>
          {sortedExames.map((item, index) => {
            const outrasPessoas = mostrarEvidencia ? item.outra_pessoa ?? [] : [];
            const dataAntiga = mostrarEvidencia ? item.data_antiga : undefined;
            const conf = outrasPessoas.length
              ? outrasPessoas.some(temCpf)
                ? OUTRA_PESSOA
                : NOME_DIFERENTE
              : ehSoLista(item)
                ? SO_NA_LISTA
                : dataAntiga
                  ? DATA_ANTIGA
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
                  temAlterado(item) && "shadow-[inset_3px_0_0_0_rgb(220_38_38)]",
                  selecionado && "bg-cyan-50/70 hover:bg-cyan-50/70",
                  selecionado && !temAlterado(item) && "shadow-[inset_2px_0_0_0_var(--primary)]",
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
                {normalidade && (
                  <TableCell className="align-top whitespace-normal">
                    <CelulaNormalidade
                      item={item}
                      parametros={normalidade.porExame[item.exame]}
                      carregando={normalidade.carregando}
                      onLocalizar={
                        localizar?.onLocalizarValor
                          ? (p) => localizar.onLocalizarValor?.(item.exame, p)
                          : undefined
                      }
                      ativo={localizar?.ativo?.exame === item.exame ? localizar.ativo.parametro : null}
                    />
                  </TableCell>
                )}
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
                      {dataAntiga && <p>{motivoDataAntiga(dataAntiga)}</p>}
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
