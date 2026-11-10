"""
Validação das regras de identificação de exame do Catálogo de Exames (STC-1052).

Três frentes:

1. A carga inicial (migração 019) é coerente: compila, chaves únicas, perfis
   existentes, todo papel coberto, exemplos de cada regra acertados, nenhuma
   regra morta (que não casa nenhum exame real), regex sem custo explosivo, e
   o CHECK da migração lista os mesmos papéis que o código.
2. A validação que o painel vai usar recusa regra malformada com motivo claro.
3. O carregamento é seguro: banco fora cai na carga inicial com log de erro,
   linha inválida no banco não derruba as outras, desativada sai, ordem vale, e
   a semeadura só grava na tabela vazia.

Rodar: PYTHONPATH=back-end pytest back-end/tests/test_regras_identificacao_validacao.py -q --noconftest
"""
import copy
import json
import logging
import re
import time
from pathlib import Path

import pytest

from app.services import regras_identificacao as ri

RAIZ = Path(__file__).resolve().parents[1]
SEMENTE = ri.ler_semente()
REGRAS = SEMENTE["regras"]
GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "regras_identificacao" / "golden.json").read_text("utf-8"))


@pytest.fixture(autouse=True)
def _sem_cache():
    ri.soltar()
    yield
    ri.soltar()


def _registro(**muda) -> dict:
    """Uma regra válida (título do clínico) com campos trocados."""
    base = copy.deepcopy(next(r for r in REGRAS if r["chave"] == "titulo_laudo.clinico"))
    base.update(muda)
    return base


# ---------------------------------------------------------------------------
# 1. Carga inicial
# ---------------------------------------------------------------------------

def test_carga_inicial_compila_sem_regra_invalida():
    conjunto = ri.montar(REGRAS, "teste")
    assert conjunto.invalidas == ()
    assert sum(len(v) for v in conjunto.por_papel.values()) == len(REGRAS)


def test_carga_inicial_cobre_todos_os_papeis():
    papeis = {r["papel"] for r in REGRAS}
    assert papeis == set(ri.PAPEIS)


def test_chaves_unicas_e_prefixadas_pelo_papel():
    chaves = [r["chave"] for r in REGRAS]
    assert len(chaves) == len(set(chaves))
    for r in REGRAS:
        assert r["chave"].startswith(r["papel"] + "."), r["chave"]


def test_todo_perfil_usado_existe_e_todo_perfil_existente_e_usado():
    perfis = [p["chave"] for p in SEMENTE["perfis"]]
    assert len(perfis) == len(set(perfis))
    usados = {r["perfil"] for r in REGRAS}
    assert usados == set(perfis)
    for p in SEMENTE["perfis"]:
        assert p["nome"].strip()


def test_ordem_unica_dentro_de_cada_papel():
    # Empate de ordem cai na chave, o que é estável, mas esconde a intenção:
    # na carga inicial cada papel tem a ordem do código antigo, sem empate.
    por_papel: dict[str, list[int]] = {}
    for r in REGRAS:
        por_papel.setdefault(r["papel"], []).append(r["ordem"])
    for papel, ordens in por_papel.items():
        assert len(ordens) == len(set(ordens)), papel


@pytest.mark.parametrize("registro", REGRAS, ids=[r["chave"] for r in REGRAS])
def test_exemplos_de_cada_regra(registro):
    assert ri.conferir_exemplos(registro) == []


@pytest.mark.parametrize("registro", REGRAS, ids=[r["chave"] for r in REGRAS])
def test_toda_regra_tem_exemplo_de_nome(registro):
    assert registro.get("exemplos", {}).get("nome_sim"), "regra sem exemplo não é validada pelo painel"


@pytest.mark.parametrize("registro", REGRAS, ids=[r["chave"] for r in REGRAS])
def test_regra_com_condicao_tem_exemplo_dos_dois_lados(registro):
    if registro.get("condicao") is None:
        pytest.skip("sem condição")
    if registro["papel"] == ri.MARCA_LAUDO and registro["parametros"].get("estrategia") != "marca":
        pytest.skip("estratégia julgada no algoritmo, não só pela regex")
    exemplos = registro.get("exemplos", {})
    assert exemplos.get("texto_sim"), "falta exemplo de texto que vale"
    if registro["papel"] not in (ri.SOROLOGIA_ANALITO,):
        assert exemplos.get("texto_nao"), "falta exemplo de texto que não vale"


