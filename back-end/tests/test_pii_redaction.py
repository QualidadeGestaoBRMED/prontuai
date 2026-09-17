"""Contratos da segregação de dados cadastrais antes da saída para a OpenAI.

Dois grupos, e os dois importam:

- **Não vaza**: cadastro nenhum sai no texto enviado.
- **Não estraga**: linha de exame sobrevive intacta.

O segundo grupo existe porque a primeira versão desta redação passava no
primeiro e reprovava no segundo — apagava o nome do exame em "Laudo Médico -
ELETROCARDIOGRAMA" e, por causa de uma frase acrescentada ao prompt, fazia o
modelo descartar "CLÍNICO OCUPACIONAL" inteiro. Medido em documentos reais.
"""

import pytest

from app.core import pii_redaction as red
from app.services import ocr_service

# CPFs/CNPJ sintéticos, válidos no dígito verificador.
CPF_VALIDO = "529.982.247-25"
CNPJ_VALIDO = "11.222.333/0001-81"


class TestNaoVaza:
    def test_campos_rotulados_do_cabecalho(self):
        texto = red.redigir_para_llm(
            f"Nome: JOAO DA SILVA SANTOS\n"
            f"CPF: {CPF_VALIDO}\n"
            f"Data de Nascimento: 24/04/1978\n"
            f"Endereco: Rua das Flores, 123\n"
            f"Telefone: (21) 98765-4321\n"
            f"E-mail: joao.silva@exemplo.com.br\n"
        )
        assert "JOAO DA SILVA SANTOS" not in texto
        assert "529" not in texto and "24/04/1978" not in texto
        assert "Rua das Flores" not in texto
        assert "98765" not in texto and "@exemplo.com.br" not in texto

    def test_coluna_dupla_do_textract(self):
        """O Textract junta colunas numa linha só; os dois campos têm de cair."""
        texto = red.redigir_para_llm("Nome FULANO DE TAL SOUZA Empresa ACME LTDA")
        assert "FULANO" not in texto and "ACME" not in texto
        assert red.NOME in texto and red.EMPRESA in texto

    def test_identificador_solto_sem_rotulo(self):
        texto = red.redigir_para_llm(f"rodape {CPF_VALIDO} {CNPJ_VALIDO} fim")
        assert "529" not in texto and "11.222" not in texto

    def test_valor_conhecido_some_onde_nao_ha_rotulo(self):
        """O nome se repete em cabeçalho e rodapé de cada página, sem rótulo."""
        texto = red.redigir_para_llm(
            "JOSE CARLOS PEREIRA - via do paciente\n"
            "## HEMOGRAMA\n"
            "JOSE CARLOS PEREIRA",
            valores_conhecidos=["JOSE CARLOS PEREIRA"],
        )
        assert "PEREIRA" not in texto
        assert "HEMOGRAMA" in texto

    def test_valor_conhecido_tolera_acento_e_pontuacao(self):
        texto = red.redigir_para_llm(
            "JOSE ANTONIO\nJOSÉ ANTÔNIO\n12345678909\n123.456.789-09",
            valores_conhecidos=["JOSÉ ANTÔNIO", "12345678909"],
        )
        assert "JOSE" not in texto.upper() and "12345678909" not in texto
        assert "123.456.789-09" not in texto

    def test_data_de_nascimento_cai_mesmo_preservando_datas(self):
        """A data de exame fica; a de nascimento é cadastro e sai de qualquer jeito."""
        texto = red.redigir_para_llm(
            "Dt. Nasc.: 24/04/1978\n## CLINICO OCUPACIONAL - 14/01/2026",
            preservar_datas=True,
        )
        assert "24/04/1978" not in texto
        assert "14/01/2026" in texto

    @pytest.mark.parametrize(
        "assinatura",
        [
            "Dr. Joana F.dos Santos",
            "Dr. J.C. Silva Junior",
            "Dra. Ana Maria Ribeiro",
            "Dr. Paulo de Souza e Silva",
        ],
    )
    def test_assinatura_abreviada_do_laudo(self, assinatura):
        """A inicial com ponto parava o padrão e o sobrenome do médico ficava."""
        texto = red.redigir_para_llm(assinatura)
        assert texto.strip() == f"Dr. {red.NOME}"

    def test_nome_em_caixa_mista_na_assinatura(self):
        """O nome sai em caixa alta no cabeçalho e em caixa mista na assinatura."""
        texto = red.redigir_para_llm(
            "NOME: YANE NUNES ALMEIDA\nAssinatura | Yane Nunes Almeida |",
            valores_conhecidos=["YANE NUNES ALMEIDA"],
        )
        assert "Yane" not in texto and "YANE" not in texto

    def test_nome_com_token_corrompido_pelo_ocr(self):
        """OCR erra uma letra e o nome completo deixa de casar; o par salva."""
        texto = red.redigir_para_llm(
            "Assinatura: Yane Nunes Almeidc", valores_conhecidos=["YANE NUNES ALMEIDA"]
        )
        assert "Yane" not in texto and "Nunes" not in texto

    def test_par_de_tokens_nao_apaga_exame_homonimo(self):
        """'ROSA' sozinho apagaria 'ROSA DE BENGALA'; por isso a regra é por par."""
        texto = red.redigir_para_llm(
            "## ROSA DE BENGALA\nPaciente ROSA MARIA SOUZA assinou",
            valores_conhecidos=["ROSA MARIA SOUZA"],
            preservar_datas=True,
        )
        assert "ROSA DE BENGALA" in texto
        assert "ROSA MARIA" not in texto

    def test_telefone_com_digito_extra_do_ocr(self):
        texto = red.redigir_para_llm("Contato: (21) 9962-11440")
        assert "9962" not in texto

    def test_logradouro_sem_rotulo(self):
        """O endereço aparece como linha solta no rodapé, sem campo que o nomeie."""
        texto = red.redigir_para_llm(
            "RUA DALVA DA FONSECA, N°: 128, SANTA ISABEL, RESENDE RJ 27522-000\n## HEMOGRAMA"
        )
        assert "DALVA" not in texto and "27522" not in texto
        assert "## HEMOGRAMA" in texto

    def test_nome_do_medico_na_assinatura_do_laudo(self):
        texto = red.redigir_para_llm("Dr. Carlos Eduardo Pereira\nCRM 12345")
        assert "Carlos" not in texto and "12345" not in texto


