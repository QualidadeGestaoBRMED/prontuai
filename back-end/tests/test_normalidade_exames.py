"""Normalidade e alteração de exames: leitura do valor no laudo, faixas e rotas.

Os textos imitam o markdown do OCR dos laudos reais (layout e ruído); valores,
nomes e CRMs são fictícios.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_normalidade_exames.py -q --noconftest
"""
import importlib
import re
import sys
import types
from datetime import datetime

import pytest
from starlette.requests import Request

from app.models.normalidade import AjusteFaixa
from app.models.user import User, UserRole
from app.services import layout_ocr, normalidade_exames as ne


def lido(markdown, chave):
    leitura = ne.ler_valores(markdown).get(chave)
    return leitura.valor if leitura and leitura.valor is not None else (leitura.valor_texto if leitura else None)


# ---------------------------------------------------------------------------
# Leitura do valor
# ---------------------------------------------------------------------------

def test_hba1c_no_layout_em_linhas_separadas():
    md = """## HEMOGLOBINA GLICADA

Valor de referência
Hb Alc:
8,9 %
Normal: Menor que 5,7%
Pré-diabetes: 5,7% a 6,4%
Hb Ala:
0,4 %
"""
    assert lido(md, "hba1c") == 8.9


def test_glicose_com_resultado_antes_da_faixa():
    md = """## GLICOSE DE JEJUM

Valor de referência
Resultado:
69 mg/dL
Glicemia em jejum:
Normal
70 a 99 mg/dL
"""
    assert lido(md, "glicemia") == 69


def test_data_da_lista_do_aso_nao_e_resultado():
    md = "## Procedimentos realizados\n## GLICEMIA DE JEJUM 15/10/2026\n## HEMOGRAMA COMPLETO COM PLAQUETAS 15/10/2026\n"
    assert ne.ler_valores(md) == {}


def test_glicemia_estimada_da_hba1c_nao_vira_glicemia():
    md = "## HEMOGLOBINA GLICADA\nHbA1c: 9,1 %\nGlicemia estimada média:\n214 mg/dL\n"
    assert lido(md, "glicemia") is None
    assert lido(md, "hba1c") == 9.1


def test_frase_de_referencia_nao_e_resultado():
    # O OCR quebra a nota do laboratório e deixa "200 mg/dL" sozinho na linha.
    md = "A Diretriz SBD recomenda utilizar a glicemia de jejum maior ou igual a 126\n200 mg/dL. Se somente um exame"
    assert lido(md, "glicemia") is None


def test_fim_de_faixa_nao_e_resultado():
    assert lido("GLICOSE\nValor de referência: 70 a 99 mg/dL\n", "glicemia") is None


def test_hemoglobina_nao_pega_glicada_nem_chcm():
    md = (
        "HEMOGLOBINA GLICADA 6,1 %\n"
        "CONCENTRACAO HEMOGLOBINA C.H.G.M 33,60 G/DL 31,0 A 35,0 G/DL\n"
        "HEMOGLOBINA 14,2 G/DL 13,0 A 17,0 G/DL\n"
    )
    assert lido(md, "hemoglobina") == 14.2


def test_numero_colado_em_unidade_nao_e_resultado():
    # Tabela embaralhada: o "3" de "MILHOES/MM3" vinha seguido do "G/DL".
    md = "HEMOGLOBINA 14,2 4,70 A 6,00 MILHOES/MM3 G/DL HEMATOCRITO 42,8 %"
    assert lido(md, "hemoglobina") is None


def test_plaquetas_formatos():
    assert lido("Plaquetas 148.000 /mm³ 150.000 a 450.000 /mm³", "plaquetas") == 148000
    assert lido("PLAQUETAS 233 MIL/MM3 150 A 450 MIL/MM3", "plaquetas") == 233000
    # "mil" sobrando depois do milhar: o laboratório quis dizer 150.600.
    assert lido("PLAQUETAS 150.600 MIL/MM3 150 A 450 MIL/MM3", "plaquetas") == 150600


def test_plaquetas_nao_pega_crm_nem_ano():
    assert lido("HEMOGRAMA COMPLETO COM PLAQUETAS DRA. FULANA MEDICA CRM 52.0123237-1", "plaquetas") is None
    assert lido("CONTAGEM DE PLAQUETAS FONTES GREER, J. 2003. WINTROBE S CLINICAL", "plaquetas") is None


def test_leucocitos_da_urina_nao_valem():
    md = (
        "SEDIMENTO QUANTITATIVO LEUCOCITOS 57.700 /ML INFERIOR A 25.000 /ML\n"
        "## LEUCOGRAMA\nLEUCOCITOS 6.890 4.000 A 10.000\n"
    )
    assert lido(md, "leucocitos") == 6890


def test_leucocitos_sem_milhar_com_unidade():
    assert lido("LEUCOCITOS 10600 MM 3 4.000 A 12.000 MM 3", "leucocitos") == 10600


