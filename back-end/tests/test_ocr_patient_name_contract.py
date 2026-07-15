from io import BytesIO

import pytest
from fastapi import UploadFile

from app.services import ocr_service


@pytest.mark.asyncio
async def test_ocr_pipeline_returns_patient_name(monkeypatch):
    markdown = """
Nome BRUNO ALEXANDRE EVORA PIMENTEL Empresa STARNAV SERVIÇOS LTDA.
Nome / Name: GR NO ALLXAN ME IVORA EMENTE
NOME: BRUNO ALEXANDRE EVORA PIMENTEL
NOME: BRUNO ALEXANDRE EVORA PIMENTEL
"""
    upload = UploadFile(filename="aso.pdf", file=BytesIO(b"pdf"))

    monkeypatch.setattr(ocr_service.settings, "USE_TEXTRACT", False)
    monkeypatch.setattr(
        ocr_service,
        "processar_arquivo_docling",
        lambda _file_path: markdown,
    )
    monkeypatch.setattr(ocr_service, "extrair_cpf_regex", lambda _markdown: None)
    monkeypatch.setattr(ocr_service, "extrair_cpf_ia", lambda _markdown: None)
    monkeypatch.setattr(ocr_service, "extrair_passaporte_regex", lambda _markdown: None)
    monkeypatch.setattr(ocr_service, "extrair_cnpj_regex", lambda _markdown: None)
    monkeypatch.setattr(
        ocr_service,
        "extrair_exames_ia",
        lambda _markdown: {"exames": []},
    )

    result = await ocr_service._ocr_pipeline_impl(upload, salvar_markdown=False)

    assert result["patient_name"] == "BRUNO ALEXANDRE EVORA PIMENTEL"
    assert result["markdown_content"] == markdown
