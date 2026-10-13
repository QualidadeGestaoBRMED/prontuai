"""Travas da classificação de causa do dashboard (`dashboard_indicadores.sql`).

A consulta não roda aqui — precisa de um Postgres com o schema real. O que se
testa é o TEXTO dela, porque os defeitos que esta classificação já teve foram
todos de redação do CASE, e todos silenciosos: o gráfico continuava somando o
mesmo total, só que atribuído à causa errada.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_classificacao_motivo.py -q --noconftest
"""
import os
import re

import pytest

_SQL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "services", "sql", "dashboard_indicadores.sql",
)


@pytest.fixture(scope="module")
def sql() -> str:
    with open(_SQL_PATH, encoding="utf-8") as arquivo:
        return arquivo.read()


@pytest.fixture(scope="module")
def bloco_motivado(sql: str) -> str:
    """Só a CTE `motivado`, que é onde a causa é decidida."""
    inicio = sql.index("motivado AS (")
    fim = sql.index("acc AS (", inicio)
    return sql[inicio:fim]


def test_ok_nao_vira_causa_de_matching(bloco_motivado: str):
    """"ok" é ausência de motivo, não "IA não reconheceu exame".

    Regressão medida: o regex de `matching_ia` tinha `^ok` e `completo`, e com
    isso 79 divergências do histórico — 8 das 10 da semana de 05/10/2026 —
    apareciam no gráfico como falha de reconhecimento que o revisor nunca
    afirmou. A divergência é real; o motivo é que não se sabe.
    """
    # Só o WHEN que decide `matching_ia`, não o `sem_justificativa` acima dele,
    # que legitimamente cita "tudo ok".
    fim = bloco_motivado.index("THEN 'matching_ia'")
    quando = bloco_motivado.rindex("WHEN j.motivo ~ (", 0, fim)
    matching = bloco_motivado[quando:fim]
    assert "^ok" not in matching
    assert "tudo ok" not in matching
    assert "completo'" not in matching  # "prontuario (completo|esta)" segue valendo
    # e precisa continuar sendo tratado como ausência de causa
    assert re.search(r"\^\(ok\|okay\|okei", bloco_motivado)
    assert bloco_motivado.count("'sem_justificativa'") == 2


def test_exame_nomeado_decide_antes_da_regra_formal(bloco_motivado: str):
    """Rejeição que diz o exame que falta é exame faltante, não regra formal.

    `fcd5eef2` ("faltando eletroencefalograma - aso cortado na lateral") casa
    nos dois lados; quem vier primeiro no CASE vence.
    """
    ramo = bloco_motivado[bloco_motivado.index("humano_status = 'rejected' THEN"):]
    assert ramo.index("falta_exame_nomeado") < ramo.index("'regra_formal'")


def test_palavra_de_falta_sozinha_nao_promove_a_exame(bloco_motivado: str):
    """A palavra "falta" NÃO pode, sozinha, vencer a regra formal.

    Medido: reordenar o CASE por palavra-chave movia 69 linhas de `regra_formal`
    para exame faltante, e 61 delas eram "falta marcação de aptidão" ou "falta
    carimbo" — onde o que falta não é exame nenhum. Por isso o teste de
    proximidade existe, e por isso a regra ampla continua DEPOIS de regra_formal.
    """
    ramo = bloco_motivado[bloco_motivado.index("humano_status = 'rejected' THEN"):]
    regex_ampla = ramo.index("|somente|apenas|nao enviou")
    assert ramo.index("'regra_formal'") < regex_ampla


def test_proximidade_exige_trecho_limpo_de_substantivo_formal(sql: str):
    """"falta: carimbo e assinatura na espirometria" não é exame faltante.

    O nome do exame está a menos de 45 caracteres de "falta", então a janela
    sozinha não basta: o trecho ENTRE as duas tem de estar limpo. Sem esta
    guarda entravam 2 falsos positivos nas 10 linhas que migram.
    """
    # O EXISTS que define a flag: do início do SELECT até o apelido.
    fim = sql.index(") AS falta_exame_nomeado")
    inicio = sql.rindex("EXISTS (", 0, fim)
    definicao = sql[inicio:fim]
    assert "regexp_replace" in definicao
    assert "(carimbo|assinatu|assinal|marcac|aptid|rubrica|data)" in definicao


def test_parecer_medico_nao_conta_como_exame(bloco_motivado: str):
    """"clínica não enviou o parecer médico" casa em `nao enviou` e não é exame.

    Parecer é documento exigido que a IA não verifica — regra formal.
    """
    ramo = bloco_motivado[bloco_motivado.index("humano_status = 'rejected' THEN"):]
    assert ramo.index("~ 'parecer'") < ramo.index("|somente|apenas|nao enviou")


def test_reconhecimento_casa_por_radical(bloco_motivado: str):
    """O revisor escreve "não reconhece", "não reconheu", "não identifou".

    O regex antigo exigia a forma exata ("reconheceu", "identificou") e perdia
    as variantes, que caíam em "Outros motivos".
    """
    assert "nao (reconhe|identif|" in bloco_motivado
    assert "nomecla" in bloco_motivado  # "nomeclatura", sem o segundo N


def test_classificacao_nao_altera_a_acuracia(sql: str):
    """A causa explica a divergência; não decide se houve.

    `acertos` e `base` saem de `ia_status`/`humano_status`/`jeitinho`, nunca de
    `categoria`. Se alguém passar a somar acerto por categoria, mexer na
    redação de um regex passa a mover o número publicado — que foi exatamente o
    risco que esta separação evita.
    """
    bloco_acc = sql[sql.index("acc AS ("):sql.index("acc AS (") + 4000]
    for linha in bloco_acc.splitlines():
        if "categoria" in linha:
            assert "AS mot_" in linha, f"categoria fora de um contador mot_: {linha.strip()}"
