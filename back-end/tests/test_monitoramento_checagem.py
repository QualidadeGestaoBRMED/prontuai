"""Monitoramento silencioso da checagem (`monitoramento_checagem`): o clique no
exame leva ao conteúdo do laudo? o aviso de outra pessoa se confirma no banco?

Rodar sem o conftest: as consultas ao banco são trocadas aqui.
  PYTHONPATH=back-end back-end/.venv/bin/python -m pytest \\
      back-end/tests/test_monitoramento_checagem.py -q --noconftest
"""
from app.services import identidade_laudo, layout_ocr
from app.services import monitoramento_checagem as mc
from app.services.ocr_service import textract_to_markdown
from app.services.workflow_service import _normalizar_busca


def _bb(y):
    return {"Geometry": {"BoundingBox": {"Left": 0.1, "Top": y, "Width": 0.5, "Height": 0.02}}}


def _pagina(*textos):
    return {"Blocks": [{"BlockType": "LINE", "Id": f"l{n}", "Text": t, **_bb(0.05 * (n + 1))} for n, t in enumerate(textos)]}


def _linhas(*paginas):
    partes, posicoes = [], []
    for numero, resposta in enumerate(paginas, start=1):
        partes.append(textract_to_markdown(resposta, pagina=numero))
        posicoes.extend(layout_ocr.linhas_textract(resposta, pagina=numero))
    return layout_ocr.alinhar("\n\n".join(partes), layout_ocr.montar(posicoes))


ASO = _pagina("Procedimentos Realizados", "CLINICO OCUPACIONAL 10/10/2026", "AUDIOMETRIA TONAL 10/10/2026")
FICHA = _pagina("Ficha Médica Periódico", "Anamnese: sem queixas", "Exame físico: sem alterações")
AUDIOGRAMA = _pagina("AVALIAÇÃO AUDIOLÓGICA", "Limiares tonais em dB", "500 1000 2000 4000 Hz")


def _medir(linhas, *exames):
    termos = lambda exame: {_normalizar_busca(exame)}  # noqa: E731
    return mc.medir_clique(linhas, exames, termos, _normalizar_busca)


def test_clique_que_leva_ao_laudo_e_acerto():
    medidas = _medir(_linhas(ASO, FICHA, AUDIOGRAMA), "CLÍNICO OCUPACIONAL", "AUDIOMETRIA TONAL")
    assert medidas == [{"grupo": "clinico", "resultado": "acerto"}, {"grupo": "audiometria", "resultado": "acerto"}]


def test_laudo_no_pdf_que_o_clique_nao_alcanca_e_erro():
    # Ficha sem o título "Ficha Médica": o clique fica no ASO, o laudo está na página 2.
    ficha_sem_titulo = _pagina("Atendimento", "Anamnese: sem queixas", "Exame físico: sem alterações")
    assert _medir(_linhas(ASO, ficha_sem_titulo), "CLÍNICO OCUPACIONAL") == [{"grupo": "clinico", "resultado": "erro"}]


def test_sem_laudo_no_pdf_nao_julga_e_exame_fora_da_regua_nao_e_medido():
    medidas = _medir(_linhas(ASO), "AUDIOMETRIA TONAL", "TOXICOLÓGICO CAPILAR")
    assert medidas == [{"grupo": "audiometria", "resultado": "sem_laudo"}]


def test_sem_layout_nada_e_medido():
    assert _medir([], "CLÍNICO OCUPACIONAL") == [{"grupo": "clinico", "resultado": "sem_laudo"}]


def test_aviso_confirmado_pelo_cpf_pelo_nome_ou_sem_confirmacao():
    pessoas = [
        {"nome": "JOAO FICTICIO SOUZA", "cpf": "11144477735", "tipo": identidade_laudo.NOME_E_CPF},
        {"nome": "CARLOS LIMA ROCHA", "cpf": None, "tipo": identidade_laudo.SO_NOME},
        {"nome": "PEDRO OUTRO DIAS", "cpf": None, "tipo": identidade_laudo.SO_NOME},
    ]
    consultas = []

    def nomes():
        consultas.append(1)
        return ["Carlos Lima Rocha", "MARIA FICTICIA DA SILVA"]

    medidas = mc.confirmar_avisos(pessoas, lambda cpf: cpf == "11144477735", nomes)
    assert [m["confirmacao"] for m in medidas] == ["cpf", "nome", "sem_confirmacao"]
    assert len(consultas) == 1  # a lista de nomes da clínica é lida uma vez só


def test_aviso_forte_confirmado_pelo_cpf_nao_consulta_os_nomes():
    pessoas = [{"nome": "JOAO FICTICIO SOUZA", "cpf": "11144477735", "tipo": identidade_laudo.NOME_E_CPF}]

    def nomes():
        raise AssertionError("não devia consultar")

    assert mc.confirmar_avisos(pessoas, lambda cpf: True, nomes) == [{"tipo": "nome_e_cpf", "confirmacao": "cpf"}]


def test_resumo_so_tem_contagens():
    clique = [{"grupo": "clinico", "resultado": "acerto"}, {"grupo": "clinico", "resultado": "acerto"}]
    avisos = [{"tipo": "so_nome", "confirmacao": "nome"}]
    assert mc.resumo(clique, avisos) == {"clique": {"clinico:acerto": 2}, "avisos": {"so_nome:nome": 1}}
