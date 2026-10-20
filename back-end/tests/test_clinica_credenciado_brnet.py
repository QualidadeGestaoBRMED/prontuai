"""Vínculo da clínica com o credenciado do BRNET (`clinics.brnet_id`, migration 014).

**Por que existe.** Até aqui a clínica não guardava nada do BRNET, e o
dashboard casava credenciado e cadastro pelo nome digitado à mão. O cadastro
passa a escolher o credenciado da rede (`GET /api/rede/credenciada`), e três
regras não podem escapar:

  * sem credenciado, só ADMIN cadastra (contas internas, credenciado fora da
    rede) — o Gestor escolhe da lista;
  * cidade e UF vêm da rede, não do formulário;
  * o vínculo das clínicas antigas casa pelo rótulo inteiro, nunca pelo nome
    curto, que se repete entre unidades de uma mesma rede.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:

    PYTHONPATH=back-end pytest back-end/tests/test_clinica_credenciado_brnet.py -q --noconftest
"""
import asyncio
import importlib
import sys
import types

import pytest
from fastapi import HTTPException

from app.models.clinic import Clinic, ClinicCreate, ClinicUpdate
from app.models.user import User, UserRole
from app.services import rede_credenciada_service as servico
from app.services.rede_credenciada_service import CredenciadoRede, RedeCredenciadaIndisponivel

REDE = [
    CredenciadoRede(identificador="C4071", nome="TRÊS RIOS - RJ - ASO", cidade="TRÊS RIOS", uf="RJ"),
    CredenciadoRede(identificador="C25414", nome="AÇAILÂNDIA - MA - CLINICA PREVEN", cidade="AÇAILÂNDIA", uf="MA"),
    CredenciadoRede(identificador="C1", nome="RECIFE - PE - QUALITY", cidade="RECIFE", uf="PE"),
    CredenciadoRede(identificador="C2", nome="FORTALEZA - CE - QUALITY", cidade="FORTALEZA", uf="CE"),
]


# ── leitura da API ───────────────────────────────────────────────────────────

def test_mapear_rede_descarta_item_incompleto_e_ignora_acento_na_ordem():
    rede = servico.mapear_rede([
        {"identificador": "C30155", "nome": "ACARAU - CE - CLÍNICA DR. FAUSTINO", "cidade": "ACARAU", "UF": "CE",
         "cnpj": "00000000000000", "email": "x@y"},
        {"identificador": "C25414", "nome": "AÇAILÂNDIA - MA - CLINICA PREVEN", "cidade": "AÇAILÂNDIA", "UF": "MA"},
        {"identificador": "", "nome": "SEM ID"},
        {"identificador": "C9", "nome": "  "},
        "lixo",
    ])
    # Sem acento, "ACAILANDIA" vem antes de "ACARAU"; com acento, o Ç ia para o fim.
    assert [c.identificador for c in rede] == ["C25414", "C30155"]
    # CNPJ e e-mail não entram: o CNPJ do credenciado ainda não é adotado.
    assert "cnpj" not in rede[0].model_dump()


def test_resposta_que_nao_e_lista_e_recusada():
    with pytest.raises(ValueError):
        servico.mapear_rede({"detail": "erro"})


def test_cache_e_lista_anterior_quando_a_api_cai(monkeypatch):
    chamadas = []

    async def api_ok():
        chamadas.append("ok")
        return REDE

    async def api_fora():
        chamadas.append("fora")
        raise RedeCredenciadaIndisponivel("timeout")

    relogio = {"t": 1000.0}
    monkeypatch.setattr(servico.time, "monotonic", lambda: relogio["t"])
    monkeypatch.setattr(servico, "_cache", None)

    monkeypatch.setattr(servico, "_buscar_na_api", api_ok)
    assert asyncio.run(servico.listar_rede_credenciada()) == REDE
    relogio["t"] += 60
    assert asyncio.run(servico.listar_rede_credenciada()) == REDE
    assert chamadas == ["ok"]  # dentro da hora, sem nova chamada

    monkeypatch.setattr(servico, "_buscar_na_api", api_fora)
    relogio["t"] += servico.CACHE_TTL_SECONDS
    assert asyncio.run(servico.listar_rede_credenciada()) == REDE  # venceu, API caiu: usa a anterior
    assert chamadas == ["ok", "fora"]

    monkeypatch.setattr(servico, "_cache", None)
    with pytest.raises(RedeCredenciadaIndisponivel):
        asyncio.run(servico.listar_rede_credenciada())


