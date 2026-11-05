"""Alerta de dados de outra pessoa no documento (STC-947).

Os textos imitam o markdown do OCR nos formatos achados na vistoria de 29/10
(bloco "Nome / Name" do ASO, "Dados do colaborador" da espirometria, "Paciente:"
do ECG, "Funcionário:" da acuidade). Nomes e CPFs são fictícios; os CPFs têm
dígito verificador válido.

Rodar sem o conftest, que importa main.py e exige DATABASE_URL:
  PYTHONPATH=back-end back-end/.venv/bin/python -m pytest \
      back-end/tests/test_identidade_laudo.py -q --noconftest
"""
import re
import unicodedata

import pytest

from app.services import identidade_laudo as il
from app.services import workflow_service as ws

PACIENTE = "MARIA FICTICIA DA SILVA"
CPF_PACIENTE = "529.982.247-25"
CPF_OUTRO = "111.444.777-35"
CPF_MEDICO = "390.533.447-05"

ASO_DA_PACIENTE = f"""<!-- pagina 1 -->
## ATESTADO DE SAÚDE OCUPACIONAL
Nome / Name: {PACIENTE}
Identidade / ID Number: 123456
## CPF: {CPF_PACIENTE}
Exames complementares: ELETROCARDIOGRAMA - 10/10/2026
Apto para a função.
"""


def _achar(markdown, cpf=CPF_PACIENTE, nome=PACIENTE):
    return il.outra_pessoa(markdown.splitlines(), cpf, nome)


# ── O que deve acusar ───────────────────────────────────────────────────────

@pytest.mark.parametrize("bloco", [
    # ECG: "Paciente:" e o CPF na linha de baixo.
    f"## DADOS DO PACIENTE\nPaciente: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\nData de Nascimento: 01/01/1990",
    # Espirometria: data de nascimento e RG entre o nome e o CPF.
    f"## DADOS DO COLABORADOR\n## Nome: JOAO FICTICIO SOUZA\nData de Nascimento: 01/01/1990 (36 Anos)\n## RG:\n## CPF: {CPF_OUTRO}",
    # Acuidade visual: "Funcionário:".
    f"## ACUIDADE VISUAL\n## Funcionário: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\nEmpresa: OUTRA EMPRESA LTDA",
    # Nome e CPF na mesma linha.
    f"Paciente: JOAO FICTICIO SOUZA CPF: {CPF_OUTRO}",
    # CPF sem pontuação, com o OCR separando o hífen.
    f"NOME : JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO.replace('-', ' -')}",
])
def test_laudo_de_outra_pessoa_anexado_ao_prontuario(bloco):
    markdown = ASO_DA_PACIENTE + "<!-- pagina 2 -->\n" + bloco
    achados = _achar(markdown)
    assert [(p["nome"], p["cpf"]) for p in achados] == [("JOAO FICTICIO SOUZA", "11144477735")]


def test_as_linhas_do_achado_sao_a_do_nome_e_a_do_cpf_na_ordem_do_documento():
    markdown = ASO_DA_PACIENTE + f"<!-- pagina 2 -->\n## Nome: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}"
    linhas = markdown.splitlines()
    (achado,) = _achar(markdown)
    assert [linhas[i] for i in achado["linhas"]] == ["## Nome: JOAO FICTICIO SOUZA", f"## CPF: {CPF_OUTRO}"]


def test_mesma_pessoa_em_varias_paginas_vira_um_achado_so():
    bloco = f"## Nome: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
    markdown = ASO_DA_PACIENTE + "<!-- pagina 2 -->\n" + bloco + "<!-- pagina 3 -->\n" + bloco
    (achado,) = _achar(markdown)
    assert len(achado["linhas"]) == 4


# ── O que NÃO deve acusar ───────────────────────────────────────────────────

@pytest.mark.parametrize("bloco", [
    # Assinatura digital do laudo, com o CPF do médico.
    f"ASSINADO POR DRA FULANA MEDICA ({CPF_MEDICO}) EM 10/10/2026 10:00:00.",
    # Certificado ICP-Brasil: nome do titular colado no CPF, sem rótulo.
    f"Assinado Digitalmente\nFULANA BORGES MEDICA:{CPF_MEDICO.replace('.', '').replace('-', '')}\nMédico Examinador",
    # Médico ao lado do CRM, mesmo com um "Nome:" do paciente perto.
    f"Paciente: {PACIENTE}\nCRM-RJ 12345\n## CPF: {CPF_MEDICO}\nMédico Examinador",
    # Solicitante.
    f"Solicitante: Dr(a). FULANO MEDICO\n## CPF: {CPF_MEDICO}",
])
def test_cpf_de_profissional_nao_e_outra_pessoa(bloco):
    assert _achar(ASO_DA_PACIENTE + bloco) == []


