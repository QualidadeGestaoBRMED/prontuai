"""Reenvio não conta duas vezes no dashboard.

Desde 06/11/2026 o reenvio vai para a Checagem com a decisão da IA e só a coluna
`reenvio_de` o marca; o status 'reenvio' ficou nos documentos gravados antes
disso. Filtrar só pelo status deixava todo reenvio novo contar de novo em
"Envios realizados" e "Análises realizadas". O documento ajustado depois de uma
rejeição não tem `reenvio_de` e continua contando como outra avaliação.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_dashboard_reenvio.py -q --noconftest
"""
import os
import re

import pytest

_SQL = os.path.join(
    os.path.dirname(__file__), "..", "app", "services", "sql", "dashboard_indicadores.sql"
)
_SERVICE = os.path.join(os.path.dirname(__file__), "..", "app", "services", "dashboard_service.py")


def _sem_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


@pytest.fixture(scope="module")
def sql() -> str:
    with open(_SQL, encoding="utf-8") as f:
        return _sem_comentarios(f.read())


def _bloco(sql: str, cte: str) -> str:
    inicio = sql.index(f"{cte} AS (")
    fim = re.compile(r"\n\),\n").search(sql, inicio).end()
    return sql[inicio:fim]


def test_base_de_utilizacao_tira_o_reenvio_pela_coluna(sql: str):
    doc = _bloco(sql, "doc")
    assert "d.reenvio_de IS NULL" in doc
    # O status continua no filtro: é o que marca os reenvios anteriores a 06/11.
    assert "d.validation_status IS DISTINCT FROM 'reenvio'" in doc


def test_revisao_feita_no_reenvio_conta_para_o_original(sql: str):
    revisado = _bloco(sql, "reenvio_revisado")
    assert "r.reenvio_de AS document_id" in revisado
    assert "JOIN humano" in revisado
    doc = _bloco(sql, "doc")
    assert "LEFT JOIN reenvio_revisado rr ON rr.document_id = d.id" in doc
    assert "rr.document_id IS NOT NULL" in doc


def test_prazos_por_pedido_tiram_o_reenvio_pela_coluna():
    with open(_SERVICE, encoding="utf-8") as f:
        fonte = f.read()
    prazos = fonte[fonte.index("_SQL_PRAZOS = "):]
    prazos = _sem_comentarios(prazos[: prazos.index('"""', prazos.index('"""') + 3)])
    assert "d.reenvio_de IS NULL" in prazos