def test_nenhuma_regra_morta_nos_nomes_reais():
    """Toda regra casa pelo menos um nome de exame real (BRNET ou catálogo) ou
    um exemplo próprio — regra que não casa nada é engano de curadoria."""
    from app.services import evidencia_laboratorio, workflow_service

    nomes = list(GOLDEN["nomes"])
    mortas = []
    for registro in REGRAS:
        regra = ri.compilar_regra(registro)
        normalizar = (
            evidencia_laboratorio.normalizar
            if registro["papel"] in (ri.LABORATORIO, ri.TERMOS_EXTRAS)
            else workflow_service._normalizar_busca
        )
        if not any(regra.casa_nome(normalizar(n)) for n in nomes):
            mortas.append(registro["chave"])
    assert mortas == [], mortas


def test_regex_sem_custo_explosivo():
    """Todas as condições sobre um texto grande e repetitivo (o pior caso de
    backtracking) em tempo de documento comum."""
    pedaco = "OLHO DIREITO OLHO ESQUERDO 20 GLICOSE MG DL ANTI HBS REAGENTE AUDIOMETR " * 5
    texto = (" " + pedaco + "A" * 2000 + " ") * 40  # ~100 KB
    conjunto = ri.montar(REGRAS, "teste")
    inicio = time.perf_counter()
    for regras in conjunto.por_papel.values():
        for regra in regras:
            regra.vale(texto)
            regra.casa_nome(texto[:5000])
    assert time.perf_counter() - inicio < 5.0


def test_check_da_migracao_lista_os_mesmos_papeis():
    sql = (RAIZ / "migrations" / "019_add_exam_report_rules.sql").read_text("utf-8")
    bloco = re.search(r"CHECK \(role IN \((.*?)\)\)", sql, re.S).group(1)
    assert set(re.findall(r"'([a-z_]+)'", bloco)) == set(ri.PAPEIS)


def test_migracao_019_registrada_no_auto_migrate():
    fonte = (RAIZ / "app" / "core" / "migrations.py").read_text("utf-8")
    assert '"019_add_exam_report_rules.sql"' in fonte
    assert "semear_regras_de_exame()" in fonte


def test_nada_mais_de_exame_fixo_nos_modulos():
    """As listas que saíram não podem voltar por engano."""
    proibidos = {
        "app/services/layout_ocr.py": ["TITULOS_DE_LAUDO =", "FICHA (MEDICA"],
        "app/services/laudo_evidencia.py": ["_TIPOS", "_DROGAS", "_SOROLOGIA_ANALITOS", "OLHO DIREITO", "ERGOMETRI"],
        "app/services/evidencia_laboratorio.py": ["_LABORATORIO =", "_TERMOS_EXTRAS", "HEMOGLOBINA GLICADA"],
        "app/services/monitoramento_checagem.py": ["REGUA_LAUDO", "_FREQUENCIAS", "ANAMNESE"],
        "app/services/identidade_laudo.py": ["_TITULO_ASO", "ATESTADO DE SAUDE OCUPACIONAL"],
        "app/services/workflow_service.py": ["_has_audiometria_marker_text", '"AUDIOMETRIA" in', '" GGT " in'],
        "app/services/validacao_service.py": ["_has_audiometria_marker_text", '"AUDIOMETRIA" in'],
    }
    for arquivo, trechos in proibidos.items():
        fonte = (RAIZ / arquivo).read_text("utf-8")
        for trecho in trechos:
            assert trecho not in fonte, f"{arquivo} voltou a ter '{trecho}'"