def test_valor_impossivel_e_descartado():
    md = "HEMOGLOBINA GLICADA NA MESMA AMOSTRA. BETA LIPOPROTEINA 56,9 38,6A 69.4 %"
    assert lido(md, "hba1c") is None


def test_vdrl_qualitativo():
    assert lido("## VDRL SORO\nValor de referência\nResultado: Positivo 1/4 Negativo", "vdrl") == "Positivo 1/4"
    assert lido("VDRL Valor de referência: Não reagente Resultado: Reagente 1/2", "vdrl") == "Reagente 1/2"
    assert lido("VDRL\nResultado:\nNão reagente", "vdrl") == "Não reagente"


# ---------------------------------------------------------------------------
# Exame do BRNET → parâmetros
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exame,esperado", [
    ("HEMOGRAMA COMPLETO COM PLAQUETAS", ne._HEMOGRAMA),
    ("TRIAGEM TOXICOLÓGICO", ne._TOXICOLOGICO),
    ("EXAME TOXICOLÓGICO DE LARGA JANELA", ne._TOXICOLOGICO),
    ("GLICEMIA DE JEJUM", ("glicemia",)),
    ("GLICOSE", ("glicemia",)),
    ("HEMOGLOBINA GLICADA", ("hba1c",)),
    ("LIPIDOGRAMA (PERFIL LIPÍDICO)", ("colesterol", "hdl", "ldl", "triglic")),
    ("COLESTEROL TOTAL E FRAÇÕES", ("colesterol", "hdl", "ldl", "triglic")),
    ("COLESTEROL HDL", ("hdl",)),
    ("COLESTEROL LDL", ("ldl",)),
    ("COLESTEROL NÃO HDL", ()),
    ("COLESTEROL VLDL", ()),
    ("COLESTEROL TOTAL", ("colesterol",)),
    ("TRIGLICERÍDEOS", ("triglic",)),
    ("CREATININA SÉRICA", ("creatinina",)),
    ("URÉIA", ("ureia",)),
    ("TGO (AST)", ("tgo",)),
    ("TGP (ALT)", ("tgp",)),
    ("GGT (GAMA-GT)", ("ggt",)),
    ("VDRL", ("vdrl",)),
    ("CARBOXI-HEMOGLOBINA", ()),
    ("AUDIOMETRIA TONAL", ()),
    ("CLÍNICO OCUPACIONAL", ()),
])
def test_parametros_do_exame(exame, esperado):
    assert ne.parametros_do_exame(exame) == esperado


# ---------------------------------------------------------------------------
# Avaliação do documento
# ---------------------------------------------------------------------------

LAUDO = """## Procedimentos realizados
## GLICEMIA DE JEJUM 15/10/2026
## HEMOGRAMA COMPLETO COM PLAQUETAS 15/10/2026
## AUDIOMETRIA TONAL 15/10/2026

## GLICOSE DE JEJUM
Resultado: 182 mg/dL   Valor de referência: 70 a 99 mg/dL

## HEMOGRAMA
HEMOGLOBINA 11,2 g/dL 12,0 a 15,5
LEUCOCITOS 6.000 /mm³ 4.000 a 10.000
"""
TABELA = [
    {"exame": "GLICEMIA DE JEJUM", "status": "encontrado"},
    {"exame": "HEMOGRAMA COMPLETO COM PLAQUETAS", "status": "encontrado"},
    {"exame": "AUDIOMETRIA TONAL", "status": "encontrado"},
    {"exame": "CREATININA", "status": "faltante"},
]


def test_avaliar_documento():
    itens = ne.avaliar_documento(LAUDO, TABELA)
    # Audiometria não tem valor; creatinina faltou e não tem laudo para ler.
    assert [i["exame"] for i in itens] == ["GLICEMIA DE JEJUM", "HEMOGRAMA COMPLETO COM PLAQUETAS"]
    glic = itens[0]["parametros"][0]
    assert (glic["valor"], glic["situacao"], glic["referencia"]) == (182, ne.ACIMA, "70 a 99 mg/dL")
    hemo = {p["chave"]: p for p in itens[1]["parametros"]}
    assert hemo["hemoglobina"]["situacao"] == ne.ABAIXO
    assert hemo["leucocitos"]["situacao"] == ne.NORMAL
    assert hemo["plaquetas"]["situacao"] == ne.SEM_RESULTADO


def test_texto_faixa():
    assert ne.texto_faixa("hba1c", ne.FaixaLaudo(None, 5.6)) == "até 5,6 %"
    assert ne.texto_faixa("colesterol", ne.FaixaLaudo(None, 190, True)) == "abaixo de 190 mg/dL"
    assert ne.texto_faixa("plaquetas", ne.FaixaLaudo(150000, 450000)) == "150.000 a 450.000 /mm³"
    assert ne.texto_faixa("glicemia", None) == "faixa não identificada no laudo"
    assert ne.texto_faixa("vdrl", None) == "Não reagente"