def test_cpf_sem_nome_rotulado_perto_nao_acusa():
    # O CPF sozinho não diz de quem é (mãe, responsável, médico sem rótulo).
    markdown = ASO_DA_PACIENTE + "\n".join(["Texto do laudo."] * 6) + f"\n## CPF: {CPF_OUTRO}"
    assert _achar(markdown) == []


def test_cpf_diferente_com_o_nome_do_paciente_e_erro_de_ocr_e_nao_outra_pessoa():
    # Mesmo nome, CPF diferente: o OCR trocou dígito, ou o BRNET tem outro CPF.
    markdown = ASO_DA_PACIENTE + f"Paciente: MARlA FICTICIA DA SlLVA\n## CPF: {CPF_OUTRO}"
    assert _achar(markdown) == []


def test_nome_e_cpf_em_paginas_diferentes_nao_formam_bloco():
    markdown = ASO_DA_PACIENTE + f"Nome: JOAO FICTICIO SOUZA\n<!-- pagina 2 -->\n## CPF: {CPF_OUTRO}"
    assert _achar(markdown) == []


def test_rotulo_de_medico_nao_e_rotulo_de_paciente():
    markdown = ASO_DA_PACIENTE + f"Nome do médico: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}"
    assert _achar(markdown) == []


def test_sem_cpf_do_paciente_a_regra_nao_opina():
    markdown = ASO_DA_PACIENTE + f"Paciente: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}"
    assert _achar(markdown, cpf=None) == []
    assert _achar(markdown, cpf="Não encontrado") == []


def test_cpf_invalido_nao_conta():
    markdown = ASO_DA_PACIENTE + "Paciente: JOAO FICTICIO SOUZA\n## CPF: 111.444.777-00"
    assert _achar(markdown) == []


# ── Mesmo nome, com tolerância ao OCR ───────────────────────────────────────

@pytest.mark.parametrize("a, b", [
    ("MARIA FICTICIA DA SILVA", "Maria Fictícia da Silva"),
    ("MARIA FICTICIA DA SILVA", "MARlA FICTlCIA DA SILVA"),     # l no lugar de I
    ("MARIA FICTICIA DA SILVA", "MARIA F. SILVA"),              # abreviado
    ("MARIA FICTICIA DA SILVA", "MARIA FICTICIA SILVAJUNIOR"),  # espaço perdido
    ("JOSE CARLOS SILVA SANTOS", "J0SE CARLOS SILVA SANTOS"),   # primeiro nome corrompido
    ("MARIA FICTICIA DA SILVA", ""),                            # sem como comparar
])
def test_mesma_pessoa(a, b):
    assert il.mesma_pessoa(a, b)


@pytest.mark.parametrize("a, b", [
    ("MARIA FICTICIA DA SILVA", "JOAO FICTICIO SOUZA"),
    ("JOSE DA SILVA SANTOS", "MARIA SILVA SANTOS"),  # só o sobrenome em comum
    ("MARIA FICTICIA DA SILVA", "MARIA SOUZA LIMA"),  # só o primeiro nome
])
def test_pessoas_diferentes(a, b):
    assert not il.mesma_pessoa(a, b)


# ── Payload e checklist ─────────────────────────────────────────────────────

def test_payload_guarda_o_cpf_mascarado_e_a_pagina():
    markdown = ASO_DA_PACIENTE + f"<!-- pagina 2 -->\n## Nome: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}"
    linhas = markdown.splitlines()
    assert il.para_payload(_achar(markdown), linhas) == [{
        "chave": "outra_pessoa:0",
        "nome": "JOAO FICTICIO SOUZA",
        "cpf": "***.***.***-35",
        "tipo": il.NOME_E_CPF,
        "pagina": 2,
        "linhas": ["## Nome: JOAO FICTICIO SOUZA", "## CPF: ***.***.***-35"],
        "exames": [],
    }]