# ---------------------------------------------------------------------------
# 2. Validação de regra (a mesma do painel)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "condicao, trecho_do_erro",
    [
        ({"regex": "("}, "regex inválida"),
        ({"regex": ""}, "regex vazia"),
        ({"regex": "A" * (ri.MAX_REGEX + 1)}, "caracteres"),
        ({"todos": []}, "lista vazia"),
        ({"algum": "X"}, "lista vazia"),
        ({"regex": "A", "todos": [{"regex": "B"}]}, "exatamente um operador"),
        ({"contar": [{"regex": "A"}]}, "'minimo'"),
        ({"contar": [{"regex": "A"}], "minimo": 2}, "maior que"),
        ({"contar": [{"regex": "A"}], "minimo": 0}, "'minimo'"),
        ({"contar": [{"regex": "A"}], "minimo": True}, "'minimo'"),
        ({"regex": "A", "minimo": 1}, "só vale com"),
        ({"distintos": "(A|B)", "minimo": 1}, "sem captura"),
        ({"xpto": "A"}, "operador desconhecido"),
        ("A", "esperado objeto"),
        ({"nao": {"nao": {"nao": {"nao": {"nao": {"nao": {"nao": {"regex": "A"}}}}}}}}, "aninhada demais"),
    ],
)
def test_condicao_malformada_e_recusada(condicao, trecho_do_erro):
    with pytest.raises(ri.RegraInvalida, match=re.escape(trecho_do_erro)):
        ri.compilar_condicao(condicao)


@pytest.mark.parametrize(
    "muda, trecho_do_erro",
    [
        ({"chave": ""}, "sem chave"),
        ({"papel": "titulo"}, "papel 'titulo' desconhecido"),
        ({"perfil": " "}, "sem perfil"),
        ({"ordem": "10"}, "ordem tem de ser inteiro"),
        ({"padrao_nome": "("}, "regex inválida"),
        ({"padrao_nome": "X?"}, "casa qualquer nome"),
        ({"parametros": []}, "parametros tem de ser objeto"),
        ({"condicao": {"todos": [{"regex": "A"}]}}, "pede condição {'regex'"),
        ({"condicao": None}, "pede condição {'regex'"),
    ],
)
def test_regra_malformada_e_recusada(muda, trecho_do_erro):
    with pytest.raises(ri.RegraInvalida, match=re.escape(trecho_do_erro)):
        ri.compilar_regra(_registro(**muda))


@pytest.mark.parametrize(
    "papel, condicao, parametros, motivo, trecho_do_erro",
    [
        (ri.PROVA_CONTEUDO, {"regex": "A"}, {}, None, "pede o motivo"),
        (ri.PROVA_CONTEUDO, None, {}, "x", "pede condição"),
        (ri.MARCA_LAUDO, None, {}, None, "pede parametros.tipo"),
        (ri.MARCA_LAUDO, None, {"tipo": "X", "estrategia": "magia"}, None, "estratégia 'magia'"),
        (ri.MARCA_LAUDO, None, {"tipo": "X", "estrategia": "nome_fora_das_listas"}, None, "pede a regex"),
        (ri.MARCA_LAUDO, {"todos": [{"regex": "A"}]}, {"tipo": "X"}, None, "pede condição {'regex'"),
        (ri.MARCA_LAUDO, {"regex": "A"}, {"tipo": "X", "estrategia": "sorologia", "janela": 400}, None,
         "marca_proximidade"),
        (ri.MARCA_LAUDO, {"regex": "A"},
         {"tipo": "X", "estrategia": "sorologia", "marca_proximidade": "R", "janela": 0}, None, "janela"),
        (ri.REGUA_MONITORAMENTO, {"regex": "A"}, {}, None, "parametros.grupo"),
        (ri.MARCADOR_OCR, None, {}, None, "pede condição"),
        (ri.TITULO_IDENTIDADE, None, {"termos": []}, None, "parametros.termos"),
        (ri.TERMOS_EXTRAS, None, {"termos": ["A", " "]}, None, "parametros.termos"),
        (ri.TERMOS_EXTRAS, {"regex": "A"}, {"termos": ["A"]}, None, "não usa condição"),
        (ri.LABORATORIO, {"regex": "A"}, {}, None, "só classifica pelo nome"),
        (ri.SOROLOGIA_ANALITO, None, {}, None, "pede condição {'regex'"),
    ],
)
def test_validacao_por_papel(papel, condicao, parametros, motivo, trecho_do_erro):
    registro = _registro(papel=papel, chave=f"{papel}.x", condicao=condicao, parametros=parametros, motivo=motivo)
    with pytest.raises(ri.RegraInvalida, match=re.escape(trecho_do_erro)):
        ri.compilar_regra(registro)