# ── rotas de clínica ─────────────────────────────────────────────────────────

class BancoFalso:
    def __init__(self, clinicas=()):
        self.clinicas = {c.id: c for c in clinicas}
        self.criada = None
        self.atualizada = None

    def get_all_clinics(self, include_inactive=False):
        return [c for c in self.clinicas.values() if include_inactive or c.is_active]

    def get_clinic_by_id(self, cid):
        return self.clinicas.get(cid)

    def create_clinic(self, **kw):
        self.criada = kw
        return Clinic(id="nova", name=kw["name"], city=kw["city"], state=kw["state"], brnet_id=kw["brnet_id"])

    def update_clinic(self, **kw):
        self.atualizada = kw
        return self.clinicas[kw["clinic_id"]]


def carregar(monkeypatch, banco):
    # Mesmo truque de test_multiplos_cargos.py: importar um router carrega
    # `app.api` inteiro, que cria cliente da OpenAI e exige a chave.
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste")
    import app.core.config as config
    for chave, valor in {"APP_ENV": "test", "JWT_SECRET_KEY": "x" * 40, "DEV_AUTH_BYPASS": False}.items():
        monkeypatch.setattr(config.settings, chave, valor, raising=False)
    falso = types.ModuleType("app.core.database")
    falso.user_db = banco
    monkeypatch.setitem(sys.modules, "app.core.database", falso)
    for nome in ("app.core.auth", "app.api.v1.clinics"):
        sys.modules.pop(nome, None)
    mod = importlib.import_module("app.api.v1.clinics")

    async def listar():
        return REDE

    async def buscar(identificador):
        return next((c for c in REDE if c.identificador == identificador.strip().upper()), None)

    monkeypatch.setattr(mod, "listar_rede_credenciada", listar)
    monkeypatch.setattr(mod, "buscar_credenciado", buscar)
    return mod


ADMIN = User(id="a", email="a@grupobrmed.com.br", name="a", roles=[UserRole.ADMIN])
GESTOR = User(id="g", email="g@grupobrmed.com.br", name="g", roles=[UserRole.MANAGER])


def criar(mod, dados, quem):
    return asyncio.run(mod.create_clinic(clinic_data=ClinicCreate(**dados), current_user=quem))


def editar(mod, cid, dados, quem):
    return asyncio.run(mod.update_clinic(clinic_id=cid, clinic_data=ClinicUpdate(**dados), current_user=quem))


