"""
Regressão do STC-1052: as regras de identificação de exame saíram do código e
foram para o Catálogo de Exames. Com a carga inicial (migração 019) carregada,
toda função que usava as listas fixas tem de dar EXATAMENTE a mesma saída que
dava antes.

O gabarito `fixtures/regras_identificacao/golden.json` foi gerado com o código
de origin/v1 (listas fixas), sem banco, sobre:

  - 794 nomes de exame reais (os 157 que o BRNET pediu até 04/11 e os 673 do
    catálogo) e alguns nomes no formato do OCR para o marcador de audiometria;
  - 72 trechos de laudo sintéticos (`trechos.json`), cada um exercitando uma
    regra pelo lado positivo ou negativo.

Não regere o gabarito para fazer o teste passar: diferença aqui é mudança de
comportamento da IA, e tem de ser medida (replay) antes de entrar. Mudança de
regra pelo painel não passa por aqui — este teste fixa a carga INICIAL.

Mudanças medidas que entraram na carga depois do STC-1052, com o gabarito
regerado SÓ nos campos que elas afetam, pelo código de referência da v1 com a
mesma mudança (não pelo catálogo, que é o que se testa):

  - 10/11/2026 — avaliação psicológica, odontológica e EEG exigem laudo fora das
    listas do ASO/voucher (`marca_laudo.psicologica`, `.odontologica`, `.eeg`).
    Campos `nomes.*.tipo` e `trechos.*.falta_laudo`. Medição nas notas das regras.
  - 10/11/2026 — RX OIT dado como faltante é recuperado pela folha de leitura OIT
    (`prova_conteudo.rx_oit`). Campo `trechos.*.faltante`.
  - 11/11/2026 — audiograma em gráfico (título AUDIOGRAMA, "LIMIAR OD/OE",
    meatoscopia) passa a ser marca do laudo de audiometria
    (`marca_laudo.audiometria`). Campo `trechos.audiograma_so_frequencias.falta_laudo`.
    Medição nas notas da regra.

Rodar: PYTHONPATH=back-end pytest back-end/tests/test_regras_identificacao_regressao.py -q --noconftest
"""
import json
from pathlib import Path

import pytest

from app.services import (
    evidencia_laboratorio as ev,
    exam_catalog_source,
    identidade_laudo,
    laudo_evidencia as le,
    layout_ocr,
    monitoramento_checagem as mon,
    regras_identificacao,
    validacao_service as vs,
    workflow_service as ws,
)

FIXTURES = Path(__file__).parent / "fixtures" / "regras_identificacao"
GOLDEN = json.loads((FIXTURES / "golden.json").read_text(encoding="utf-8"))
TRECHOS = {t["id"]: t["texto"] for t in json.loads((FIXTURES / "trechos.json").read_text(encoding="utf-8"))["trechos"]}
NOMES = sorted(GOLDEN["nomes"])


@pytest.fixture(autouse=True)
def catalogo_da_carga_inicial(monkeypatch):
    """Regras da carga inicial e catálogo de variações vazio — o mesmo ambiente
    em que o gabarito foi gerado (sem banco)."""
    regras_identificacao.fixar()
    monkeypatch.setattr(exam_catalog_source, "_termos", set())
    monkeypatch.setattr(exam_catalog_source, "_sinonimos", {})
    monkeypatch.setattr(exam_catalog_source, "_pais_ativos", set())
    yield
    regras_identificacao.soltar()


def _brnet() -> list[str]:
    """Os nomes do BRNET usados ao gerar o gabarito dos trechos: os que não são
    sintéticos de OCR nem só do catálogo. Ficam gravados no próprio gabarito."""
    return GOLDEN["brnet"]


# ---------------------------------------------------------------------------
# Por nome de exame
# ---------------------------------------------------------------------------

def _por_nome(nome: str) -> dict:
    nb = ws._normalizar_busca(nome)
    return {
        "tipo": le.tipo_do_exame(nb),
        "lab": ev.eh_laboratorio(nome),
        "termos_lab": sorted(ev.termos_do_exame(nome)),
        "titulos": [t.pattern for t in layout_ocr.titulos_do_exame(nb)],
        "titulos_pad": [t.pattern for t in layout_ocr.titulos_do_exame(f" {nb} ")],
        "regua": mon.grupo_da_regua(nb),
        "aud_ws": ws._match_ocr_exame("AUDIOMETRIA TONAL", [nome], [])["match_type"],
        "aud_vs": vs._match_exame_local("AUDIOMETRIA TONAL", [nome]),
        "aud_filtro": ws._filtrar_exames_ocr([nome], ["AUDIOMETRIA TONAL"], ""),
    }