def test_payload_nao_guarda_o_cpf_inteiro_do_terceiro_em_lugar_nenhum():
    import json
    markdown = ASO_DA_PACIENTE + f"<!-- pagina 2 -->\nPaciente: JOAO FICTICIO SOUZA CPF: {CPF_OUTRO}\n"
    payload = json.dumps(il.para_payload(_achar(markdown), markdown.splitlines()))
    assert "11144477735" not in payload and "111.444.777" not in payload


def test_checklist_com_cpf_do_pedido_so_conta_o_cpf_do_paciente():
    markdown = f"Paciente: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\nCRM 1234 CPF {CPF_MEDICO}"
    linhas = ws._extrair_linhas_markdown(markdown)
    campos = {c["field"]: c for c in ws._avaliar_campos(markdown, linhas, PACIENTE, CPF_PACIENTE)}
    assert campos["cpf"]["label"] == "CPF do paciente"
    assert campos["cpf"]["found"] is False
    # Sem o CPF do pedido, a regra antiga: qualquer número com formato de CPF.
    antigos = {c["field"]: c for c in ws._avaliar_campos(markdown, linhas, PACIENTE)}
    assert antigos["cpf"]["label"] == "CPF" and antigos["cpf"]["found"] is True


def test_checklist_acha_o_cpf_do_paciente_com_a_pontuacao_do_ocr():
    markdown = "## CPF: 529.982.247 -25"
    linhas = ws._extrair_linhas_markdown(markdown)
    (cpf,) = [c for c in ws._avaliar_campos(markdown, linhas, None, "52998224725") if c["field"] == "cpf"]
    assert cpf["found"] and cpf["evidence"] == ["## CPF: 529.982.247 -25"]
    assert ws.trecho_do_campo("cpf", "## CPF: 529.982.247 -25", None, "52998224725") == (8, 23)


# ── Em que exame o aviso aparece ────────────────────────────────────────────

def _normalizar(texto):
    # Como `workflow_service._normalizar_busca`: sem acento, maiúsculas, só letras e dígitos.
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[A-Z0-9]+", sem_acento.upper()))


SINONIMOS = {"ELETROCARDIOGRAMA": {"ECG", "ELETROCARDIOGRAMA DE REPOUSO"}}


def _anotar(markdown, exames):
    linhas = markdown.splitlines()
    pessoas = _achar(markdown)
    comparativo = [{"exame": e, "status": "encontrado"} for e in exames]
    il.anotar_comparativo(comparativo, pessoas, linhas, _normalizar, lambda t: SINONIMOS.get(t, set()))
    return comparativo, pessoas


def test_aviso_vai_no_exame_do_titulo_acima_do_bloco():
    markdown = ASO_DA_PACIENTE + (
        f"<!-- pagina 2 -->\n## LAUDO DE ESPIROMETRIA\n## DADOS DO COLABORADOR\n"
        f"## Nome: JOAO FICTICIO SOUZA\nData de Nascimento: 01/01/1990\n## CPF: {CPF_OUTRO}\n"
        "## DADOS DA EMPRESA\n"
    )
    comparativo, (pessoa,) = _anotar(markdown, ["ESPIROMETRIA", "ELETROCARDIOGRAMA"])
    assert comparativo[0]["outra_pessoa"] == [
        {"chave": "outra_pessoa:0", "nome": "JOAO FICTICIO SOUZA", "cpf": "***.***.***-35", "pagina": 2,
         "tipo": il.NOME_E_CPF}
    ]
    assert "outra_pessoa" not in comparativo[1]
    assert pessoa["exames"] == ["ESPIROMETRIA"]
    # Status e justificativa ficam como estão: é só aviso.
    assert comparativo[0]["status"] == "encontrado" and "justificativa" not in comparativo[0]


def test_aviso_vai_no_exame_do_titulo_abaixo_do_bloco_pelo_sinonimo():
    # Fast Laudos: identificação primeiro, o nome do exame logo depois.
    markdown = ASO_DA_PACIENTE + (
        f"<!-- pagina 2 -->\n## DADOS DO PACIENTE\n## Nome: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
        "Sexo: Masculino\nLaudo Eletrocardiograma de Repouso (ECG)\nRitmo sinusal\n"
    )
    comparativo, _ = _anotar(markdown, ["ESPIROMETRIA", "ELETROCARDIOGRAMA"])
    assert [("outra_pessoa" in item) for item in comparativo] == [False, True]