def test_gestor_nao_cadastra_sem_credenciado(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        criar(mod, {"name": "Clínica avulsa"}, GESTOR)
    assert exc.value.status_code == 403
    assert banco.criada is None


def test_admin_cadastra_sem_credenciado(monkeypatch):
    """Contas internas ("BR MED Teste") não têm credenciado no BRNET."""
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    criar(mod, {"name": "BR MED Teste"}, ADMIN)
    assert banco.criada["brnet_id"] is None


def test_cidade_e_uf_vem_da_rede_e_nao_do_formulario(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    criar(mod, {"name": "TRÊS RIOS - RJ - ASO", "brnet_id": " C4071 ", "city": "Outra", "state": "SP"}, GESTOR)
    assert banco.criada["brnet_id"] == "C4071"
    assert (banco.criada["city"], banco.criada["state"]) == ("TRÊS RIOS", "RJ")


def test_credenciado_fora_da_rede_e_recusado(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        criar(mod, {"name": "x", "brnet_id": "C999999"}, ADMIN)
    assert exc.value.status_code == 400
    assert banco.criada is None


def test_rede_fora_do_ar_da_503_e_nao_cadastra(monkeypatch):
    banco = BancoFalso()
    mod = carregar(monkeypatch, banco)

    async def fora(_):
        raise RedeCredenciadaIndisponivel("timeout")

    monkeypatch.setattr(mod, "buscar_credenciado", fora)
    with pytest.raises(HTTPException) as exc:
        criar(mod, {"name": "x", "brnet_id": "C4071"}, GESTOR)
    assert exc.value.status_code == 503
    assert banco.criada is None


def test_so_admin_tira_o_vinculo(monkeypatch):
    clinica = Clinic(id="c1", name="TRÊS RIOS - RJ - ASO", brnet_id="C4071")
    banco = BancoFalso([clinica])
    mod = carregar(monkeypatch, banco)
    with pytest.raises(HTTPException) as exc:
        editar(mod, "c1", {"remover_vinculo_brnet": True}, GESTOR)
    assert exc.value.status_code == 403
    editar(mod, "c1", {"remover_vinculo_brnet": True}, ADMIN)
    assert banco.atualizada["remover_vinculo_brnet"] is True


def test_gestor_vincula_clinica_antiga(monkeypatch):
    clinica = Clinic(id="c1", name="Quality Fortaleza")
    banco = BancoFalso([clinica])
    mod = carregar(monkeypatch, banco)
    editar(mod, "c1", {"brnet_id": "C2"}, GESTOR)
    assert banco.atualizada["brnet_id"] == "C2"
    assert (banco.atualizada["city"], banco.atualizada["state"]) == ("FORTALEZA", "CE")


def test_editar_so_o_nome_nao_mexe_no_vinculo(monkeypatch):
    clinica = Clinic(id="c1", name="TRÊS RIOS - RJ - ASO", brnet_id="C4071")
    banco = BancoFalso([clinica])
    mod = carregar(monkeypatch, banco)
    editar(mod, "c1", {"name": "Três Rios ASO"}, GESTOR)
    assert banco.atualizada["brnet_id"] is None
    assert banco.atualizada["remover_vinculo_brnet"] is False


def test_lista_de_credenciados_mostra_as_clinicas_ja_vinculadas(monkeypatch):
    """Enquanto o vínculo não é único, é isso que avisa antes de duplicar."""
    banco = BancoFalso([
        Clinic(id="c1", name="TRÊS RIOS - RJ - ASO", brnet_id="C4071"),
        Clinic(id="c2", name="TRÊS RIOS - RJ - ASO", brnet_id="C4071", is_active=False),
        Clinic(id="c3", name="BR MED Teste"),
    ])
    mod = carregar(monkeypatch, banco)
    opcoes = {o.identificador: o for o in asyncio.run(mod.list_credenciados_brnet(current_user=GESTOR))}
    assert len(opcoes) == len(REDE)
    assert {c.id for c in opcoes["C4071"].clinicas} == {"c1", "c2"}
    assert opcoes["C25414"].clinicas == []


# ── vínculo das clínicas antigas ─────────────────────────────────────────────

def _script():
    caminho = __import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "vincular_clinicas_brnet.py"
    spec = importlib.util.spec_from_file_location("vincular_clinicas_brnet", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_vinculo_antigo_casa_pelo_rotulo_inteiro_e_nunca_pelo_nome_curto():
    planejar = _script().planejar_vinculos
    clinicas = [
        Clinic(id="c1", name="Três Rios - RJ - ASO"),             # caixa e acento diferentes: casa
        Clinic(id="c2", name="TRÊS RIOS – RJ – ASO"),             # travessão: casa
        Clinic(id="c3", name="QUALITY"),                          # nome curto em duas cidades: não casa
        Clinic(id="c4", name="BR MED Teste"),
        Clinic(id="c5", name="AÇAILÂNDIA - MA - CLINICA PREVEN", brnet_id="C25414"),  # já vinculada
    ]
    plano = planejar(clinicas, REDE)
    assert {(c.id, cred.identificador) for c, cred in plano["vincular"]} == {("c1", "C4071"), ("c2", "C4071")}
    assert {c.id for c in plano["sem_par"]} == {"c3", "c4"}
    assert [c.id for c, _ in plano["ja_vinculadas"]] == ["c5"]
    assert set(plano["duplicadas"]) == {"C4071"}