@pytest.mark.parametrize("campo", ["tipo", "lab", "termos_lab", "titulos", "titulos_pad", "regua",
                                   "aud_ws", "aud_vs", "aud_filtro"])
def test_classificacao_por_nome_igual_a_das_listas_fixas(campo):
    diferentes = {}
    for nome in NOMES:
        atual = _por_nome(nome)[campo]
        esperado = GOLDEN["nomes"][nome][campo]
        if atual != esperado:
            diferentes[nome] = {"antes": esperado, "agora": atual}
    assert not diferentes, f"{len(diferentes)} nomes mudaram em '{campo}': " + json.dumps(
        dict(list(diferentes.items())[:10]), ensure_ascii=False, indent=1
    )


def test_gabarito_cobre_os_nomes_que_importam():
    # Guarda contra gabarito encolhido: se alguém regerar com menos nomes, o
    # teste de cima passa sem provar nada.
    assert len(NOMES) >= 790
    tipos = {v["tipo"] for v in GOLDEN["nomes"].values()}
    # 17 do STC-1052 + psicológica e odontológica (10/11/2026).
    assert len(tipos - {None}) == 19, "os 19 tipos de marca_laudo aparecem no gabarito"
    assert sum(1 for v in GOLDEN["nomes"].values() if v["titulos"]) >= 80
    assert sum(1 for v in GOLDEN["nomes"].values() if v["aud_ws"] == "parcial") >= 15


# ---------------------------------------------------------------------------
# Por trecho de laudo
# ---------------------------------------------------------------------------

def _por_trecho(md: str) -> dict:
    brnet = _brnet()
    md_norm = f" {ws._normalizar_busca(md)} "
    pagina = mon._sem_acento(md)
    r = {
        "faltante": {e: m for e in brnet if (m := le.evidencia_de_faltante(ws._normalizar_busca(e), md_norm))},
        "falta_laudo": {e: m for e in brnet if (m := le.falta_laudo(ws._normalizar_busca(e), md_norm))},
        "filtro": ws._filtrar_exames_ocr([], brnet, md) if md else [],
        "regua": {
            r.parametros["grupo"]: r.vale(pagina)
            for r in regras_identificacao.regras(regras_identificacao.REGUA_MONITORAMENTO)
        },
    }
    comp = [{"exame": e, "status": "encontrado", "justificativa": "x"} for e in brnet]
    ev.anotar_comparativo(comp, md)
    r["lab"] = {i["exame"]: [i.get("evidencia"), i.get("linha_origem")] for i in comp
                if i.get("evidencia") or i.get("linha_origem")}
    linhas_txt = md.split("\n")
    pessoas = [{"chave": f"p{k}", "nome": "FULANO DE TAL TESTE", "cpf": None, "linhas": [i]}
               for k, i in enumerate(i for i, l in enumerate(linhas_txt) if l.strip())]
    identidade_laudo.anotar_comparativo([{"exame": e} for e in brnet], pessoas, linhas_txt,
                                        ws._normalizar_busca, exam_catalog_source.sinonimos_de)
    r["ident"] = [p["exames"] for p in pessoas]
    return r


@pytest.mark.parametrize("trecho", sorted(TRECHOS))
def test_trecho_de_laudo_igual_ao_das_listas_fixas(trecho):
    atual = _por_trecho(TRECHOS[trecho])
    esperado = GOLDEN["trechos"][trecho]
    for campo in ("faltante", "falta_laudo", "filtro", "regua", "lab", "ident"):
        assert atual[campo] == esperado[campo], f"{trecho}.{campo}"


def test_gabarito_dos_trechos_exercita_cada_papel():
    t = GOLDEN["trechos"].values()
    assert sum(1 for v in t if v["faltante"]) >= 8, "prova_conteudo"
    assert sum(1 for v in t if v["falta_laudo"]) >= 50, "marca_laudo"
    assert sum(1 for v in t if v["filtro"]) >= 40, "marcador_texto"
    assert sum(sum(v["regua"].values()) for v in t) >= 15, "regua_monitoramento"
    assert sum(1 for v in t if any(v["ident"])) >= 30, "titulo_identidade/titulo_laudo"