# Layout do laboratório que trouxe o caso (DB Diagnósticos, nov/2026): a faixa vem
# depois de repetir o nome do exame, o diferencial traz percentual e contagem com
# uma faixa cada, e o toxicológico é uma substância por linha.
LAUDO_DB = """## GLICOSE DE JEJUM

Valor de referência
Resultado:
89 mg/dL
Glicemia em jejum:
Normal
70 a 99 mg/dL
Diagnóstico de Diabetes Mellitus tipo 2:
Normal Inferior a 100 mg/dL
Pré-diabetes mellitus...: 100 a 125 mg/dL

## HEMOGRAMA COMPLETO

## SÉRIE VERMELHA

Valores de Referência

## ERITRÓCITOS

5,04 milhões/mm³
4,10 a 5,60 milhões/mm³

## HEMOGLOBINA

15,4 g/dL
12,5 a 17,0 g/dL

## VCM

89,9 µm³
80,0 a 99,9 µm³

## HCM

30,5 pg
23,8 a 33,4 pg

## LEUCÓCITOS

7.600 /mm³
3.600 a 12.000 /mm³

## SEGMENTADOS

32 %
2.432 /mm³
40 a 75
1.440 a 9.000 /mm³

## BASÓFILOS

2%
152 /mm³
0 2 %
o a 240 /mm³

## LINFÓCITOS

56 %
4.256 /mm³
20 a 45 %
720 a 5.400 /mm³

## SÉRIE PLAQUETÁRIA

Valor de referência
Plaquetas: 224.000 /mm³
150.000 a 450.000 /mm³

## VPM:

## 9,6 fL

Masculino:
7,4 a 11,4 fL
Feminino:
7,9 a 10,8 fL

Sexo: Masculino

## TRIAGEM TOXICOLÓGICA

Valor de referência
Anfetaminas:
Negativo
Negativo
Cocaína:
Positivo
Negativo
Maconha - Tetrahidrocanabinol: Negativo
Negativo
Metanfetamina:
Negativo
Negativo
"""


def test_faixa_depois_de_repetir_o_nome_do_exame():
    glic = leitura(LAUDO_DB, "glicemia")
    assert (glic.valor, glic.faixa, ne.classificar(glic)) == (89, ne.FaixaLaudo(70, 99), ne.NORMAL)


@pytest.mark.parametrize("chave,valor,faixa,situacao", [
    ("eritrocitos", 5.04, (4.1, 5.6), ne.NORMAL),
    ("hemoglobina", 15.4, (12.5, 17), ne.NORMAL),
    ("vcm", 89.9, (80, 99.9), ne.NORMAL),
    ("hcm", 30.5, (23.8, 33.4), ne.NORMAL),
    ("leucocitos", 7600, (3600, 12000), ne.NORMAL),
    # Percentual e contagem, cada um com a sua faixa, uma depois da outra.
    ("segmentados", 32, (40, 75), ne.ABAIXO),
    ("segmentados_abs", 2432, (1440, 9000), ne.NORMAL),
    ("linfocitos", 56, (20, 45), ne.ACIMA),
    ("linfocitos_abs", 4256, (720, 5400), ne.NORMAL),
    # "0 2 %" sem conector e "o a 240" com a letra no lugar do zero.
    ("basofilos", 2, (0, 2), ne.NORMAL),
    ("basofilos_abs", 152, (0, 240), ne.NORMAL),
    ("plaquetas", 224000, (150000, 450000), ne.NORMAL),
    # Faixa por sexo, com o sexo impresso no laudo.
    ("vpm", 9.6, (7.4, 11.4), ne.NORMAL),
])
def test_hemograma_completo(chave, valor, faixa, situacao):
    lida = leitura(LAUDO_DB, chave)
    assert (lida.valor, (lida.faixa.minimo, lida.faixa.maximo), ne.classificar(lida)) == (valor, faixa, situacao)


def test_hemoglobina_corpuscular_media_nao_e_a_hemoglobina():
    md = "HEMOGLOBINA CORPUSCULAR MEDIA 30,5 pg 26 a 34 pg\nCONCENTRACAO DE HEMOGLOBINA CORPUSCULAR MEDIA 33 g/dL 32 a 36"
    assert lido(md, "hemoglobina") is None
    assert lido(md, "hcm") == 30.5
    assert lido(md, "chcm") == 33


def test_hemacias_do_sedimento_urinario_nao_sao_eritrocitos():
    assert lido("HEMACIAS 3 /campo\nHEMACIAS 5.000 /mL", "eritrocitos") is None


def test_toxicologico_por_substancia():
    leituras = ne.ler_valores(LAUDO_DB)
    # Vale a primeira palavra (o resultado); a segunda é a referência.
    assert leituras["tox_anfetaminas"].valor_texto == "Negativo"
    assert ne.classificar(leituras["tox_cocaina"]) == ne.ALTERADO
    assert leituras["tox_maconha"].valor_texto == "Negativo"
    # "METANFETAMINA" não é lida como anfetamina.
    assert leituras["tox_metanfetamina"].valor_texto == "Negativo"
    assert ne.texto_faixa("tox_cocaina", leituras["tox_cocaina"].faixa) == "Negativo"
    assert lido("Cocaína: Não detectado", "tox_cocaina") == "Não detectado"
    assert ne.classificar(ne.ler_valores("Cocaína: Não detectado")["tox_cocaina"]) == ne.NORMAL


