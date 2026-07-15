"""
Gera logs de exemplo reproduzindo os mesmos pontos de log de
ocr_service.py e workflow_service.py, usando dados FALSOS, para
verificar visualmente que CPF/nome/identificadores saem mascarados.

Uso:
    cd back-end
    python3 scripts/verificar_mascaramento_logs.py

O arquivo de log é escrito em back-end/logs_teste_pii/app.log (fora da
pasta logs/ padrão, que pertence a root neste ambiente).
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logging import setup_logging
from app.core.pii import mask_cpf, mask_identifier, mask_name

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs_teste_pii", "app.log")
LOG_PATH = os.path.abspath(LOG_PATH)

# Dados de exemplo, claramente falsos.
CPF_FAKE = "12345678900"
CPF_ALT_FAKE = "98765432100"
PASSAPORTE_FAKE = "AB123456"
CNPJ_FAKE = "12345678000190"
NOME_FAKE = "Fulano de Tal Teste"

os.environ.setdefault("LOG_FORMAT", "plain")
setup_logging(LOG_PATH)
logger = logging.getLogger("verificacao_pii")

logger.info(f"[OCR] CPF extraído: {mask_cpf(CPF_FAKE)}")
logger.info(f"[OCR] Passaporte extraído: {mask_identifier(PASSAPORTE_FAKE)}")
logger.info(f"[OCR] CNPJ extraído: {mask_identifier(CNPJ_FAKE)}")
logger.info(f"[WORKFLOW] Realizando validação para identificador: {mask_identifier(CPF_FAKE)}")

import json
logger.info("[WORKFLOW-EVENT] %s", json.dumps({
    "event": "ocr_completed",
    "run_id": "teste-run-id",
    "cpf_extraido": mask_cpf(CPF_FAKE),
    "passaporte_extraido": mask_identifier(PASSAPORTE_FAKE),
    "cnpj_extraido": mask_identifier(CNPJ_FAKE),
    "patient_name_from_ocr": mask_name(NOME_FAKE),
}, ensure_ascii=False))
logger.info("[WORKFLOW-EVENT] %s", json.dumps({
    "event": "prontuai_api_cpf_alternatives",
    "run_id": "teste-run-id",
    "cpf_inicial": mask_cpf(CPF_FAKE),
    "cpfs_alternativos": [mask_cpf(CPF_ALT_FAKE)],
}, ensure_ascii=False))

for handler in logging.getLogger().handlers:
    handler.flush()

with open(LOG_PATH, encoding="utf-8") as f:
    conteudo = f.read()

print(f"\nLog escrito em: {LOG_PATH}\n")
print("--- conteúdo ---")
print(conteudo)
print("--- fim ---\n")

vazamentos = [v for v in (CPF_FAKE, CPF_ALT_FAKE, NOME_FAKE) if v in conteudo]
if vazamentos:
    print(f"FALHOU: valor(es) não mascarado(s) encontrado(s) no log: {vazamentos}")
    sys.exit(1)
print("OK: nenhum CPF/nome bruto encontrado no log; apenas versões mascaradas.")