def test_aso_de_outra_pessoa_vai_no_clinico():
    markdown = ASO_DA_PACIENTE + (
        f"<!-- pagina 2 -->\nAtestado de Saúde Ocupacional\nEMPRESA FICTICIA LTDA\n"
        f"Nome / Name: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\nFunção: AJUDANTE\n"
    )
    comparativo, _ = _anotar(markdown, ["CLÍNICO OCUPACIONAL", "ESPIROMETRIA"])
    assert [item["exame"] for item in comparativo if "outra_pessoa" in item] == ["CLÍNICO OCUPACIONAL"]


def test_empate_fica_com_o_titulo_de_cima():
    markdown = ASO_DA_PACIENTE + (
        f"<!-- pagina 2 -->\n## ESPIROMETRIA\n## Nome: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n## ELETROCARDIOGRAMA\n"
    )
    comparativo, _ = _anotar(markdown, ["ELETROCARDIOGRAMA", "ESPIROMETRIA"])
    assert [item["exame"] for item in comparativo if "outra_pessoa" in item] == ["ESPIROMETRIA"]


def test_titulo_em_outra_pagina_ou_fora_da_tabela_deixa_a_pessoa_sem_exame():
    markdown = ASO_DA_PACIENTE + (
        f"## ESPIROMETRIA\n<!-- pagina 2 -->\n## AVALIAÇÃO AUDIOLÓGICA\n"
        f"## Funcionário: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
    )
    comparativo, (pessoa,) = _anotar(markdown, ["ESPIROMETRIA", "AUDIOMETRIA TONAL"])
    assert not any("outra_pessoa" in item for item in comparativo)
    assert pessoa["exames"] == []
    assert il.para_payload([pessoa], markdown.splitlines())[0]["exames"] == []


def test_mesma_pessoa_em_dois_laudos_avisa_nos_dois_exames():
    bloco = f"## Nome: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
    markdown = ASO_DA_PACIENTE + (
        "<!-- pagina 2 -->\n## ESPIROMETRIA\n" + bloco + "<!-- pagina 3 -->\n## ELETROCARDIOGRAMA\n" + bloco
    )
    comparativo, (pessoa,) = _anotar(markdown, ["ESPIROMETRIA", "ELETROCARDIOGRAMA"])
    assert pessoa["exames"] == ["ESPIROMETRIA", "ELETROCARDIOGRAMA"]
    assert [item["outra_pessoa"][0]["pagina"] for item in comparativo] == [2, 3]


# ── Aviso só pelo nome ──────────────────────────────────────────────────────

# Vocabulário de nomes fictício: no app vem de `nomes_conhecidos.vocabulario()`.
NOMES = {"MARIA", "SILVA", "JOAO", "FICTICIO", "SOUZA", "PEDRO", "OUTRO", "LIMA", "CARLOS", "ROCHA"}


def _pessoas(markdown, cpf=CPF_PACIENTE, nome=PACIENTE, nomes=NOMES):
    return il.pessoas_no_documento(markdown.splitlines(), cpf, nome, nomes_conhecidos=nomes)


def test_nome_diferente_sem_cpf_vira_aviso_so_pelo_nome():
    markdown = ASO_DA_PACIENTE + "<!-- pagina 2 -->\n## AVALIAÇÃO ODONTOLÓGICA\nPaciente: CARLOS LIMA ROCHA\nIdade: 30\n"
    (pessoa,) = _pessoas(markdown)
    assert (pessoa["nome"], pessoa["cpf"], pessoa["tipo"]) == ("CARLOS LIMA ROCHA", None, il.SO_NOME)
    assert pessoa["chave"] == "outra_pessoa:0"


def test_nome_e_cpf_continua_aviso_forte_e_vem_primeiro():
    markdown = ASO_DA_PACIENTE + (
        f"<!-- pagina 2 -->\nPaciente: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
        "<!-- pagina 3 -->\nNome: PEDRO OUTRO LIMA\n"
    )
    assert [(p["nome"], p["tipo"]) for p in _pessoas(markdown)] == [
        ("JOAO FICTICIO SOUZA", il.NOME_E_CPF),
        ("PEDRO OUTRO LIMA", il.SO_NOME),
    ]