def test_exemplo_errado_e_apontado():
    registro = _registro(exemplos={"nome_sim": ["AUDIOMETRIA"], "texto_nao": [" FICHA MEDICA "]})
    erros = ri.conferir_exemplos(registro)
    assert len(erros) == 2
    assert "AUDIOMETRIA" in erros[0] and "FICHA MEDICA" in erros[1]


def test_exemplo_com_chave_desconhecida_e_apontado():
    assert "desconhecida" in ri.conferir_exemplos(_registro(exemplos={"nome": ["X"]}))[0]


# ---------------------------------------------------------------------------
# Semântica da condição
# ---------------------------------------------------------------------------

def test_contar_expoe_a_contagem_no_motivo():
    regra = ri.compilar_regra(next(r for r in REGRAS if r["chave"] == "prova_conteudo.toxicologico"))
    vale, ctx = regra.avaliar(" COCAINA NEGATIVO THC NEGATIVO ANFETAMINA OPIACEO METADONA ")
    assert vale and ctx["contagem"] == 5
    assert regra.motivo_formatado(ctx) == "laudos por substância (5 drogas) com resultado"


def test_motivo_sem_contagem_nao_quebra():
    regra = ri.compilar_regra(next(r for r in REGRAS if r["chave"] == "prova_conteudo.toxicologico"))
    assert regra.motivo_formatado({}) == regra.motivo


def test_distintos_conta_textos_diferentes_e_nao_repeticoes():
    avaliar = ri.compilar_condicao({"distintos": r"\b(?:500|1K|2K)\b", "minimo": 2})
    assert not avaliar("500 500 500", {})
    assert avaliar("500 1K", {})


def test_nao_inverte():
    assert ri.compilar_condicao({"nao": {"regex": "X"}})("ABC", {})


def test_marcador_avalia_com_espaco_nas_pontas_e_nunca_casa_vazio():
    regra = ri.compilar_regra(next(r for r in REGRAS if r["chave"] == "marcador_ocr.audiometria"))
    assert ri.marcador(regra, "OD 20 DB")
    assert not regra.vale("OD 20 DB"), "sem o espaço nas pontas ' OD ' não casa no começo"
    assert not ri.marcador(regra, "")


def test_regra_sem_condicao_nunca_vale():
    regra = ri.compilar_regra(next(r for r in REGRAS if r["chave"] == "marca_laudo.hemograma"))
    assert regra.condicao_json is None and not regra.vale("HEMOGRAMA")


# ---------------------------------------------------------------------------
# 3. Carregamento e semeadura
# ---------------------------------------------------------------------------

def test_banco_fora_cai_na_carga_inicial_com_log_de_erro(monkeypatch, caplog):
    def falha():
        raise ConnectionError("sem banco")

    monkeypatch.setattr(ri, "_ler_banco", falha)
    with caplog.at_level(logging.ERROR, logger=ri.__name__):
        conjunto = ri.conjunto()
    assert conjunto.origem == "semente"
    assert len(ri.regras(ri.MARCA_LAUDO)) == 17
    assert "Catálogo de regras indisponível" in caplog.text


def test_tabela_vazia_cai_na_carga_inicial(monkeypatch):
    monkeypatch.setattr(ri, "_ler_banco", lambda: [])
    assert ri.conjunto().origem == "semente"


def test_banco_vence_a_carga_inicial(monkeypatch):
    so_uma = [r for r in REGRAS if r["chave"] == "titulo_laudo.clinico"]
    monkeypatch.setattr(ri, "_ler_banco", lambda: copy.deepcopy(so_uma))
    assert ri.conjunto().origem == "banco"
    assert [r.chave for r in ri.regras(ri.TITULO_LAUDO)] == ["titulo_laudo.clinico"]
    # Papel sem regra no banco fica vazio: desligar é decisão de curadoria.
    assert ri.regras(ri.MARCA_LAUDO) == ()