def test_toxicologico_nao_le_resultado_de_outro_campo():
    # Ficha clínica: o "POSITIVO" é do fator RH, longe da palavra "maconha".
    assert lido("Uso de maconha\nTipagem sanguínea A B AB O Fator RH positivo negativo", "tox_maconha") is None
    # Exame de cabelo: "não foi detectado" não é "detectado".
    assert lido("MORFINA 0.2 ng/mg\nResultado final: não foi detectado o uso de substâncias", "tox_morfina") is None
    # Dentro do alcance: "COCAINA E METABOLITOS POSITIVO".
    assert lido("Cocaína e metabólitos Positivo Sem observações", "tox_cocaina") == "Positivo"


def test_faixa_estendida_nao_troca_faixa_ja_lida():
    md = ("COLESTEROL TOTAL Resultado 155 mg/dL Valor de referência com ou sem jejum inferior a 190 mg/dL "
          "Nota: valores de colesterol total iguais ou superiores a 310 mg/dL em adultos")
    assert leitura(md, "colesterol").faixa == ne.FaixaLaudo(None, 190, True)


def test_opcional_so_aparece_quando_lido():
    tabela = [
        {"exame": "HEMOGRAMA COMPLETO", "status": "encontrado"},
        {"exame": "TRIAGEM TOXICOLÓGICO", "status": "encontrado"},
    ]
    hemo, tox = ne.avaliar_documento(LAUDO_DB, tabela)
    chaves = [p["chave"] for p in hemo["parametros"]]
    # Ordem do laudo; o que o laboratório não imprimiu (RDW, monócitos) não aparece.
    assert chaves[:4] == ["eritrocitos", "hemoglobina", "vcm", "hcm"]
    assert "rdw" not in chaves and "monocitos" not in chaves
    assert [p["nome"] for p in tox["parametros"]] == ["Anfetaminas", "Metanfetamina", "Cocaína", "Maconha (THC)"]
    # Hemograma sem nada lido: os três obrigatórios como "Não lido".
    hemo, tox = ne.avaliar_documento("## HEMOGRAMA\n## TRIAGEM TOXICOLOGICA", tabela)
    assert [p["chave"] for p in hemo["parametros"]] == ["hemoglobina", "leucocitos", "plaquetas"]
    # Toxicológico sem substância lida: uma linha "Não lido", não "Não se aplica".
    assert [(p["nome"], p["situacao"]) for p in tox["parametros"]] == [("Resultado", ne.SEM_RESULTADO)]


# ---------------------------------------------------------------------------
# Faixa impressa no laudo. Os textos vêm de formatos vistos na cópia de produção
# de 03/11/2026; valores e nomes são fictícios.
# ---------------------------------------------------------------------------

def leitura(markdown, chave):
    return ne.ler_valores(markdown)[chave]


@pytest.mark.parametrize("markdown,chave,faixa,situacao", [
    ("GLICOSE 88 mg/dL VALOR DE REFERENCIA 60,0 99,0 MG/DL", "glicemia", (60, 99, False), ne.NORMAL),
    ("HEMOGLOBINA 12,7 g/dL 13,0 a 17,5 g/dL", "hemoglobina", (13, 17.5, False), ne.ABAIXO),
    ("PLAQUETAS 148.000 /mm³ 140.000 a 400.000 /mm³", "plaquetas", (140000, 400000, False), ne.NORMAL),
    ("PLAQUETAS 201.000 MIL/MM3 150 A 400 METODO AUTOMACAO", "plaquetas", (150000, 400000, False), ne.NORMAL),
    # O OCR trocou o ponto do milhar por espaço ("3.500" virou "3 500").
    ("LEUCOCITOS GLOBAL 4.800 CELS. /MM3 3 500 A 10.500 CELS/MM3 BASOFILOS 0,0 %", "leucocitos", (3500, 10500, False), ne.NORMAL),
    ("PLAQUETAS 241.000 /MM3 150 000 A 450 000 /MM3", "plaquetas", (150000, 450000, False), ne.NORMAL),
    # Par sem conector continua sendo par, e não um número só.
    ("PLAQUETAS 233.000 MIL/MM 150 450 MPV 13,3", "plaquetas", (150000, 450000, False), ne.NORMAL),
    # O "3" de MM3 não se junta ao número seguinte.
    ("PLAQUETAS 233.000 MIL/MM3 150 A 450 MIL/MM3", "plaquetas", (150000, 450000, False), ne.NORMAL),
    # O laboratório vale mesmo quando difere da faixa mais comum.
    ("PLAQUETAS 487.000 /mm³ 140.000 a 500.000 /mm³", "plaquetas", (140000, 500000, False), ne.NORMAL),
    ("TGP 56 U/L ATE 55 U/L", "tgp", (None, 55, False), ne.ACIMA),
    # "Inferior a 190": o próprio 190 está fora.
    ("COLESTEROL TOTAL 190 mg/dL ADULTOS ACIMA DE 20 ANOS INFERIOR A 190 MG/DL CRIANCAS INFERIOR A 170",
     "colesterol", (None, 190, True), ne.ACIMA),
    # A classe normal vem antes das outras da tabela.
    ("GLICOSE 99 mg/dL VALORES DE REFERENCIA NORMAL INFERIOR A 100 PRE-DIABETIS MELLITUS DE 100 A 125",
     "glicemia", (None, 100, True), ne.NORMAL),
    ("TRIGLICERIDEOS 89 mg/dL ADULTOS ACIMA DE 20 ANOS COM JEJUM INFERIOR A 150 MG/DL SEM JEJUM INFERIOR A 175",
     "triglic", (None, 150, True), ne.NORMAL),
])
def test_faixa_impressa_no_laudo(markdown, chave, faixa, situacao):
    lida = leitura(markdown, chave)
    assert lida.faixa == faixa
    assert ne.classificar(lida) == situacao


