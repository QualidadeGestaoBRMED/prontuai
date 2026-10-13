"""
Condição da busca das telas de lista — `_filtro_busca_documento`.

**Por que existe.** Histórico, Pendentes e Checagem têm UM campo de busca que
atende a CPF, nome do paciente, nome do arquivo e e-mail de quem enviou. O CPF é
o caso delicado: a coluna guarda só dígitos (`05700231735`) e a tela exibe
formatado (`057.002.317-35`), então o usuário copia da própria tela um valor que
o `ILIKE` cru não encontra.

Isso já foi regressão uma vez: enquanto o Histórico filtrava no cliente, ele
normalizava os dígitos; ao mover a busca para o banco, a normalização ficou para
trás e buscar por CPF formatado passou a não achar nada. O teste trava a volta
disso sem precisar de banco — ele lê a expressão SQL compilada.
"""
import re

import pytest

from app.core.database_postgres import _filtro_busca_documento


def _sql(termo: str) -> str:
    """SQL da condição, com os valores embutidos, para poder inspecionar."""
    return str(
        _filtro_busca_documento(termo).compile(compile_kwargs={"literal_binds": True})
    )


@pytest.mark.parametrize(
    "coluna",
    ["cpf", "filename", "uploaded_by_user_email", "patient_name"],
)
def test_busca_cobre_as_quatro_colunas(coluna):
    """Um campo só atende aos quatro, senão o usuário não acha o que vê na tela."""
    assert coluna in _sql("MARIA")


def test_cpf_formatado_vira_comparacao_por_digitos():
    """`057.002.317-35` precisa achar a linha gravada como `05700231735`."""
    sql = _sql("057.002.317-35")
    assert "regexp_replace" in sql
    # A comparação normalizada usa só os dígitos do termo.
    assert "05700231735" in sql.replace("'", "")


def test_cpf_parcial_tambem_normaliza():
    sql = _sql("057.002")
    assert "regexp_replace" in sql
    assert "057002" in sql.replace("'", "")


def test_termo_sem_digito_nao_gera_comparacao_normalizada():
    """Buscar por nome não deve pagar o `regexp_replace` à toa."""
    assert "regexp_replace" not in _sql("MARIA")


def test_termo_com_digito_no_meio_de_texto_mantem_o_like_original():
    """`ASO 2026.pdf` tem dígitos, mas ainda precisa achar pelo nome do arquivo."""
    sql = _sql("ASO 2026.pdf")
    assert "filename" in sql
    assert "regexp_replace" in sql  # os dígitos também são tentados, de graça