class TestLayoutDeLaudoDeLaboratorio:
    """Defeitos que só apareceram em documentos reais de produção.

    O ASO da BR MED é bem comportado; as páginas de laudo anexadas ao mesmo PDF
    (laboratório, telemedicina) usam outro layout e foi por elas que o nome do
    paciente escapou. Cada teste aqui é um vazamento medido, não hipotético.
    """

    def test_rotulo_preenchido_com_pontos(self):
        """'Paciente....:' — o preenchimento por pontos matava a regra de campo."""
        texto = red.redigir_para_llm(
            "Paciente....:166076-DARLAN SEVERO DOS SANTOS\nCPF.........: 529.982.247-25"
        )
        assert "DARLAN" not in texto and "529" not in texto

    def test_nome_colado_numa_pagina_e_espacado_em_outra(self):
        """O voucher traz o nome colado; o laudo, espaçado. O extrator vê um só."""
        texto = red.redigir_para_llm(
            "Nome:EMANUELSANTOSDASILVA\nEMANUEL SANTOS DA SILVA (M) 46 anos",
            valores_conhecidos=["EMANUELSANTOSDASILVA"],
        )
        assert "EMANUEL" not in texto

    def test_nome_quebrado_entre_linhas_na_assinatura(self):
        texto = red.redigir_para_llm(
            "Assinatura\nDarlan\nSevero dos Santos",
            valores_conhecidos=["DARLANSEVERODOSSANTOS"],
        )
        assert "Darlan" not in texto and "Severo" not in texto

    def test_nome_com_cauda_corrompida_pelo_ocr(self):
        """'Severo dos Serntor': a sequência inteira não casa, o prefixo casa."""
        texto = red.redigir_para_llm(
            "Darlan Severo dos Serntor", valores_conhecidos=["DARLANSEVERODOSSANTOS"]
        )
        assert "Darlan" not in texto and "Severo" not in texto


class TestNaoEstraga:
    """Cada caso aqui é uma linha de exame que já foi destruída em alguma versão."""

    @pytest.mark.parametrize(
        "linha",
        [
            "## Laudo Médico - ELETROCARDIOGRAMA",
            "Laudo Médico - RAIO-X",
            "## MÉDICO OCUPACIONAL",
            "PROVA DE FUNÇÃO PULMONAR",
            "## CLÍNICO OCUPACIONAL",
            "HEMOGRAMA COMPLETO COM PLAQUETAS",
            "ACUIDADE VISUAL COM SENSO CROMÁTICO",
            "## TGO (AST)",
            "AVALIAÇÃO PSICOSSOCIAL",
        ],
    )
    def test_linha_de_exame_sobrevive_intacta(self, linha):
        assert red.redigir_para_llm(linha, preservar_datas=True).strip() == linha

    def test_data_de_realizacao_do_exame_fica(self):
        """Sem a data, o modelo perde a âncora 'NOME DO EXAME - DATA' e pula a linha."""
        linha = "## CLÍNICO OCUPACIONAL - 14/01/2026"
        assert red.redigir_para_llm(linha, preservar_datas=True).strip() == linha

    def test_prompt_de_exames_nao_instrui_sobre_marcador(self):
        """Instruir o modelo a ignorar marcadores fazia ele descartar a linha toda.

        Medido em documento real: com a instrução, "CLÍNICO OCUPACIONAL" sumia
        da extração. A defesa contra marcador-virando-exame é `filtrar_exames`,
        não o prompt.
        """
        assert "marcador" not in ocr_service.PROMPT_EXTRAIR_EXAMES.lower()

    def test_marcador_nunca_vira_exame(self):
        assert ocr_service.filtrar_exames(["[NOME]", "HEMOGRAMA", "[CPF]"]) == ["HEMOGRAMA"]


