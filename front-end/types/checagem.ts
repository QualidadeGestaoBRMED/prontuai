import type { ReenvioLiberado } from "@/types/process";

export type StatusDocumento = "pendente" | "aprovado" | "rejeitado";

export type DocumentoChecagem = {
  id: string;
  clinicName?: string;
  cpf: string;
  paciente: string;
  dataUpload: string;
  dataPrevisaoLiberacao?: string;
  dataProcessamento?: string;
  status: StatusDocumento;
  motivoRejeicao?: string;
  approvalReason?: string; // Justificativa para aprovação manual (quando IA rejeitou)
  examesFaltantes: number;
  examesExtras: number;
  documentoUrl?: string;
  decisaoIA?: 'approved' | 'rejected'; // Indica se IA aprovou ou rejeitou (antes de revisão humana)
  submittedBy?: string; // Email do usuário que enviou
  reenvio?: ReenvioLiberado | null; // Prontuário já liberado ou em revisão: vira a tag
};

export type AcaoChecagem = "aprovar" | "rejeitar";