def test_mesma_outra_pessoa_num_laudo_sem_cpf_entra_no_aviso_forte():
    markdown = ASO_DA_PACIENTE + (
        f"<!-- pagina 2 -->\nPaciente: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
        "<!-- pagina 3 -->\nNome: JOAO FICTlCIO SOUZA\n"
    )
    (pessoa,) = _pessoas(markdown)
    assert pessoa["tipo"] == il.NOME_E_CPF and len(pessoa["linhas"]) == 3


@pytest.mark.parametrize("linha", [
    "Paciente: MARlA FICTICIA DA SlLVA",       # o paciente, com erro de OCR
    "Nome do médico: JOAO FICTICIO SOUZA",      # rótulo de profissional
    "Nome: JOAO",                               # uma palavra só
    "Responsável técnico: JOAO FICTICIO SOUZA",  # não é rótulo de paciente
])
def test_o_que_nao_vira_aviso_so_pelo_nome(linha):
    assert _pessoas(ASO_DA_PACIENTE + linha) == []


def test_aviso_so_pelo_nome_nao_precisa_do_cpf_do_paciente():
    markdown = ASO_DA_PACIENTE + "Paciente: CARLOS LIMA ROCHA\n"
    assert [p["tipo"] for p in _pessoas(markdown, cpf=None)] == [il.SO_NOME]
    assert _pessoas(markdown, nome=None) == []


def test_sem_vocabulario_de_nomes_nao_ha_aviso_so_pelo_nome():
    # Banco fora: preferir não avisar a avisar ruído. O aviso forte não depende dele.
    markdown = ASO_DA_PACIENTE + "Paciente: JOAO FICTICIO SOUZA\n"
    assert _pessoas(markdown, nomes=frozenset()) == []
    assert _pessoas(markdown, nomes=None) == []


@pytest.mark.parametrize("bloco", [
    # 1. Grafia parecida: o próprio paciente com o nome manuscrito estragado.
    "Paciente: Marta Fictacia da Sirva Rocha",
    # 2. Conselho logo abaixo: é a profissional que assina.
    "Nome: CARLOS LIMA ROCHA\nFonoaudióloga\nCRFa: 1-2345",
    # 3. Formulário de custódia do toxicológico: é o coletor.
    "ESPAÇO RESERVADO PARA O SUPERVISOR DA COLETA\nNome: CARLOS LIMA ROCHA",
    # 4. Palavra em minúscula: o OCR inventando.
    "Nome: carlos lima rocha",
    # 5. Nome cortado.
    "Nome: CARLOS LIMA DE RO",
    # 6. Empresa no lugar do nome.
    "Nome: ROCHA SERVICOS LTDA",
    # 7. Palavras fora do vocabulário de nomes: o OCR inventando com maiúsculas.
    "Nome: Quelgo Varnip Trusda",
])
def test_cortes_do_aviso_so_pelo_nome(bloco):
    assert _pessoas(ASO_DA_PACIENTE + "<!-- pagina 2 -->\n" + bloco + "\n") == []


def test_metade_das_palavras_conhecidas_basta():
    # Sobrenome raro ("ZANFRUQ") não derruba um nome que é de gente.
    (pessoa,) = _pessoas(ASO_DA_PACIENTE + "Paciente: CARLOS ZANFRUQ\n")
    assert pessoa["tipo"] == il.SO_NOME


def test_aviso_so_pelo_nome_vai_no_exame_e_no_payload_sem_cpf():
    markdown = ASO_DA_PACIENTE + "<!-- pagina 2 -->\n## ESPIROMETRIA\nNome: CARLOS LIMA ROCHA\n"
    linhas = markdown.splitlines()
    pessoas = _pessoas(markdown)
    comparativo = [{"exame": "ESPIROMETRIA", "status": "encontrado"}]
    il.anotar_comparativo(comparativo, pessoas, linhas, _normalizar, lambda t: set())
    assert comparativo[0]["outra_pessoa"] == [{
        "chave": "outra_pessoa:0", "nome": "CARLOS LIMA ROCHA",
        "cpf": None, "pagina": 2, "tipo": il.SO_NOME,
    }]
    (payload,) = il.para_payload(pessoas, linhas)
    assert (payload["cpf"], payload["tipo"], payload["exames"]) == (None, il.SO_NOME, ["ESPIROMETRIA"])