def test_regra_invalida_no_banco_sai_sozinha(monkeypatch, caplog):
    registros = copy.deepcopy(REGRAS)
    quebrada = next(r for r in registros if r["chave"] == "titulo_laudo.audiometria")
    quebrada["condicao"] = {"regex": "("}
    monkeypatch.setattr(ri, "_ler_banco", lambda: registros)
    with caplog.at_level(logging.ERROR, logger=ri.__name__):
        conjunto = ri.conjunto()
    assert len(conjunto.invalidas) == 1
    chaves = [r.chave for r in ri.regras(ri.TITULO_LAUDO)]
    assert "titulo_laudo.audiometria" not in chaves and "titulo_laudo.clinico" in chaves
    assert "Regra ignorada" in caplog.text


def test_regra_desativada_e_chave_repetida_saem(monkeypatch):
    registros = copy.deepcopy(REGRAS)
    next(r for r in registros if r["chave"] == "titulo_laudo.ecg")["ativo"] = False
    registros.append(copy.deepcopy(next(r for r in REGRAS if r["chave"] == "titulo_laudo.eeg")))
    monkeypatch.setattr(ri, "_ler_banco", lambda: registros)
    chaves = [r.chave for r in ri.regras(ri.TITULO_LAUDO)]
    assert "titulo_laudo.ecg" not in chaves
    assert chaves.count("titulo_laudo.eeg") == 1
    assert any("repetida" in i for i in ri.conjunto().invalidas)


def test_ordem_decide_a_primeira_regra(monkeypatch):
    """RX_OIT antes de RX: trocando a ordem no banco, a classificação muda."""
    registros = copy.deepcopy(REGRAS)
    monkeypatch.setattr(ri, "_ler_banco", lambda: registros)
    assert ri.primeira_do_nome(ri.MARCA_LAUDO, "RADIOGRAFIA DE TORAX OIT").parametros["tipo"] == "RX_OIT"
    next(r for r in registros if r["chave"] == "marca_laudo.rx")["ordem"] = 1
    ri.invalidar()
    assert ri.primeira_do_nome(ri.MARCA_LAUDO, "RADIOGRAFIA DE TORAX OIT").parametros["tipo"] == "RX"


def test_invalidar_rele_o_banco(monkeypatch):
    leituras = []

    def ler():
        leituras.append(1)
        return copy.deepcopy(REGRAS)

    monkeypatch.setattr(ri, "_ler_banco", ler)
    ri.regras(ri.TITULO_LAUDO)
    ri.regras(ri.MARCA_LAUDO)
    assert len(leituras) == 1, "cache por processo"
    ri.invalidar()
    ri.regras(ri.TITULO_LAUDO)
    assert len(leituras) == 2


def test_fixar_isola_o_teste_do_banco(monkeypatch):
    monkeypatch.setattr(ri, "_ler_banco", lambda: pytest.fail("não devia ler o banco"))
    ri.fixar()
    ri.invalidar()  # o painel invalidando no meio do teste não solta a fixação
    assert ri.conjunto().origem == "teste"


def test_papel_desconhecido_levanta():
    with pytest.raises(ValueError):
        ri.regras("titulo")


def test_registros_do_banco_convertem_as_colunas():
    linha = ("k", "perfil", ri.TITULO_LAUDO, 1, "X", {"regex": "Y"}, None, None, None, True)
    (r,) = ri.registros_do_banco([linha])
    assert r["parametros"] == {} and r["exemplos"] == {} and r["ativo"] is True


class _Cursor:
    def __init__(self, banco):
        self.banco = banco
        self._resultado = None

    def execute(self, sql, parametros=None):
        sql = " ".join(sql.split())
        if sql.startswith("SELECT count(*) FROM exam_report_rules"):
            self._resultado = (len(self.banco["regras"]),)
        elif sql.startswith("SELECT id FROM exam_report_profiles"):
            achado = [p for p in self.banco["perfis"] if p[1] == parametros[0]]
            self._resultado = (achado[0][0],) if achado else None
        elif sql.startswith("INSERT INTO exam_report_profiles"):
            self.banco["perfis"].append(parametros)
        elif sql.startswith("INSERT INTO exam_report_rules"):
            self.banco["regras"].append(parametros)
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self._resultado

    def close(self):
        pass


