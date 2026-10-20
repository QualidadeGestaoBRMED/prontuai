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


# O WHEN de palavras-chave da regra formal. O parecer do modal também leva a
# 'regra_formal', antes dele; os testes de ordem falam deste.
_REGEX_FORMAL = "WHEN j.motivo ~ ('cortad"


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
    assert ramo.index("falta_exame_nomeado") < ramo.index(_REGEX_FORMAL)


def test_palavra_de_falta_sozinha_nao_promove_a_exame(bloco_motivado: str):
    """A palavra "falta" NÃO pode, sozinha, vencer a regra formal.

    Medido: reordenar o CASE por palavra-chave movia 69 linhas de `regra_formal`
    para exame faltante, e 61 delas eram "falta marcação de aptidão" ou "falta
    carimbo" — onde o que falta não é exame nenhum. Por isso o teste de
    proximidade existe, e por isso a regra ampla continua DEPOIS de regra_formal.
    """
    ramo = bloco_motivado[bloco_motivado.index("humano_status = 'rejected' THEN"):]
    regex_ampla = ramo.index("|somente|apenas|nao enviou")
    assert ramo.index(_REGEX_FORMAL) < regex_ampla


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
    """O revisor escreve "não reconhece", "não reconheu", "não identifou",
    "não identuificou".

    O regex antigo exigia a forma exata ("reconheceu", "identificou") e perdia
    as variantes, que caíam em "Outros motivos".
    """
    assert "nao (reconhe|ident|" in bloco_motivado
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


def test_motivo_externo_do_parecer_decide_antes_das_palavras_chave(sql: str):
    """O parecer do modal é a fonte do motivo externo; o texto é o histórico.

    O modal de feedback não pede justificativa para aprovar, então o `motivo`
    lido de `approval_reason` fica vazio justamente no lado em que o motivo
    externo é mais comum (IA rejeita, humano libera — um terço das vezes). Sem a
    leitura do parecer, essas divergências passariam a contar como erro da IA.
    """
    inicio = sql.index("julgamento AS (")
    fim = sql.index("motivado AS (", inicio)
    bloco = sql[inicio:fim]
    caso = bloco[bloco.index("CASE"):bloco.index("END AS jeitinho")]
    parecer = caso.index("WHEN fb.motivo_externo IS NOT NULL THEN true")
    assert parecer < caso.index("WHEN h.humano_status = 'validated' AND motivo ~"), (
        "o parecer tem de vir antes das palavras-chave"
    )
    # LEFT, e não INNER: documento sem parecer continua no julgamento.
    assert "LEFT JOIN document_feedbacks fb ON fb.document_id = d.id" in bloco


def test_parecer_do_modal_decide_antes_do_texto(bloco_motivado: str):
    """No "Errou" de uma liberação o front não grava texto nenhum.

    Lendo só o texto, os 6 pareceres de 19/10/2026 que diziam "estava no
    documento" caíam em "Revisor não informou a causa", justamente quando a
    causa foi dita exame por exame. O parecer vem antes, nos dois ramos.
    """
    rejeitou = bloco_motivado[bloco_motivado.index("humano_status = 'rejected' THEN"):
                              bloco_motivado.index("humano_status = 'validated' THEN")]
    assert rejeitou.index("parecer_nao_estava THEN 'exame_nao_detectado'") < rejeitou.index("'sem_justificativa'")
    assert rejeitou.index("parecer_formal THEN 'regra_formal'") < rejeitou.index("'sem_justificativa'")
    liberou = bloco_motivado[bloco_motivado.index("humano_status = 'validated' THEN"):]
    assert liberou.index("parecer_estava THEN 'matching_ia'") < liberou.index("'sem_justificativa'")


def test_categorias_do_parecer_existem_no_modelo(sql: str):
    """Código digitado errado no SQL some em silêncio: o bool_or só dá falso."""
    from app.models.feedback import CATEGORIAS_DOCUMENTO, CATEGORIAS_EXAME

    inicio = sql.index("julgamento AS (")
    bloco = sql[inicio:sql.index("motivado AS (", inicio)]
    citados = set(re.findall(r"'([A-Z][A-Z_]+)'", bloco))
    assert citados, "a leitura do parecer sumiu do julgamento"
    assert citados <= CATEGORIAS_EXAME | CATEGORIAS_DOCUMENTO, citados - (CATEGORIAS_EXAME | CATEGORIAS_DOCUMENTO)


def test_documento_exigido_pela_empresa_e_regra_formal(bloco_motivado: str):
    """"faltando kit vix" e "faltando aso com o decreto" não são exame da grade.

    Caíam em exame faltante pela palavra de falta. Medido no histórico inteiro:
    a mudança move 19 linhas de categoria, todas conferidas pelo texto.
    """
    ramo = bloco_motivado[bloco_motivado.index("humano_status = 'rejected' THEN"):]
    inicio = ramo.index(_REGEX_FORMAL)
    formal = ramo[inicio:ramo.index("THEN 'regra_formal'", inicio)]
    for termo in ("\\mkit\\M", "decreto", "digitaliz", "\\mnrs?\\M"):
        assert termo in formal, termo
