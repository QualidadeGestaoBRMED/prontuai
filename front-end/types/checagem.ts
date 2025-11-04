export type StatusDocumento = "pendente" | "aprovado" | "rejeitado";

export type DocumentoChecagem = {
  id: string;
  cpf: string;
  paciente: string;
  dataUpload: string;
  dataProcessamento?: string;
  status: StatusDocumento;
  motivoRejeicao?: string;
  examesFaltantes: number;
  examesExtras: number;
  documentoUrl?: string;
  decisaoIA?: 'approved' | 'rejected'; // Indica se IA aprovou ou rejeitou (antes de revisão humana)
  submittedBy?: string; // Email do usuário que enviou
};

export type AcaoChecagem = "aprovar" | "rejeitar";