class _Conexao:
    def __init__(self):
        self.banco = {"perfis": [], "regras": []}
        self.commits = 0

    def cursor(self):
        return _Cursor(self.banco)

    def commit(self):
        self.commits += 1


def test_semeadura_grava_tudo_na_tabela_vazia_e_nada_depois():
    conexao = _Conexao()
    assert ri.semear_se_vazio(conexao) == len(REGRAS)
    assert len(conexao.banco["perfis"]) == len(SEMENTE["perfis"])
    assert conexao.commits == 1
    # Linha gravada volta igual pela leitura do banco.
    ids = {p[0]: p[1] for p in conexao.banco["perfis"]}
    linhas = [
        (r[1], ids[r[2]], r[3], r[4], r[5], json.loads(r[6]) if r[6] else None, json.loads(r[7]), r[8],
         json.loads(r[9]), True)
        for r in conexao.banco["regras"]
    ]
    lidas = {r["chave"]: r for r in ri.registros_do_banco(linhas)}
    for original in REGRAS:
        lida = lidas[original["chave"]]
        for campo in ("perfil", "papel", "ordem", "padrao_nome", "condicao", "parametros", "motivo", "exemplos"):
            assert lida[campo] == (original.get(campo) or ({} if campo in ("parametros", "exemplos") else None)), (
                original["chave"], campo)
    # Segunda vez: já há regras, nada é regravado por cima da curadoria.
    assert ri.semear_se_vazio(conexao) == 0
    assert len(conexao.banco["regras"]) == len(REGRAS)


def test_semeadura_recusa_carga_com_regra_invalida():
    semente = copy.deepcopy(SEMENTE)
    semente["regras"][0]["padrao_nome"] = "("
    conexao = _Conexao()
    with pytest.raises(ri.RegraInvalida):
        ri.semear_se_vazio(conexao, semente)
    assert conexao.banco["regras"] == [] and conexao.banco["perfis"] == []


# ---------------------------------------------------------------------------
# O gabarito de regressão detecta mudança de regra
# ---------------------------------------------------------------------------

def test_regressao_detecta_regra_alterada(monkeypatch):
    """Sem isto, um gabarito que não exercita a regra passaria calado."""
    import test_regras_identificacao_regressao as reg

    from app.services import exam_catalog_source

    monkeypatch.setattr(exam_catalog_source, "_termos", set())
    monkeypatch.setattr(exam_catalog_source, "_sinonimos", {})
    monkeypatch.setattr(exam_catalog_source, "_pais_ativos", set())
    for chave, campo, onde in [
        ("titulo_laudo.clinico", "titulos", "nomes"),
        ("marca_laudo.rx_oit", "tipo", "nomes"),
        ("marcador_ocr.audiometria", "aud_ws", "nomes"),
        ("laboratorio.hormonios", "lab", "nomes"),
        ("termos_extras.glicemia", "termos_lab", "nomes"),
        ("regua_monitoramento.ecg", "regua", "nomes"),
    ]:
        ri.fixar([r for r in REGRAS if r["chave"] != chave])
        mudou = any(reg._por_nome(n)[campo] != GOLDEN["nomes"][n][campo] for n in GOLDEN["nomes"])
        assert mudou, f"tirar {chave} não mudou '{campo}' em nenhum nome"
    for chave, campo, trecho in [
        ("prova_conteudo.glicemia", "faltante", "glicose_laudo"),
        ("marca_laudo.ecg", "falta_laudo", "glicose_laudo"),
        ("marcador_texto.ggt", "filtro", "gama_glutamil_solto"),
        ("sorologia_analito.hcv", "falta_laudo", "sorologia_marca_na_lista"),
        ("titulo_identidade.clinico", "ident", "aso_lista"),
    ]:
        ri.fixar([r for r in REGRAS if r["chave"] != chave])
        atual = reg._por_trecho(reg.TRECHOS[trecho])[campo]
        assert atual != GOLDEN["trechos"][trecho][campo], f"tirar {chave} não mudou {trecho}.{campo}"
