import type { ReenvioLiberado } from "@/types/process"

/** "15/10/2026", no fuso do navegador (o back-end manda a data com fuso). */
export function dataDaLiberacao(reenvio: ReenvioLiberado): string {
  const data = new Date(reenvio.liberado_em)
  return Number.isNaN(data.getTime()) ? "" : data.toLocaleDateString("pt-BR")
}

/**
 * O aviso que a clínica vê quando reenvia um prontuário já liberado. O reenvio
 * não vai para a Checagem: sem o aviso, ela entendia que o documento não tinha
 * sido aprovado e mandava de novo.
 */
export function mensagemReenvio(reenvio: ReenvioLiberado): string {
  const data = dataDaLiberacao(reenvio)
  return data
    ? `Este prontuário já foi liberado em ${data}. Não é preciso reenviar.`
    : "Este prontuário já foi liberado. Não é preciso reenviar."
}