@pytest.mark.parametrize("markdown,chave", [
    # Sem faixa nenhuma.
    ("GLICOSE 86 mg/dL", "glicemia"),
    # Hemácias logo depois da hemoglobina: faixa de outro analito.
    ("HEMOGLOBINA 15,30 g/dL 4,50 a 5,50 10 6/L", "hemoglobina"),
    # Só faixa de recém-nascido à vista.
    ("GLICOSE 97 mg/dL CORDAO UMBILICAL 45,0 A 96,0 PREMATURO 20,0 A 60,0", "glicemia"),
    # Idade não é faixa.
    ("TRIGLICERIDEOS 80 mg/dL VALOR DE REFERENCIA CRIANCAS 0 A 9 ANOS < 75MG/DL", "triglic"),
    ("LEUCOCITOS 5.840 /MM3 4 A 120 ANOS 3.600 A 12.000 MM3", "leucocitos"),
    # Homem e mulher sem saber o sexo do paciente.
    ("TGO 18 U/L HOMEM INFERIOR A 35 U/L MULHER INFERIOR A 31 U/L", "tgo"),
    # Zero à esquerda não é milhar: "0 500" é a contagem do basófilo vizinho.
    ("LEUCOCITOS 6.900 /MM3 0 500 /MM3 BASTONETES", "leucocitos"),
    # Duas colunas sem rótulo.
    ("HEMOGLOBINA 12,7 g/dL 13,0 a 17,5 12,0 a 16,0", "hemoglobina"),
    # Meta de tratamento não é faixa de normalidade.
    ("HEMOGLOBINA GLICADA 6,4 % DIAGNOSTICO ACIMA DE 6,5 META TERAPEUTICA MENOR QUE 7,0%", "hba1c"),
    ("HEMOGLOBINA GLICADA 5,9 % PACIENTES DM1 OU DM2 MENOR QUE 7,0%", "hba1c"),
    # Hora da coleta não é faixa.
    ("TGO 50 U/L DATA HORA 06 51 20 RESULTADO 27 U/L", "tgo"),
])
def test_na_duvida_nao_classifica(markdown, chave):
    lida = leitura(markdown, chave)
    assert lida.faixa is None
    assert ne.classificar(lida) == ne.SEM_REFERENCIA


@pytest.mark.parametrize("sexo,faixa,situacao", [("M", (None, 35, True), ne.NORMAL), ("F", (None, 31, True), ne.ACIMA)])
def test_sexo_impresso_escolhe_a_coluna(sexo, faixa, situacao):
    lida = leitura(f"Sexo: {sexo}\nTGO 32 U/L HOMEM INFERIOR A 35 U/L MULHER INFERIOR A 31 U/L", "tgo")
    assert lida.faixa == faixa
    assert ne.classificar(lida) == situacao


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

def usuario(role=UserRole.MANAGER):
    return User(id="gestora", email="gestora@grupobrmed.com.br", name="Gestora", role=role, is_active=True)


def requisicao(metodo="PUT"):
    return Request({
        "type": "http", "method": metodo, "scheme": "http", "server": ("testserver", 80),
        "path": "/v1/normalidade/faixas/glicemia", "raw_path": b"/v1/normalidade/faixas/glicemia",
        "query_string": b"", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 1234),
    })


class BancoFalso:
    def __init__(self):
        self.ajustes = {}
        self.documento = None
        self.layout = None

    def get_document_layout(self, document_id):
        return self.layout

    def list_faixas_normalidade(self):
        return list(self.ajustes.values())

    def upsert_faixa_normalidade(self, parametro, minimo, maximo, atualizado_por_id, atualizado_por_email, atualizado_por_nome):
        self.ajustes[parametro] = AjusteFaixa(
            parametro=parametro, minimo=minimo, maximo=maximo, atualizado_por_email=atualizado_por_email,
            atualizado_por_nome=atualizado_por_nome, atualizado_em=datetime(2026, 10, 26, 18, 0),
        )
        return self.ajustes[parametro]

    def delete_faixa_normalidade(self, parametro):
        return self.ajustes.pop(parametro, None) is not None

    def get_document_by_id(self, document_id):
        return self.documento


