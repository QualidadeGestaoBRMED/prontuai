"""
Integração da migração 019 com um Postgres de verdade (STC-1052).

Só roda com REGRAS_TEST_DATABASE_URL apontando para um banco DESCARTÁVEL: o
teste cria um schema temporário, aplica 019_add_exam_report_rules.sql, grava a
carga inicial, lê de volta pela mesma consulta do motor e apaga o schema.

    docker exec prontuai-db-dev createdb -U prontuai stc1052_teste
    REGRAS_TEST_DATABASE_URL=postgresql://prontuai:prontuai@localhost:5436/stc1052_teste \\
        PYTHONPATH=back-end pytest back-end/tests/test_regras_identificacao_postgres.py -q --noconftest
"""
import json
import os
import uuid
from pathlib import Path

import pytest

from app.services import regras_identificacao as ri

URL = os.getenv("REGRAS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="REGRAS_TEST_DATABASE_URL não definida")
SQL_019 = (Path(__file__).resolve().parents[1] / "migrations" / "019_add_exam_report_rules.sql").read_text("utf-8")


@pytest.fixture
def conexao():
    import psycopg2

    schema = f"stc1052_{uuid.uuid4().hex[:8]}"
    con = psycopg2.connect(URL)
    with con.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema}")
        cur.execute(f"SET search_path TO {schema}")
    con.commit()
    try:
        yield con
    finally:
        con.rollback()
        with con.cursor() as cur:
            cur.execute(f"DROP SCHEMA {schema} CASCADE")
        con.commit()
        con.close()


def _aplicar_019(con):
    with con.cursor() as cur:
        cur.execute(SQL_019)
    con.commit()


def _ler(con) -> list[dict]:
    with con.cursor() as cur:
        cur.execute(ri.SQL_REGRAS)
        return ri.registros_do_banco(cur.fetchall())


def test_019_e_idempotente(conexao):
    _aplicar_019(conexao)
    _aplicar_019(conexao)


def test_carga_inicial_volta_igual_do_banco(conexao):
    _aplicar_019(conexao)
    assert ri.semear_se_vazio(conexao) == len(ri.ler_semente()["regras"])
    lidas = ri.montar(_ler(conexao), "banco")
    semente = ri.montar(ri.ler_semente()["regras"], "semente")
    assert lidas.invalidas == ()
    for papel in ri.PAPEIS:
        a = [(r.chave, r.ordem, r.nome.pattern, json.dumps(r.condicao_json, sort_keys=True), dict(r.parametros), r.motivo)
             for r in lidas.do_papel(papel)]
        b = [(r.chave, r.ordem, r.nome.pattern, json.dumps(r.condicao_json, sort_keys=True), dict(r.parametros), r.motivo)
             for r in semente.do_papel(papel)]
        assert a == b, papel
    assert ri.semear_se_vazio(conexao) == 0


def test_check_recusa_papel_desconhecido(conexao):
    import psycopg2

    _aplicar_019(conexao)
    ri.semear_se_vazio(conexao)
    with conexao.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO exam_report_rules (id, key, profile_id, role, position, name_pattern) "
            "SELECT 'x', 'x.x', id, 'titulo', 1, 'X' FROM exam_report_profiles LIMIT 1"
        )
    conexao.rollback()


def test_perfil_com_regra_nao_e_apagado(conexao):
    import psycopg2

    _aplicar_019(conexao)
    ri.semear_se_vazio(conexao)
    with conexao.cursor() as cur, pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute("DELETE FROM exam_report_profiles WHERE key = 'audiometria'")
    conexao.rollback()


def test_desativar_perfil_desativa_as_regras_dele(conexao):
    _aplicar_019(conexao)
    ri.semear_se_vazio(conexao)
    with conexao.cursor() as cur:
        cur.execute("UPDATE exam_report_profiles SET is_active = false WHERE key = 'audiometria'")
    conexao.commit()
    conjunto = ri.montar(_ler(conexao), "banco")
    assert all(r.perfil != "audiometria" for papel in ri.PAPEIS for r in conjunto.do_papel(papel))
    assert conjunto.do_papel(ri.TITULO_LAUDO), "os outros perfis continuam"
