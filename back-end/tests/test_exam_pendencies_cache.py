"""
Cache das pendências do catálogo — `app/services/exam_pendencies.py`.

O que está sob teste é **quantas vezes o scan roda**, não o conteúdo da lista
(esse é assunto de `listar_pendencias_catalogo`). A consulta varre `documents`
inteiro parseando `result_payload` como JSONB: 1,65s medidos no dev com 11.188
documentos, e ela rodava duas vezes por carga do painel porque `/stats` e
`/pendencies` a chamavam cada um por si.

Se alguém tirar o cache, ou esquecer de invalidá-lo numa escrita, a tela volta
a ficar lenta — ou pior, passa a mostrar pendência já resolvida.
"""
import pytest

from app.services import exam_pendencies


@pytest.fixture(autouse=True)
def _cache_limpo():
    """Cada teste começa sem cache e não deixa resíduo para o próximo."""
    exam_pendencies.invalidar()
    yield
    exam_pendencies.invalidar()


class _Scan:
    """Conta as chamadas e devolve uma lista do tamanho pedido."""

    def __init__(self, itens=5):
        self.chamadas = 0
        self.limites = []
        self._itens = [f"p{i}" for i in range(itens)]

    def __call__(self, limit):
        self.chamadas += 1
        self.limites.append(limit)
        return self._itens[:limit]


def test_primeira_chamada_executa_o_scan():
    scan = _Scan()
    assert exam_pendencies.obter(scan, limit=3) == ["p0", "p1", "p2"]
    assert scan.chamadas == 1


def test_segunda_chamada_nao_executa_o_scan():
    """É o caso real: `/stats` e `/pendencies` em sequência na mesma carga."""
    scan = _Scan()
    exam_pendencies.obter(scan, limit=10000)
    exam_pendencies.obter(scan, limit=200)
    assert scan.chamadas == 1


def test_limite_menor_sai_do_mesmo_cache():
    """Guardar uma entrada por `limit` recalcularia à toa: a ordem é fixa, então
    o topo de uma lista menor é o mesmo topo da maior."""
    scan = _Scan(itens=5)
    exam_pendencies.obter(scan, limit=10000)
    assert exam_pendencies.obter(scan, limit=2) == ["p0", "p1"]
    assert scan.chamadas == 1


def test_scan_sempre_pede_a_lista_completa():
    """O cache é alimentado com o limite interno, não com o do chamador — senão
    um `/pendencies?limit=5` envenenaria o cache do `/stats`, que conta tudo."""
    scan = _Scan()
    exam_pendencies.obter(scan, limit=5)
    assert scan.limites == [exam_pendencies._LIMITE_INTERNO]


def test_invalidar_forca_novo_scan():
    """Toda escrita no catálogo passa por aqui: cadastrar um pai tira o nome da
    lista, e o painel recarrega logo em seguida."""
    scan = _Scan()
    exam_pendencies.obter(scan, limit=200)
    exam_pendencies.invalidar()
    exam_pendencies.obter(scan, limit=200)
    assert scan.chamadas == 2


def test_cache_vencido_recalcula(monkeypatch):
    """O TTL existe porque a lista também depende de `documents`, que muda sem
    passar por `invalidar()` — exame recém-visto num prontuário precisa sair da
    lista de 'nunca encontrado' sozinho."""
    # O relógio é controlado desde a PRIMEIRA chamada: a validade é gravada com
    # o `monotonic` do momento da gravação, então trocar o relógio depois só
    # adiantaria o ponteiro em relação a uma validade já no futuro distante.
    relogio = [0.0]
    monkeypatch.setattr(exam_pendencies.time, "monotonic", lambda: relogio[0])

    scan = _Scan()
    exam_pendencies.obter(scan, limit=200)

    relogio[0] = exam_pendencies.TTL_SEGUNDOS - 1
    exam_pendencies.obter(scan, limit=200)
    assert scan.chamadas == 1, "dentro do TTL não pode recalcular"

    relogio[0] = exam_pendencies.TTL_SEGUNDOS + 1
    exam_pendencies.obter(scan, limit=200)
    assert scan.chamadas == 2


def test_escrita_no_catalogo_invalida_o_cache():
    """Trava de fiação: `_pos_escrita` é o funil de toda escrita do painel, e é
    lá que a invalidação precisa estar."""
    import inspect

    from app.api.v1 import exams

    fonte = inspect.getsource(exams._pos_escrita)
    assert "exam_pendencies.invalidar()" in fonte