def carregar(monkeypatch, banco):
    # Mesmo truque de test_credenciado_abordagem.py: importar o router carrega
    # `app.api` inteiro, que cria um cliente da OpenAI e abre o banco na importação.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.normalidade"):
        sys.modules.pop(nome, None)
    return importlib.import_module("app.api.v1.normalidade")


def test_lista_parametros_sem_faixa_cadastrada(monkeypatch):
    rota = carregar(monkeypatch, BancoFalso())
    lista = {p.parametro: p for p in rota.listar_parametros(current_user=usuario(UserRole.CHECKER))}
    assert lista["glicemia"].unidade == "mg/dL"
    assert lista["vdrl"].qualitativo and lista["vdrl"].normal_texto == "Não reagente"
    # Cadastrar faixa saiu: a rota de ajuste não existe mais.
    assert not hasattr(rota, "ajustar_faixa")


def test_normalidade_do_documento(monkeypatch):
    banco = BancoFalso()
    banco.documento = types.SimpleNamespace(ocr_markdown=LAUDO, result_payload={"tabela_comparacao": TABELA})
    rota = carregar(monkeypatch, banco)
    resposta = rota.normalidade_do_documento("doc-1", current_user=usuario(UserRole.CHECKER))
    assert resposta.habilitada
    assert resposta.itens[0].parametros[0].situacao == "acima"
    assert resposta.itens[0].parametros[0].referencia == "70 a 99 mg/dL"
    assert resposta.itens[1].parametros[0].situacao == "abaixo"


def test_sender_nao_le_normalidade(monkeypatch):
    rota = carregar(monkeypatch, BancoFalso())
    assert UserRole.SENDER not in rota._LEITORES


# ── onde o valor está no PDF ───────────────────────────────────────────────

def _layout_de(markdown, pagina=1):
    """Layout sintético, como o do OCR: uma entrada por linha com conteúdo, uma
    linha a cada 0,02 da página, e cada caractere com 0,01 de largura."""
    linhas = []
    for bruta in markdown.split("\n"):
        texto = bruta.strip()
        if not texto or texto.startswith("<!--"):
            continue
        texto = texto[3:] if texto.startswith("## ") else texto
        palavras = [[100 * m.start(), 100 * len(m.group())] for m in re.finditer(r"\S+", texto)]
        linhas.append([pagina, 0, 200 * len(linhas), 100 * len(texto), 150, palavras])
    return {"versao": 1, "linhas": linhas}


def _caixa(c):
    return tuple(round(c[k], 2) for k in ("x", "y", "w"))


def test_texto_normalizado_por_linha_e_igual_ao_do_documento_inteiro():
    markdown = "<!-- pagina 1 -->\n## GLICEMIA 15/10/2026\n\nResultado: 182 mg/dL\n15/10/2026\nFIM"
    norm, inicios = ne._texto_normalizado(markdown)
    assert norm == re.sub(r" {2,}", " ", ne._DATA.sub(" ", ne.normalizar(markdown))).strip()
    # Cada linha com conteúdo começa onde o índice diz; a de data some.
    assert [norm[a:].split()[0] for a, _ in inicios] == ["<", "GLICEMIA", "RESULTADO", "FIM"]


def test_valor_lido_vem_com_a_posicao_do_valor_e_do_nome():
    linhas = layout_ocr.alinhar(LAUDO, _layout_de(LAUDO))
    glicose, hemograma = ne.avaliar_documento(LAUDO, TABELA, linhas=linhas)
    loc = glicose["parametros"][0]["localizacao"]
    assert loc["pagina"] == 1
    valor, nome = loc["caixas"]
    # "182 mg/dL" na linha "Resultado: 182 mg/dL ...", e o nome no título do laudo
    # (a lista do ASO, sem valor, não conta).
    assert _caixa(valor) == (0.11, 0.10, 0.09)
    assert _caixa(nome) == (0.0, 0.08, 0.16)
    # Valor e nome na mesma linha: "HEMOGLOBINA 11,2 g/dL".
    valor, nome = hemograma["parametros"][0]["localizacao"]["caixas"]
    assert _caixa(valor) == (0.12, 0.14, 0.09)
    assert _caixa(nome) == (0.0, 0.14, 0.11)
    # Contagem com a unidade de contagem: "6.000 /mm³".
    assert _caixa(hemograma["parametros"][1]["localizacao"]["caixas"][0]) == (0.11, 0.16, 0.10)
    # Plaquetas não foi lida: sem valor, sem posição.
    assert hemograma["parametros"][2]["localizacao"] is None