def test_chave_e_unica_mesmo_com_iniciais_e_final_de_cpf_iguais():
    # Mesmo final de CPF (-35) e mesmas iniciais: com a chave mascarada, colidiam.
    markdown = ASO_DA_PACIENTE + (
        f"<!-- pagina 2 -->\nPaciente: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
        "<!-- pagina 3 -->\nPaciente: JOSE FICTICIO SANTOS\n## CPF: 222.333.442-35\n"
    )
    pessoas = _pessoas(markdown, nomes=NOMES | {"JOSE", "SANTOS"})
    assert [p["chave"] for p in pessoas] == ["outra_pessoa:0", "outra_pessoa:1"]


def test_linhas_salvas_acham_a_pessoa_no_texto_do_layout_sem_o_cabecalho():
    markdown = ASO_DA_PACIENTE + f"<!-- pagina 2 -->\n## Nome: JOAO FICTICIO SOUZA\n## CPF: {CPF_OUTRO}\n"
    (salva,) = il.para_payload(_achar(markdown), markdown.splitlines())
    textos_do_layout = ["ATESTADO", "Nome: JOAO FICTICIO SOUZA", f"CPF: {CPF_OUTRO}"]
    assert il.linhas_salvas(salva, textos_do_layout) == [1, 2]
    # O CPF guardado é mascarado: o trecho é o CPF válido com o mesmo final.
    assert il.trecho_salvo(salva, f"CPF: {CPF_OUTRO}") == (5, 19)
    assert il.trecho_salvo(salva, "Nome: JOAO FICTICIO SOUZA") == (6, 25)


# ── Rejeição pela IA (30/10) ────────────────────────────────────────────────

def test_motivo_cita_so_os_exames_e_nunca_a_pessoa():
    pessoas = [
        {"nome": "JOAO FICTICIO PEREIRA", "cpf": CPF_OUTRO, "exames": ["ELETROCARDIOGRAMA"]},
        {"nome": "JOAO FICTICIO PEREIRA", "cpf": None, "exames": ["ESPIROMETRIA", "ELETROCARDIOGRAMA"]},
    ]
    motivo = il.motivo_rejeicao(pessoas)
    assert motivo == "Laudo de outra pessoa nos exames: ELETROCARDIOGRAMA, ESPIROMETRIA."
    assert "JOAO" not in motivo and "111" not in motivo


def test_motivo_de_um_exame_e_de_pessoa_sem_exame():
    assert il.motivo_rejeicao([{"exames": ["AUDIOMETRIA"]}]) == "Laudo de outra pessoa no exame: AUDIOMETRIA."
    assert il.motivo_rejeicao([{"exames": []}]) == "Dados de outra pessoa no documento."


def test_documento_liberado_vira_rejeitado_com_o_motivo():
    validacao = {"status_liberado": True, "mensagem": "Todos os exames obrigatórios foram enviados. Liberação concedida."}
    ws._rejeitar_por_outra_pessoa(validacao, [{"exames": ["ELETROCARDIOGRAMA"]}])
    assert validacao == {
        "status_liberado": False,
        "mensagem": "Laudo de outra pessoa no exame: ELETROCARDIOGRAMA.",
    }


def test_documento_com_faltante_ganha_o_motivo_depois():
    validacao = {"status_liberado": False, "mensagem": "Faltam exames obrigatórios: AUDIOMETRIA"}
    ws._rejeitar_por_outra_pessoa(validacao, [{"exames": []}])
    assert validacao["mensagem"] == "Faltam exames obrigatórios: AUDIOMETRIA Dados de outra pessoa no documento."
    assert validacao["status_liberado"] is False


@pytest.mark.parametrize(
    "resultado, esperado",
    [
        ({"status": "success", "validation_result": {"exames_faltantes": []}}, "validated"),
        ({"status": "success", "validation_result": {"exames_faltantes": [], "outra_pessoa": False}}, "validated"),
        ({"status": "success", "validation_result": {"exames_faltantes": [], "outra_pessoa": True}}, "pending"),
        ({"status": "success", "validation_result": {"exames_faltantes": ["AUDIOMETRIA"]}}, "pending"),
        ({"status": "success"}, "validated"),
        ({"status": "error", "validation_result": {"exames_faltantes": []}}, "rejected"),
        ({"status": "partial", "validation_result": {"exames_faltantes": []}}, "pending"),
    ],
)
def test_decisao_da_ia(resultado, esperado):
    assert ws.decisao_da_ia(resultado) == esperado
