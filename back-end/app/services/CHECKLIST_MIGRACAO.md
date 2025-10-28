# Checklist de Migração e Regras Essenciais

Este checklist garante que todas as regras, fallbacks e detalhes importantes do sistema original sejam mantidos na migração para a nova arquitetura FastAPI.

## OCR (Extração de Exames e CPF dos Documentos)
- [x] Prompt detalhado para LLM, incluindo:
  - [x] Priorizar CPF após sigla de UF
  - [x] Se houver mais de um UF/CPF, pegar o primeiro
  - [x] Se não houver, pegar o primeiro CPF de 11 dígitos
  - [x] Não inventar exames, não inferir de menções genéricas
  - [x] Extrair exames de headers e linhas no formato 'NOME DO EXAME - DATA'
  - [x] Retornar JSON válido, com "cpf": null se não encontrar, e "exames": [] se não houver exames
  - [x] Retornar nomes dos exames em caixa alta
- [x] Fallback de CPF via regex se LLM não identificar
- [x] Tratamento de erros (resposta inválida, chaves faltando, etc)
- [x] Salvamento do markdown OCR para referência
- [x] Liberação de memória GPU após OCR

## RPA/BRMED (Extração de Exames Obrigatórios)
- [x] Regex/parsing flexível para nome e exames
- [x] Ignorar duplicatas e nomes de seção
- [x] Extrair apenas nomes dos exames em português, antes de '/' ou '*'
- [x] Dividir linhas por tabulação para múltiplos exames
- [x] Fallbacks de parsing para nome e exames
- [x] Tratamento de erros amigável

## Validação/Comparação de Exames
- [x] Normalização dos nomes dos exames (remover acentos, caixa alta/baixa, etc)
- [x] Fuzzy matching para considerar variações ortográficas
- [x] Comparar listas e identificar exames obrigatórios faltantes
- [x] Mensagens de erro claras e amigáveis
- [x] Salvamento dos arquivos processados para auditoria

## Robustez e Resiliência
- [x] Logs estruturados e detalhados
- [x] Validação de parâmetros obrigatórios (CPF, arquivo, etc)
- [x] Retorno consistente de erros HTTP (400 para input, 500 para erro interno)

---

**À medida que cada item for implementado, marque como concluído neste checklist.** 