def test_sem_layout_nao_ha_posicao():
    glicose = ne.avaliar_documento(LAUDO, TABELA)[0]["parametros"][0]
    assert glicose["valor"] == 182 and glicose["localizacao"] is None


def test_trecho_na_linha_usa_a_mesma_ocorrencia_da_leitura():
    linha = layout_ocr.LinhaPosicionada("99 Glicose 99mg/dL", 1, (0, 0, 1800, 100))
    assert ne._trecho_na_linha(linha, ["99"], "") == (0, 2)
    # Segunda ocorrência, colada na unidade.
    assert ne._trecho_na_linha(linha, ["99"], "99 GLICOSE") == (11, 18)


def test_trecho_na_linha_nao_confunde_numero_com_data_ou_outro_numero():
    linha = layout_ocr.LinhaPosicionada("22/10/2026 220 22 mg/dL", 1, (0, 0, 2300, 100))
    assert ne._trecho_na_linha(linha, ["22"], "") == (15, 17)


def test_normalidade_do_documento_com_layout(monkeypatch):
    banco = BancoFalso()
    banco.documento = types.SimpleNamespace(ocr_markdown=LAUDO, result_payload={"tabela_comparacao": TABELA})
    banco.layout = _layout_de(LAUDO)
    rota = carregar(monkeypatch, banco)
    resposta = rota.normalidade_do_documento("doc-1", current_user=usuario(UserRole.CHECKER))
    loc = resposta.itens[0].parametros[0].localizacao
    assert loc.pagina == 1 and len(loc.caixas) == 2


# Lipidograma com a faixa por idade (Souza Fidelis, nov/2026): o bloco de adulto
# vem escrito pela idade, longe do valor, e cada exame tem com e sem jejum.
LIPIDOGRAMA = """## COLESTEROL TOTAL

Material: Sangue
Resultado: 132 mg/dL
Valores de Referência:
0 a 2 anos: Não existe valores de referência
estabelecidos para esta faixa etária.
2 a 19 anos:
Com jejum: Inferior a 170 mg/dL
Sem jejum: Inferior a 170 mg/dL
Superior a 19 anos:
Com jejum: Inferior a 190 mg/dL
Sem jejum: Inferior a 190 mg/dL

## COLESTEROL HDL

Resultado: 38 mg/dL
Valor de Referência: Baixo...: : menor que 40 mg/dL
Desejável: maior ou igual a 60 mg/dL
Aceitável: de 41 a 59 mg/dL

## COLESTEROL LDL

Resultado: 135 mg/dL
Valor de Referência: Ótimo.....: : menor que 100 mg/dL
Desejável. de 100 a 129 mg/dL
Limitrofe. : de 130 a 159 mg/dL
Alto......: : de 160 a 189 mg/dL
Triglicérides
Resultado: 160 mg/dL
Valores de Referência:
0 a 9 anos:
Com jejum: Inferior a 75 mg/dL
Sem jejum: Inferior a 85 mg/dL
10 a 19 anos:
Com jejum: Inferior a 90 mg/dL
Sem jejum: Inferior a 100 mg/dL
Superior a 19 anos:
Com jejum: Inferior a 150 mg/dL
Sem jejum: Inferior a 175 mg/dL
"""


@pytest.mark.parametrize("chave,valor,referencia,situacao", [
    ("colesterol", 132, "abaixo de 190 mg/dL", ne.NORMAL),
    # Abaixo do "Baixo: menor que 40"; o "maior ou igual a 60" é a classe de cima.
    ("hdl", 38, "a partir de 40 mg/dL", ne.ABAIXO),
    # Ótimo e desejável vão até 129; 130 em diante é limítrofe.
    ("ldl", 135, "até 129 mg/dL", ne.ACIMA),
    # Com jejum (150), não sem jejum (175).
    ("triglic", 160, "abaixo de 150 mg/dL", ne.ACIMA),
])
def test_lipidograma_com_faixa_por_idade(chave, valor, referencia, situacao):
    lida = leitura(LIPIDOGRAMA, chave)
    assert (lida.valor, ne.texto_faixa(chave, lida.faixa), ne.classificar(lida)) == (valor, referencia, situacao)


def test_faixa_por_idade_sem_bloco_de_adulto_continua_sem_referencia():
    md = "TRIGLICERIDES Resultado: 71 mg/dL Valores de Referência: 0 a 9 anos: Inferior a 75 mg/dL 10 a 19 anos: Inferior a 90 mg/dL"
    assert leitura(md, "triglic").faixa is None


def test_ldl_por_risco_cardiovascular_fica_sem_referencia():
    md = "COLESTEROL LDL 87 mg/dL < 130 < 130 Baixo < 100 < 100 Intermediário < 70 < 70 Alto"
    assert leitura(md, "ldl").faixa is None


def test_hdl_pelo_sexo_do_laudo():
    md = "Sexo: Feminino\nHDL COLESTEROL 42 mg/dL Valor de referência: Homens > 40 mg/dL Mulheres > 45 mg/dL"
    lida = leitura(md, "hdl")
    assert (lida.faixa, ne.classificar(lida)) == (ne.FaixaLaudo(45, None), ne.ABAIXO)


