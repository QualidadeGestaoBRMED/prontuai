export type StatusProcessamento = "sucesso" | "erro" | "processando" | "pendente";

export type DocumentoPendente = {
  id: string;
  nome: string;
  cpf: string;
  dataUpload: string;
  status: StatusProcessamento;
  examesEncontrados: number;
  examesPrevistos: number;
  compatibilidade: number; // Porcentagem 0-100
  mensagem?: string;
};
