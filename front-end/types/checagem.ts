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
  // Era reenvio e voltou para a revisão (botão "É um complemento", ou o
  // original rejeitado). Ver `result_payload.reenvio_desfeito`.
  complemento?: boolean;
};

export type AcaoChecagem = "aprovar" | "rejeitar";
