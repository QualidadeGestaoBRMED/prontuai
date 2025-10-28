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
};

export type AcaoChecagem = "aprovar" | "rejeitar";
