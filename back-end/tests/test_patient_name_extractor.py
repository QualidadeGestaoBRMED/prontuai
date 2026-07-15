import pytest

from app.services.patient_name_extractor import extract_patient_name_from_markdown


def test_prefers_repeated_correct_name_over_corrupted_bilingual_line():
    markdown = """
Dados do paciente:
Nome BRUNO ALEXANDRE EVORA PIMENTEL Empresa STARNAV SERVIÇOS MAR TIMOS LTDA.
CPF 712.102.062-93

Nome / Name: GR NO ALLXAN ME IVORA EMENTE

1. IDENTIFICAÇÃO DO PACIENTE
NOME: BRUNO ALEXANDRE EVORA PIMENTEL

NOME: BRUNO ALEXANDRE EVORA PIMENTEL
Nome: BRUNO ALEXANDRE EVORA PIMENTEL Empresa: 500359 - CLIMED
"""

    assert (
        extract_patient_name_from_markdown(markdown)
        == "BRUNO ALEXANDRE EVORA PIMENTEL"
    )


def test_uses_bounded_name_without_colon_even_with_one_occurrence():
    markdown = (
        "Dados do paciente:\n"
        "Nome MARIA EDUARDA DA SILVA Empresa ACME SERVIÇOS LTDA.\n"
        "Nascimento 01/01/1990 CPF 123.456.789-00\n"
    )

    assert extract_patient_name_from_markdown(markdown) == "MARIA EDUARDA DA SILVA"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        (
            "Nome / Name: ADRIANA CARDOSO FONSECA Matrícula / Register: 123\n",
            "ADRIANA CARDOSO FONSECA",
        ),
        ("Nome do paciente: José da Silva\n", "José da Silva"),
        ("## Paciente : SAMUEL SILVA CUNHA\n", "SAMUEL SILVA CUNHA"),
        ("## Nome: ANA CLÁUDIA DE ASSIS\n", "ANA CLÁUDIA DE ASSIS"),
    ],
)
def test_supports_existing_name_labels(markdown, expected):
    assert extract_patient_name_from_markdown(markdown) == expected


def test_consensus_normalizes_case_and_accents():
    markdown = """
Nome / Name: OCR INCOMPLETO ERRADO
Nome: João Antônio da Silva
NOME: JOAO ANTONIO DA SILVA
NOME: JOÃO ANTÔNIO DA SILVA
"""

    assert extract_patient_name_from_markdown(markdown) == "João Antônio da Silva"


def test_does_not_treat_nascimento_surname_as_a_trailing_field():
    markdown = """
Nome / Name: ANA RAQUEL SILVA DO NASCIMENTO
Nome: ANA RAQUEL SILVA DO NASCIMENTO
"""

    assert (
        extract_patient_name_from_markdown(markdown)
        == "ANA RAQUEL SILVA DO NASCIMENTO"
    )


def test_strips_birth_field_only_when_followed_by_a_date():
    markdown = "Nome: MARIA JESSICA DO NASCIMENTO Nascimento 01/01/1990\n"

    assert (
        extract_patient_name_from_markdown(markdown)
        == "MARIA JESSICA DO NASCIMENTO"
    )


def test_groups_candidates_that_only_differ_by_word_spacing():
    markdown = """
Nome / Name: JETHER PONTES E SILVA JUNIOR
Nome: JETHER PONTES E SILVAJUNIOR
Nome: JETHER PONTES E SILVAJUNIOR
"""

    assert (
        extract_patient_name_from_markdown(markdown)
        == "JETHER PONTES E SILVA JUNIOR"
    )


def test_does_not_prefer_an_ocr_split_over_a_bilingual_name():
    markdown = """
Nome / Name: LINDEMBERG DA COSTA BERNARDO
Nome LINDEMBERG DA COSTA BERNARDO Empresa ACME LTDA.
Nome: Lindem berg da Costa Bernardo Idade: 38
"""

    assert (
        extract_patient_name_from_markdown(markdown)
        == "LINDEMBERG DA COSTA BERNARDO"
    )


@pytest.mark.parametrize(
    "markdown",
    [
        "",
        "Nome:\nCPF: 123.456.789-00\n",
        "Nome: N/A\n",
        "Nome da empresa: ACME LTDA.\n",
        "Paciente: 123456\n",
    ],
)
def test_rejects_empty_or_non_name_values(markdown):
    assert extract_patient_name_from_markdown(markdown) is None
