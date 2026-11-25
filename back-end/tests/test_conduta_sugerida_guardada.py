"""Trilha do ml-exams por documento: cada chamada vira uma linha (resposta ou falha), e abrir de novo com as mesmas
features reaproveita a última resposta sem chamar o POST /prever."""
import httpx
import pytest

from app.services.conduta import conduta_sugerida as cs

MD = "ATESTADO DE SAUDE OCUPACIONAL\nTipo de exame: PERIODICO\nPressao arterial: 120 x 80 mmHg\n"
RESPOSTA = {"versao_modelo": "teste-v1", "versao_features": cs.VERSAO_FEATURES,
            "resultados": [{"caso_id": "x", "prob_encaminhamento": 0.05, "zona": "liberar", "fatores": [],
                            "especialidades": {}, "features_ausentes": 6}]}


class Memoria:
    def __init__(self):
        self.linhas = []

    def ler(self, features_hash):
        ok = [l for l in self.linhas if l["features_hash"] == features_hash and l["resposta"] is not None]
        return ok[-1] if ok else None

    def gravar(self, features_hash, features, versao_modelo, resposta, status_http, erro, duracao_ms, request_id):
        self.linhas.append({"id": len(self.linhas) + 1, "features_hash": features_hash, "versao_modelo": versao_modelo,
                            "resposta": resposta, "status_http": status_http, "erro": erro, "duracao_ms": duracao_ms,
                            "request_id": request_id, "criado_em": "2026-11-25T00:00:00"})
        return len(self.linhas)


@pytest.fixture
def chamadas(monkeypatch):
    feitas = []

    def falso(casos, request_id=None):
        feitas.append(casos)
        return RESPOSTA

    monkeypatch.setattr(cs, "_chamar_modelo", falso)
    return feitas


def test_segunda_abertura_reaproveita_a_resposta(chamadas):
    memoria = Memoria()
    a = cs.sugerir(MD, "2026-11-25", [], [], [], memoria)
    b = cs.sugerir(MD, "2026-11-25", [], [], [], memoria)
    assert len(chamadas) == 1
    assert a["conduta_sugerida"]["situacao_aso"] == b["conduta_sugerida"]["situacao_aso"] == "LIBERADO"
    assert a["sugestao_guardada_em"] is None and b["sugestao_guardada_em"]
    assert a["sugestao_id"] == b["sugestao_id"] == 1
    linha = memoria.linhas[0]
    assert linha["status_http"] == 200 and linha["request_id"] and linha["duracao_ms"] >= 0
    assert linha["resposta"] == RESPOSTA


def test_features_novas_chamam_o_modelo_de_novo(chamadas):
    memoria = Memoria()
    cs.sugerir(MD, "2026-11-25", [], [], [], memoria)
    # Outro pedido no BR NET muda os exames obrigatórios, e com eles as features.
    cs.sugerir(MD, "2026-11-25", [], [], ["AUDIOMETRIA TONAL OCUPACIONAL"], memoria)
    assert len(chamadas) == 2


def test_exame_ausente_vale_mesmo_com_resposta_guardada(chamadas):
    memoria = Memoria()
    cs.sugerir(MD, "2026-11-25", [], [], [], memoria)
    r = cs.sugerir(MD, "2026-11-25", ["AUDIOMETRIA"], [], [], memoria)
    assert len(chamadas) == 1
    assert r["conduta_sugerida"]["situacao_aso"] == "RETIDO"


def test_falha_fica_na_trilha_e_a_proxima_abertura_tenta_de_novo(monkeypatch, chamadas):
    resposta_ok = cs._chamar_modelo

    def caiu(casos, request_id=None):
        raise httpx.ConnectError("fora do ar")

    monkeypatch.setattr(cs, "_chamar_modelo", caiu)
    monkeypatch.setattr(cs, "_saude", lambda: "sem resposta")
    memoria = Memoria()
    r = cs.sugerir(MD, "2026-11-25", [], [], [], memoria)
    assert r["conduta_sugerida"] is None and r["motivo_sem_sugestao"] == "CONFIANCA_BAIXA"
    assert memoria.linhas[0]["resposta"] is None and memoria.linhas[0]["erro"] == "ConnectError"
    monkeypatch.setattr(cs, "_chamar_modelo", resposta_ok)
    r = cs.sugerir(MD, "2026-11-25", [], [], [], memoria)
    assert r["conduta_sugerida"]["situacao_aso"] == "LIBERADO" and len(memoria.linhas) == 2


def test_nada_identificavel_vai_para_o_modelo(chamadas):
    cs.sugerir(MD, "2026-11-25", [], [], [], Memoria())
    enviadas = chamadas[0][0]["features"]
    assert not [k for k in enviadas if cs._nunca_sai(k)]
