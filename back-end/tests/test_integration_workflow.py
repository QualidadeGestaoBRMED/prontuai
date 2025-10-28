import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import os
import json
from main import app

client = TestClient(app)

# --- Definição dos Casos de Teste ---
# Adicione novos casos a esta lista para expandir os testes de integração.
# Cada dicionário representa um cenário de teste completo.
TEST_CASES = [
    {
        "test_id": "periodico_ana_faltando_audiometria",
        "pdf_filename": "periodico_ana.pdf",
        # O que esperamos que a IA extraia do PDF.
        "expected_ocr_extraction": {
            "cpf": "67495788372",
            "exames": [
                'HEMOGRAMA', 'ERITROGRAMA', 'LEUCOGRAMA', 'GLICOSE',
                'COLESTEROL HDL', 'COLESTEROL LDL', 'TRIGLICERIDEOS',
                'ÁCIDO ÚRICO', 'CREATININA', 'GAMA GT', 'SUMARIO DE URINA'
            ]
        },
        # O que simulamos como sendo os exames obrigatórios para este caso.
        "mock_brmed_exams": {
            "nome": "ANA PAULA",
            "exames": [
                "HEMOGRAMA COMPLETO",
                "GLICOSE",
                "AUDIOMETRIA",  # Exame que deve ser marcado como faltante
                "GAMA GT"
            ]
        },
        # O resultado que esperamos da validação final.
        "expected_validation": {
            "status_liberado": False,
            "exames_faltantes": ["AUDIOMETRIA"],
            "exames_presentes": ["HEMOGRAMA COMPLETO", "GLICOSE", "GAMA GT"]
        }
    },
    {
        "test_id": "rafael_barroso_faltando_raiox",
        "pdf_filename": "BR MED - PERIÓDICO - RAFAEL BARROSO DE SOUZA FARIAS - EXAMES.pdf",
        "expected_ocr_extraction": {
            "cpf": "95659366368",
            "exames": [
                'ACUIDADE VISUAL', 'AUDIOMETRIA TONAL', 'HEMOGRAMA', 'GLICOSE',
                'LIPIDOGRAMA COMPLETO', 'CREATININA', 'TGO', 'TGP', 'GAMA GT',
                'FOSFATASE ALCALINA', 'BILIRRUBINA INDIRETA', 'TSH ULTRA SENSIVEL'
            ]
        },
        "mock_brmed_exams": {
            "nome": "RAFAEL BARROSO DE SOUZA FARIAS",
            "exames": [
                "AUDIOMETRIA TONAL",
                "HEMOGRAMA",
                "RAIO-X DE TÓRAX", # Exame que deve ser marcado como faltante
                "GLICOSE"
            ]
        },
        "expected_validation": {
            "status_liberado": False,
            "exames_faltantes": ["RAIO-X DE TÓRAX"],
            "exames_presentes": ["AUDIOMETRIA TONAL", "HEMOGRAMA", "GLICOSE"]
        }
    },
    {
        "test_id": "periodico_ana_regex_falha_cpf_ia_sucesso",
        "pdf_filename": "periodico_ana.pdf",
        "mock_regex_cpf": None, # Força o regex a retornar None
        "expected_ocr_extraction": {
            "cpf": "67495788372", # Este CPF virá da extração via IA
            "exames": [
                'HEMOGRAMA', 'ERITROGRAMA', 'LEUCOGRAMA', 'GLICOSE',
                'COLESTEROL HDL', 'COLESTEROL LDL', 'TRIGLICERIDEOS',
                'ÁCIDO ÚRICO', 'CREATININA', 'GAMA GT', 'SUMARIO DE URINA'
            ]
        },
        "mock_brmed_exams": {
            "nome": "ANA PAULA",
            "exames": [
                "HEMOGRAMA COMPLETO",
                "GLICOSE",
                "AUDIOMETRIA",
                "GAMA GT"
            ]
        },
        "expected_validation": {
            "status_liberado": False,
            "exames_faltantes": ["AUDIOMETRIA"],
            "exames_presentes": ["HEMOGRAMA COMPLETO", "GLICOSE", "GAMA GT"]
        }
    }
    # Para adicionar um novo teste:
    # 1. Adicione o PDF na pasta 'test_data'.
    # 2. Use 'scripts/inspect_document.py' para ver o que o OCR extrai.
    # 3. Crie um novo dicionário aqui com os dados do novo cenário.
]

# --- Parametrização do Teste ---
# O pytest executará o teste abaixo uma vez para cada caso em TEST_CASES.
@pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc["test_id"] for tc in TEST_CASES])
@patch('app.services.brmed_service.consultar_exames_brmed') # Mock da consulta externa
def test_full_integration_workflow(mock_brmed, test_case):
    """
    Testa o fluxo de integração completo de forma parametrizada.
    Este teste usa PDFs reais e valida a integração com Docling e a lógica de validação.
    """
    pdf_path = os.path.join(os.path.dirname(__file__), "test_data", test_case["pdf_filename"])
    if not os.path.exists(pdf_path):
        pytest.skip(f"Arquivo de teste não encontrado: {pdf_path}")

    # Moca a extração da IA com os dados esperados para este caso específico
    with (
        patch('app.services.ocr_service.extrair_exames_ia', return_value=test_case["expected_ocr_extraction"]) as mock_exames_ia,
        patch('app.services.ocr_service.extrair_cpf_ia', return_value=test_case["expected_ocr_extraction"]["cpf"]) as mock_cpf_ia,
        patch('app.services.ocr_service.extrair_cpf_regex', return_value=test_case.get("mock_regex_cpf", None)) as mock_regex_cpf,
        patch('app.services.brmed_service.consultar_exames_brmed', return_value=test_case["mock_brmed_exams"]) as mock_brmed
    ):

        # --- 1. Etapa de Processamento Completo ---
        with open(pdf_path, "rb") as f:
            response_full_process = client.post(
                "/v1/processar-documento",
                files={"arquivo": (test_case["pdf_filename"], f, "application/pdf")},
                data={"exames_obrigatorios": json.dumps(test_case["mock_brmed_exams"]["exames"])}
            )

        assert response_full_process.status_code == 200
        full_process_data = response_full_process.json()

        # --- 2. Verificação da Resposta do Workflow ---
        assert full_process_data["status"] == "sucesso"
        assert full_process_data["cpf_processado"] == test_case["expected_ocr_extraction"]["cpf"]
        assert full_process_data["exames_enviados"] == test_case["expected_ocr_extraction"]["exames"]

        validation_data = full_process_data["resultado_validacao"]
        expected_result = test_case["expected_validation"]

        assert validation_data["status_liberado"] == expected_result["status_liberado"]
        # Compara as listas de exames como conjuntos para ignorar a ordem
        assert set(validation_data["exames_faltantes"]) == set(expected_result["exames_faltantes"])
        assert set(validation_data["exames_presentes"]) == set(expected_result["exames_presentes"])

        # Garante que os mocks foram chamados como esperado
        mock_exames_ia.assert_called_once()
        if test_case.get("mock_regex_cpf") is None: # Se o regex foi mocada para falhar, a IA do CPF deve ser chamada
            mock_cpf_ia.assert_called_once()
        else: # Caso contrário, a IA do CPF não deve ser chamada
            mock_cpf_ia.assert_not_called()
        mock_brmed.assert_called_once() # A chamada ao BRMED agora é feita pelo workflow