def test_colesterol_nao_hdl_nao_e_o_hdl():
    assert lido("COLESTEROL NAO HDL 154 mg/dL", "hdl") is None


# ---------------------------------------------------------------------------
# Auditoria da tabela de treino da conduta (27/11): textos do OCR em que o
# leitor perdia o resultado ou pegava a referência. Conferidos no PDF.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("md, chave, esperado", [
    # Nome seguido de pontilhado: o ponto solto não é número de faixa.
    ("COLESTEROL TOTAL.\n260 mg/dl", "colesterol", 260),
    ("TRIGLICERIDEOS.\n80 mg/dl", "triglic", 80),
    ("HEMACIAS... 4,72 MILHOES/MM3 4,70 A 6,00 MILHOES/MM3", "eritrocitos", 4.72),
    # "mg/dl" com o l lido como 1.
    ("COLESTEROL HDL.\n65 mg/d1", "hdl", 65),
    # Nome longo das transaminases.
    ("TRANSAMINASE GLUTAMICA OXALACETICA\n26 U/L", "tgo", 26),
    ("TRANSAMINASE GLUTAMICA PIRUVICA\n21 U/L", "tgp", 21),
    # Hífen solto antes do nome.
    ("-COLESTEROL TOTAL.:174 MG/DL", "colesterol", 174),
    ("COLESTEROL -HDL\n42,0 mg/dL", "hdl", 42),
    # HbA1c com o "%" lido como 8, ou sem unidade antes da referência.
    ("Hb A1c:\n4,9 8\nNormal: Menor que 5,7%\nPré-diabetes: 5,7% a 6,4%", "hba1c", 4.9),
    ("Hb Alc:\n4,98\nNormal: Menor que 5,7%", "hba1c", 4.9),
    ("HB A1C 5,4 NORMAL MENOR QUE 5,7% PRE-DIABETES 5,7% A 6,4%", "hba1c", 5.4),
    # Textract: letras trocadas por outro alfabeto e "%" lido como "응".
    ("нь Alc:\n4,8\nNormal: Menor que 5,7%", "hba1c", 4.8),
    ("HBA1C\n:\n4,5\n응", "hba1c", 4.5),
    # Hora da coleta com segundos logo antes do resultado.
    ("GAMA GLUTAMIL TRANSFERASE\nData de recebimento:\n25/07/2025 05:13:28\n8,0 U/L\nHomens até 60,0 U/L", "ggt", 8),
])
def test_auditoria_conduta_resultado_lido(md, chave, esperado):
    assert lido(md, chave) == pytest.approx(esperado)


@pytest.mark.parametrize("md, chave", [
    # Sem o resultado no texto, a referência não vira resultado.
    ("HEMOGLOBINA GLICADA\nNormal: Menor que 5,7%\nPré-diabetes: 5,7% a 6,4%", "hba1c"),
    # "ATÉ" lido como AT6/AID: o limite da referência não é o resultado.
    ("GAMA GLUTAMILTRANSFERASE\nHOMENS AT6 60,0 U/L MULHERES ATE 43,0 U/L", "ggt"),
    ("ALANINA AMINOTRANSFERASE\nMULHERES ATE 31,0 U/L HOMENS AID 41,0 U/L", "tgp"),
    # O hífen colado continua fora.
    ("COLESTEROL NAO-HDL 131 mg/dL", "hdl"),
])
def test_auditoria_conduta_referencia_nao_e_resultado(md, chave):
    assert lido(md, chave) is None


def test_auditoria_conduta_decimal_quebrado_nao_vira_inteiro():
    assert lido("HB A1C . 4 , 7 % VR NORMAL MENOR QUE 5,7%", "hba1c") != 7


@pytest.mark.parametrize("md, chave, esperado", [
    # Nomes da HbA1c do laboratório do RJ e do scanner; "Manor qua" (Menor que) é referência.
    ("HEMOGLOBINA GLICADA\nHb SA1c - Forma estável 8,0 %", "hba1c", 8.0),
    ("HEMOGLOBINA GLICADA\nNormal: Manor qua 5,7%\nHb Ale: 4,8 %\nPre-diabetes: 5,7% a 6,4%", "hba1c", 4.8),
    # Ícone do laudo lido como "0" entre o nome e o resultado.
    ("CREATININA 0 1,11 MG/DL 0,70 A 1,30 MG/DL", "creatinina", 1.11),
    ("GLICOSE 0 95 MG/DL 70 A 99 MG/DL", "glicemia", 95),
])
def test_auditoria_conduta_v23(md, chave, esperado):
    assert lido(md, chave) == pytest.approx(esperado)


def test_zero_de_faixa_continua_referencia():
    # "0 A 5" é faixa, não ícone: o valor de verdade vem depois.
    assert lido("BASTONETES 2 % 0 A 5 %", "bastonetes") == pytest.approx(2)