class TestCpfNaoSaiDoAmbiente:
    """CPF é dado cadastral: a extração é local, sem LLM nenhum envolvido."""

    def test_nao_existe_mais_extracao_de_cpf_por_llm(self):
        assert not hasattr(ocr_service, "extrair_cpf_ia")
        assert not hasattr(ocr_service, "extrair_todos_cpfs_ia")
        assert not hasattr(ocr_service, "PROMPT_EXTRAIR_CPF")
        assert not hasattr(ocr_service, "PROMPT_EXTRAIR_TODOS_CPFS")

    def test_todos_os_cpfs_validos_na_ordem_do_texto(self):
        texto = f"titular {CPF_VALIDO}\ndependente 111.444.777-35\nlixo 123.456.789-00"
        assert ocr_service.extrair_todos_cpfs_regex(texto) == ["52998224725", "11144477735"]

    def test_exclui_o_cpf_do_titular(self):
        texto = f"titular {CPF_VALIDO}\ndependente 111.444.777-35"
        assert ocr_service.extrair_todos_cpfs_regex(texto, exclude_cpf="52998224725") == [
            "11144477735"
        ]

    def test_ignora_linha_de_cnpj_e_passaporte(self):
        texto = f"CNPJ {CNPJ_VALIDO}\nPASSAPORTE {CPF_VALIDO}"
        assert ocr_service.extrair_todos_cpfs_regex(texto) == []

    def test_e_deterministico(self):
        """O extrator por LLM variava entre execuções sobre o mesmo texto."""
        texto = f"paciente {CPF_VALIDO} e 111.444.777-35"
        assert len({tuple(ocr_service.extrair_todos_cpfs_regex(texto)) for _ in range(5)}) == 1


class TestSaidaEfetivaParaOpenAI:
    """Guarda de regressão no payload: o que de fato viaja na chamada."""

    def _capturar_prompt(self, monkeypatch, resposta):
        capturado = {}

        class _Resposta:
            def __init__(self, conteudo):
                self.choices = [type("C", (), {"message": type("M", (), {"content": conteudo})()})()]

        def _fake_create(**kwargs):
            capturado["payload"] = "\n".join(m["content"] for m in kwargs["messages"])
            return _Resposta(resposta)

        monkeypatch.setattr(
            ocr_service.client, "chat",
            type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(_fake_create)})()})(),
        )
        return capturado

    def test_extracao_de_exames_nao_envia_cadastro(self, monkeypatch):
        capturado = self._capturar_prompt(monkeypatch, '{"exames": ["HEMOGRAMA"]}')
        markdown = (
            f"Nome: PEDRO HENRIQUE COSTA\nCPF: {CPF_VALIDO}\nCNPJ: {CNPJ_VALIDO}\n"
            "## HEMOGRAMA COMPLETO 14/01/2026\n"
        )
        ocr_service.extrair_exames_ia(
            markdown, ["PEDRO HENRIQUE COSTA", "52998224725", "11222333000181", None]
        )
        payload = capturado["payload"]
        assert "PEDRO" not in payload
        assert "529" not in payload and "11.222" not in payload
        assert "HEMOGRAMA COMPLETO" in payload
        assert "14/01/2026" in payload

    def test_nenhum_dado_cadastral_no_payload_de_um_documento_completo(self, monkeypatch):
        """Documento com o cabeçalho cadastral inteiro: nada dele pode viajar."""
        capturado = self._capturar_prompt(monkeypatch, '{"exames": ["HEMOGRAMA"]}')
        markdown = (
            f"Nome ANA BEATRIZ ROCHA Empresa ACME LTDA\n"
            f"CPF: {CPF_VALIDO} Dt. Nasc.: 24/04/1978\n"
            f"CNPJ {CNPJ_VALIDO}\n"
            f"Endereco: Rua das Palmeiras, 45 - CEP 25522-000\n"
            f"Telefone: (21) 98765-4321  E-mail: ana@exemplo.com\n"
            f"Medico: Dr. Carlos Pereira CRM: 98765\n"
            f"## HEMOGRAMA COMPLETO COM PLAQUETAS 14/01/2026\n"
        )
        ocr_service.extrair_exames_ia(
            markdown, ["ANA BEATRIZ ROCHA", "52998224725", "11222333000181", None]
        )
        payload = capturado["payload"]
        for cadastral in (
            "ANA", "ROCHA", "ACME", "529", "52998224725", "24/04/1978",
            "11.222", "Palmeiras", "25522", "98765-4321", "ana@exemplo.com", "Carlos",
        ):
            assert cadastral not in payload, f"vazou: {cadastral}"
        assert "HEMOGRAMA COMPLETO COM PLAQUETAS" in payload

    def test_pipeline_nao_chama_a_openai_para_cpf(self, monkeypatch):
        """Regex sem resultado não aciona LLM: o documento segue sem CPF."""
        chamadas = []

        def _registrar(**kwargs):
            chamadas.append("\n".join(m["content"] for m in kwargs["messages"]))
            raise RuntimeError("payload registrado")

        monkeypatch.setattr(
            ocr_service.client, "chat",
            type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(_registrar)})()})(),
        )
        markdown = f"Paciente: JOAO DA SILVA\nCPF ilegivel: 000.000.000-00\n## HEMOGRAMA"
        assert ocr_service.extrair_cpf_regex(markdown) is None
        ocr_service.extrair_exames_ia(markdown, ["JOAO DA SILVA", None, None, None])
        # A única chamada é a de exames, e sem cadastro dentro.
        assert len(chamadas) == 1
        assert "JOAO" not in chamadas[0]


