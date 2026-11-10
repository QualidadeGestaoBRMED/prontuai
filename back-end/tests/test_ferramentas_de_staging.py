"""Ferramentas só de staging (`app/staging`, STC-981): chaves, fronteira e deploy.

O código dessas ferramentas pode ir para a v1. O que impede que elas ajam em
produção é o que estes testes fixam: as duas chaves de `ativo()`, a fronteira da
pasta e a conferência do deploy de produção.
"""
import pathlib
import re
import subprocess

import pytest

from app import staging
from app.core.config import settings

BACK_END = pathlib.Path(__file__).resolve().parents[1]
RAIZ = BACK_END.parent
CONFERENCIA = RAIZ / "ops" / "deploy" / "conferir_producao_sem_ferramentas_de_staging.sh"

# Únicos pontos do código compartilhado que podem importar `app.staging`. Ponto
# novo entra aqui de propósito, na revisão, e chama `ativo()` antes de agir.
GANCHOS = {
    "app/api/__init__.py",          # monta as rotas (404 fora de staging)
    "app/services/brmed_service.py",  # pedido guardado quando não há expedição aberta
}
_IMPORTA_STAGING = re.compile(r"^\s*(from app\.staging\b|import app\.staging\b|from app import staging\b)", re.M)


# ---------------------------------------------------------------------------
# As duas chaves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ambiente,variavel,esperado",
    [
        ("staging", "true", True),
        ("staging", "TRUE", True),
        ("staging", " true ", True),
        ("staging", None, False),
        ("staging", "", False),
        ("staging", "false", False),
        ("staging", "1", False),
        ("staging", "sim", False),
        ("production", "true", False),
        ("prod", "true", False),
        ("local", "true", False),
        ("test", "true", False),
        ("", "true", False),
    ],
)
def test_ativo_exige_as_duas_chaves(monkeypatch, ambiente, variavel, esperado):
    monkeypatch.setattr(settings, "APP_ENV", ambiente)
    if variavel is None:
        monkeypatch.delenv(staging.VARIAVEL, raising=False)
    else:
        monkeypatch.setenv(staging.VARIAVEL, variavel)
    assert staging.ativo() is esperado


# ---------------------------------------------------------------------------
# Fronteira da pasta
# ---------------------------------------------------------------------------


def test_codigo_compartilhado_so_importa_staging_nos_ganchos():
    importam = set()
    for arquivo in (BACK_END / "app").rglob("*.py"):
        relativo = arquivo.relative_to(BACK_END).as_posix()
        if relativo.startswith("app/staging/"):
            continue
        if _IMPORTA_STAGING.search(arquivo.read_text(encoding="utf-8")):
            importam.add(relativo)
    assert importam == GANCHOS


def test_ferramentas_de_staging_nao_tem_migracao_nem_modelo():
    """Tabela de ferramenta nasce no primeiro uso em staging, nunca no startup."""
    tabelas = set()
    for arquivo in (BACK_END / "app" / "staging").glob("*.py"):
        tabelas |= set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", arquivo.read_text(encoding="utf-8")))
    assert tabelas, "esperava ao menos as tabelas dos pedidos guardados"

    fontes = [BACK_END / "app" / "core" / "db" / "models.py", BACK_END / "app" / "core" / "migrations.py"]
    fontes += sorted((BACK_END / "migrations").glob("*"))
    for fonte in fontes:
        if fonte.is_file():
            texto = fonte.read_text(encoding="utf-8", errors="ignore")
            for tabela in tabelas:
                assert tabela not in texto, f"{tabela} aparece em {fonte.relative_to(RAIZ)}"


# ---------------------------------------------------------------------------
# Composes e conferência do deploy de produção
# ---------------------------------------------------------------------------


def test_so_o_compose_de_staging_tem_a_segunda_chave():
    stg = (BACK_END / "docker-compose.stg.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s*- FERRAMENTAS_DE_STAGING=true\s*$", stg, re.M)

    for nome in ("docker-compose.aws.yml", "docker-compose.yml"):
        caminho = BACK_END / nome
        if caminho.exists():
            assert staging.VARIAVEL not in caminho.read_text(encoding="utf-8"), nome


def _conferir(*args, entrada=""):
    return subprocess.run(
        ["bash", str(CONFERENCIA), *args], input=entrada, capture_output=True, text=True, check=False
    )


def test_conferencia_aceita_o_compose_de_producao_da_arvore():
    resultado = _conferir()
    assert resultado.returncode == 0, resultado.stderr


@pytest.mark.parametrize(
    "linhas",
    [
        '      FERRAMENTAS_DE_STAGING: "true"',
        "      FERRAMENTAS_DE_STAGING: \"false\"",  # a chave nem pode existir em produção
        "      APP_ENV: staging",
        "      APP_ENV: STAGING",
        '      APP_ENV: "staging"',
    ],
)
def test_conferencia_recusa_ambiente_de_producao_com_chave(linhas):
    resultado = _conferir("--config", entrada=f"{linhas}\nCONFERENCIA_OK\n")
    assert resultado.returncode == 1
    assert "Nao pode subir" in resultado.stderr


def test_conferencia_aceita_ambiente_de_producao_limpo():
    resultado = _conferir("--config", entrada="      APP_ENV: production\nCONFERENCIA_OK\n")
    assert resultado.returncode == 0, resultado.stderr
    assert _conferir("--config", entrada="CONFERENCIA_OK\n").returncode == 0


@pytest.mark.parametrize("entrada", ["", "      APP_ENV: production\n"])
def test_conferencia_falha_fechada_sem_confirmacao_do_servidor(entrada):
    """Sem CONFERENCIA_OK o `docker compose config` não rodou: o deploy para."""
    resultado = _conferir("--config", entrada=entrada)
    assert resultado.returncode == 1
    assert "nao rodou" in resultado.stderr