class TestConferenciaDeSaida:
    """A guarda que transforma 'as regras pegaram' em 'foi conferido'.

    Existe porque redação por regra é heurística: um layout nunca visto pode
    trazer um campo em forma que nenhuma regra alcança. A conferência não
    depende de rótulo nem de emissor.
    """

    def test_texto_so_de_exames_passa(self):
        red.verificar_payload(
            "## HEMOGRAMA COMPLETO COM PLAQUETAS 14/01/2026\n## CLÍNICO OCUPACIONAL\n[NOME]"
        )

    @pytest.mark.parametrize(
        "texto",
        [
            f"## HEMOGRAMA\nCPF {CPF_VALIDO}",
            f"## HEMOGRAMA\n{CNPJ_VALIDO}",
            "## HEMOGRAMA\ncontato ana@exemplo.com",
            "## HEMOGRAMA\n(21) 98765-4321",
            "## HEMOGRAMA\nCEP 25522-000",
        ],
    )
    def test_cadastro_remanescente_e_barrado(self, texto):
        with pytest.raises(red.VazamentoDeDadoCadastral):
            red.verificar_payload(texto)

    def test_cpf_invalido_nao_dispara_falso_positivo(self):
        """Número de 11 dígitos que não passa no dígito verificador não é CPF."""
        red.verificar_payload("## HEMOGRAMA\nprotocolo 123.456.789-00")

    def test_valor_conhecido_do_documento_e_barrado(self):
        with pytest.raises(red.VazamentoDeDadoCadastral):
            red.verificar_payload(
                "## HEMOGRAMA\nassinado por Yane Nunes Almeida",
                ["YANE NUNES ALMEIDA"],
            )

    def test_mensagem_do_erro_nao_contem_o_valor(self):
        """A mensagem vai para log: nomeia o tipo, nunca o dado."""
        with pytest.raises(red.VazamentoDeDadoCadastral) as erro:
            red.verificar_payload(f"CPF {CPF_VALIDO}")
        assert CPF_VALIDO not in str(erro.value)
        assert "529" not in str(erro.value)

    def test_falha_fechada_nao_chama_a_openai(self, monkeypatch):
        """Guarda reprovou: nada é enviado e o erro volta como 'sem exames'."""
        def _explode(**kwargs):
            raise AssertionError("não deveria enviar payload reprovado")

        monkeypatch.setattr(
            ocr_service.client, "chat",
            type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(_explode)})()})(),
        )
        # Simula regra que não alcançou o campo: redação devolve o texto cru.
        monkeypatch.setattr(
            ocr_service.pii_redaction, "redigir_para_llm",
            lambda texto, **kwargs: texto,
        )
        resultado = ocr_service.extrair_exames_ia(
            f"Paciente: MARIA SOUZA\nCPF: {CPF_VALIDO}\n## HEMOGRAMA", ["MARIA SOUZA"]
        )
        assert resultado["exames"] == []
        assert "bloqueado" in resultado["erro"].lower()
