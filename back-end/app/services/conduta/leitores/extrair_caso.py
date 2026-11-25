"""
Do documento exportado (.md redigido + linha do banco) para:

- o CASO, entrada de `montar_features` — só o que existe antes da decisão do médico;
- o RÓTULO — o que a página de encaminhamento diz (especialidade, exames que
  motivaram, acompanhamento).

A página de encaminhamento e qualquer frase de encaminhamento saem do texto ANTES
de ler valores, tipo, função e riscos. Sem isso, "glicose 113 mg/dL. Encaminho ao
endocrinologista" entraria como resultado e o modelo aprenderia com o rótulo.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

import normalidade_exames as ne
import json as _json
from pathlib import Path as _Path

# Ficha clínica extraída pelo mesmo código de produção (app.services.ficha_clinica.extrair_ficha: regras
# + 4o mini, STC-1068/1070), rodada uma vez por documento em ficha_medicao/rodar_835.py.
_FICHAS = _Path(__file__).resolve().parent.parent / "ficha_medicao" / "fichas_835.jsonl"
_FICHAS_CACHE: dict[str, Any] | None = None


def _ficha_plana(document_id: str) -> dict[str, Any]:
    """FichaClinica achatada nas chaves da tabela. Sem ficha extraída: dicionário vazio (nao_informado)."""
    global _FICHAS_CACHE
    if _FICHAS_CACHE is None:
        _FICHAS_CACHE = {}
        if _FICHAS.exists():
            for linha in _FICHAS.read_text().splitlines():
                if linha.strip():
                    x = _json.loads(linha)
                    _FICHAS_CACHE[x["document_id"]] = x["ficha"]
    f = _FICHAS_CACHE.get(document_id)
    if not f:
        return {"fonte": "sem_ficha"}
    sv = f["sinais_vitais"]
    plano: dict[str, Any] = {
        "pa_sistolica": sv["pa_sistolica"], "pa_diastolica": sv["pa_diastolica"], "freq_cardiaca": sv["freq_cardiaca"],
        "peso": sv["peso_kg"], "altura": sv["altura_cm"], "imc": sv["imc"], "circ_abdominal": sv["circ_abdominal_cm"],
        "fonte": f["fonte"], "n_outros_achados": len(f["outros_achados_relevantes"]),
    }
    for k, c in f["anamnese"].items():
        plano[k] = c["valor"]
    for k, c in f["condicoes"].items():
        plano[k if k == "doenca_neurologica" else f"doenca_{k}"] = c["valor"]
    for k, c in f["exame_fisico"].items():
        plano[f"exame_{k}"] = c["valor"]
    for k, c in f["historico_familiar"].items():
        plano[f"familiar_{k}"] = c["valor"]
    for k, c in f["medicamentos"].items():
        plano[f"medicamento_{k}"] = c["valor"]
    return plano


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", texto).strip()


# ---------------------------------------------------------------------------
# Separar o rótulo do texto de entrada
# ---------------------------------------------------------------------------

# Frases que citam "encaminh"/"aos cuidados" e não são conduta médica.
_NAO_E_CONDUTA = re.compile(
    r"GUIA DE ENCAMINHAMENTO|DATA DE ENCAMINHAMENTO|ENCAMINHADO POR\s*:|EXIJAM ALGUM ENCAMINHAMENTO"
    r"|AOS CUIDADOS COM A AUDI|AOS CUIDADOS DO DEPARTAMENTO|ENCAMINHAMENTOS/RESUMO|\[ENCAMINHAMENTO\]"
    r"|ENCAMINHO O RESULTADO|ENCAMINHAMOS O RESULTADO|ALGUM ENCAMINHAMENTO|NENHUM ENCAMINHAMENTO|SEM ENCAMINHAMENTO"
    r"|NECESSIDADE DE ENCAMINHAMENTO|AOS CUIDADOS COM"
    # Conferido no PDF/texto em 19/11 (falsos "sim" da reposição): história de vida ("por intermédio e encaminhamento da
    # APAE"), autorização de entrega de resultado, cabeçalho da guia de exames e pedido da empresa/iASO, campo em
    # branco "Encaminhamento ao perito?" e o formulário "Encaminhamento Médico Ocupacional" (empresa → clínica).
    r"|POR INTERMEDIO E ENCAMINHAMENTO|ENTREGA DOS RESULTADOS|ENCAMINHAMENTO UNIDADE\s*:|ENCAMINHAMENTO DE .{0,60}IASO|SERA ENCAMINHADO EM ANEXO|ENCAMINHAMENTO AUTOMATICO"
    r"|ENCAMINHAMENTO AO PERITO|ENCAMINHAMENTO MEDICO OCUPACIONAL"
    # Protocolo psicossocial impresso: "( ) Não existem motivos no momento que exijam encaminhamento" (8716f98a, 23/11).
    r"|EXIJAM ENCAMINHAMENTO"
    # Auditoria das pendências do Breno (23/11, conferido na imagem): introdução do relatório da psicóloga, amostra
    # "encaminhada ao laboratório", "cuidados pré-coleta", guia de exames ("para a realização dos seguintes
    # procedimentos"), declarações (INSS, ciência de perda auditiva, recibo de retirada de exames), aviso do SRQ e texto
    # padrão do laudo de RX ("devem ser encaminhados ao médico solicitante").
    r"|FOI ENCAMINHAD\w* PARA REALIZAR\b|ENCAMINHAD\w* (?:E ANALISAD\w* )?(?:AO|PELO) LABORATORIO"
    r"|AMOSTRA\w*(?: BIOLOGICA)? ENCAMINHAD|CUIDADOS PRE-? ?COLETA|PARA A REALIZACAO DO\(?S?\)? SEGUINTE"
    r"|DOCUMENTA\w* ENCAMINHAD\w* PEL|ENCAMINHAD\w* PELA EM|POR OCASIAO DO ENCAMINHAMENTO"
    r"|NECESSARIO ENCAMINHAMENTO IMEDIATO|ENCAMINHAD\w* AO MEDICO SOLICITANTE"
)
# Link impresso no rodapé do voucher de agendamento da BR MED (".../guia-encaminhamento/<token>"): o voucher é a
# guia do exame, não carta a especialista (503582d4, página 3, conferido no PDF em 19/11). Vale só para a própria
# linha: o mesmo documento pode ter uma carta de verdade perto do link (4cd8345d).
_LINK_VOUCHER = re.compile(r"GUIA-\s*ENCAMINH")
# Opção de formulário sem marca ("( ) Encaminhado para especialista") não é conduta.
_CAIXA_VAZIA = re.compile(r"\(\s*_*\s*\)\s*[A-Z/ ]{3,40}|\[\s*_*\s*\]\s*[A-Z/ ]{3,40}")
# Citação de visão que não é motivo de encaminhamento (conferido nos 50 casos que sobraram da lista do Breno, 23/11):
# anamnese ("uso de correção visual", "boa acuidade visual com lentes", "turvação visual"), laudo psicológico
# ("revela visão prática", "boa apresentação visual") e laudo/checklist de acuidade anexado na página da carta
# ("Avaliação da acuidade visual", escala "(1) 20/100 (2) 20/50", "Ortho Rater", "X Acuidade visual teste de cores").
_NAO_E_ACUIDADE = re.compile(
    r"VISAO PRATICA|APRESENTACAO VISUAL|CORRECAO VISUAL|LENTES? (?:DE )?CORRE\w*(?: VISUAL)?|BOA ACUIDADE VISUAL"
    r"|TURVACAO VISUAL|VISAO TURVA|NEGA ALTERACOES VISUAIS|ACUIDADE VISUAL TESTE DE CORES|AVAL\w*(?:\s*ACAO)? (?:DA )?ACUIDADE VISUAL"
    r"|MEDIAR ACUIDADE VISUAL|VISAO CROMATICA\s*\(?\s*NORMAL"
    r"|ORTHO RATER|ACUIDADE VISUAL\s+(?:#+\s*)?NOME\s*:|TIPO DO EXAME\s*:\s*VISUAL|\(\d{1,2}\)\s*20/\d+"
    r"|ACUIDADE VISUAL PARA LONGE\s+ACUIDADE VISUAL PARA PERTO"
)
_EMAIL_COM_ENCAMINHAMENTO = re.compile(
    r"\(\s*X\s*\)\s*COM ENCAMINHAMENTO|\(\s*X\s*\)\s*FOI ENTREGUE[^()]{0,80}ENCAMINHAMENTO|APROVAR COMO APTO COM (?:OS )?ENCAMINHAMENTO|\bAPTO COM (?:OS )?ENCAMINHAMENTOS?\b"
)
# Atendimento assistencial (ambulatório da empresa) e contato por Teams: a "Conduta:" é tratamento/orientação; só conta
# se houver verbo de encaminhamento ("encaminhamento médico à coloproctologia", 8988746) ou especialista citado. 57 dos 87 "incertos".
_ASSISTENCIAL = re.compile(r"ATENDIMENTO ASSISTENCIA|VIA TEAMS")


def _assistencial_sem_encaminhamento(n: str) -> bool:
    # Só sai do rótulo o atendimento que não encaminha nem cita especialista. "Oriento acompanhamento com psiquiatra",
    # "seguimento com ortopedista assistente" continuam (34 casos assim na base de 10 mil, conferidos em 23/11).
    return bool(_ASSISTENCIAL.search(n)) and not _VERBO.search(n) and not any(rx.search(n) for rx in ESPECIALIDADES.values())
_EMAIL = re.compile(r"COMUNICADO DE (?:EXAME ALTERADO|ALTE\w*RA\w*|REPETICAO)|PIPEFY|CAIXA DE ENTRADA")
_INICIO_CONDUTA_EMAIL = re.compile(
    r"CONDUTA|APTO COM (?:OS )?ENCAMINHAMENTO|APROVAR (?:O )?(?:ASO )?COMO APTO|LIBERAR (?:O )?(?:ASO|COMO APTO)|ENCAMINHAR")
_FIM_CONDUTA_EMAIL = re.compile(
    r"\[TEXTO DAS MENSAGENS|\[TEXLO|COMUNICAMOS QUE|SEGUEM? (?:OS )?DETALHES|<!--|ESTE E UM E-?MAIL|EM \w{3}\.?,? \d{1,2} DE")


def _conduta_do_email(n: str) -> str:
    m = _INICIO_CONDUTA_EMAIL.search(n)
    if not m:
        return ""
    trecho = n[m.start():m.start() + 600]
    fim = _FIM_CONDUTA_EMAIL.search(trecho)
    return "[CONDUTA DO E-MAIL] " + (trecho[:fim.start()] if fim else trecho)


MARCA_EMAIL = "[ENCAMINHAMENTO INFORMADO NO E-MAIL DO COMUNICADO DE EXAME ALTERADO]"
_NAO_E_CARTA = re.compile(
    r"DECLARA\w* DE DROGAS|TESTE ALEATORI|COMUNICADO DE (?:EXAME ALTERADO|ALTE\w*RA\w*|REPETICAO)|PIPEFY"
    r"|SUMARIO DE EXAMES|CAIXA DE ENTRADA"
)
# Linha que marca conduta. "ENCAM+" pega também o OCR torto ("Encammho").
_MARCA = re.compile(
    r"\bENCA?M+I?N?H|ENCAMINER|\bAOS CUIDADOS\b|\bCONDUTA\s*:|CONTRA-?REFERENCIA|RECOMENDACAO\s*:|SOLICITO (?:AVALIACAO|PARECER)"
    # Carta de acompanhamento sem "encaminho" ("sugiro acompanhamento nos resultados dos próximos exames").
    r"|SUGIRO (?:ACOMPANHAMENTO|REAVALIA)"
    # Carta BR MED em inglês (offshore): "I hereby refer / I am referring this employee ... TO: ENDOCRINOLOGY DEPARTMENT"
    # (unicodoc-8770680 tinha 4 e saía "nao"; 133 documentos na base de 10 mil, Breno 23/11).
    r"|\bI (?:HEREBY )?REFER\b|\bI AM REFERRING\b|\bREFERR?(?:ING)? (?:THIS|THE) (?:ABOVE|PATIENT|EMPLOYEE|WORKER)\b"
)
# Título de página de encaminhamento: o bloco é a página inteira.
_TITULO = re.compile(
    r"^#*\s*(?:ENCAMINHAMENTO(?:\s+(?:MEDICO|AO|A|PARA|CLINICO)\b|\s*\.?$)|GUIA DE REFERENCIA|CARTA DE ENCAMINHAMENTO"
    r"|FICHA DE ENCAMINHAMENTO|REFERENCIA E CONTRA)"
)
# Campo "Encaminhamentos" de formulário (audiometria, ficha): só o campo e a linha seguinte.
_CAMPO = re.compile(r"^ENCAMINHAMENTOS\s*:?\s*$|^ENCAMINHAMENTOS?\s*:")
LINHAS_CAMPO = 1
# Começo de carta de encaminhamento logo abaixo do título.
_CARTA = re.compile(
    r"\bENCA?M+I?N?H|ENCAMINER|\bPACIENTE\b|COLABORADOR|FUNCIONARIO|PREZAD|\bAO (?:DR|PSF|MEDICO|CLINICO)|SOLICITO|AVALIACAO"
)
# Início de outro documento ou de laudo de laboratório: fecha qualquer bloco.
_OUTRO_DOC = re.compile(
    r"ATESTADO DE SAUDE OCUPACIONAL|^#*\s*FICHA (?:MEDICA|CLINICA)|^#+\s*LAUDO|VALOR(?:ES)? DE REFERENCIA|MATERIAL\s*:|METODO\s*:"
    r"|^#+\s*(?:AUDIOMETRIA|ELETROCARDIOGRAMA|HEMOGRAMA)|QUESTIONARIO|DATA DE REVISAO"
)
# Seção da ficha ou do laudo: fecha a frase solta, não a carta (a carta cita resultado).
_SECAO = re.compile(
    r"^#*\s*(?:EXAME FISICO|SINAIS VITAIS|ANAMNESE|HABITOS|HISTORIA|DADOS DO PACIENTE|IDENTIFICACAO|TIPO DE EXAME"
    r"|PROCEDIMENTOS|RESULTADO|AUDIOMETRIA|ELETROCARDIOGRAMA|HEMOGRAMA|LAUDO)"
)
# Assinatura do médico: a carta termina logo depois.
_ASSINATURA = re.compile(r"\bCRM\b|\bCRM-|MEDICO DO TRABALHO|MEDICINA DO TRABALHO")
_PAGINA = re.compile(r"^<!--\s*pagina\s*\d+\s*-->$", re.I)
# Rótulo de campo sem valor na mesma linha ("## MOTIVO:").
_CAMPO_ABERTO = re.compile(r"^#*\s*[A-Z][A-Z ./()]{1,30}:\s*$")

LINHAS_FRASE = 6
# Linha curta de destinatário de carta: "AO OFTALMOLOGISTA,", "A UBS", "AO DR. [NOME]", "AOS CUIDADOS DO CARDIOLOGISTA".
_DESTINATARIO = re.compile(
    r"^(?:AO|A|AOS|AS|PARA|PREZAD[OA]S?|ILMO\.?|ILMA\.?|EXMO\.?)\s+(?:\(A\)\s+)?(?:DR|DRA|SR|SRA|MEDIC|ESPECIALISTA|CLINIC|"
    r"SERVICO|SETOR|AMBULATORIO|POSTO|UBS|UPA|PSF|PRONTO|UNIDADE|COLEGA|CUIDADOS|[A-Z]+(?:LOGISTA|LOGIA|IATRA|PEDISTA|OFTALM\w*))"
    r"[^\n]{0,50}$"
)
# Linha que é só a especialidade (destinatário sem "Ao"): "CLINICO GERAL/ENDOCRINOLOGISTA", "OFTALMOLOGISTA,".
_SO_ESPECIALIDADE = re.compile(
    r"^(?:CLINIC[OA](?: GERAL| MEDIC[OA])?|MEDICO ASSISTENTE|GENERALISTA|[A-Z]+(?:LOGISTA|LOGIA|IATRA|PEDISTA)|OTORRINO\w*|OFTALM\w*)"
    r"(?:\s*(?:/|\bE\b|\bOU\b|,)\s*(?:CLINIC[OA](?: GERAL)?|GENERALISTA|[A-Z]+(?:LOGISTA|LOGIA|IATRA)|OTORRINO\w*|OFTALM\w*))*\s*[,:.]?$"
)
# Abertura de carta: saudação, destinatário ou linha que é só a especialidade.
_ABERTURA_CARTA = re.compile(
    r"(?:PREZAD[OA]|CAR[OA]\s+(?:COLEGA|DR))|" + _DESTINATARIO.pattern.lstrip("^") + "|" + _SO_ESPECIALIDADE.pattern.lstrip("^")
)
LINHAS_PAGINA = 45


# Campo de formulário com opções: "Encaminhamento oftalmológico ( ) Sim ( ) Não", "Encaminhar ao oftalmologista /
# ( ) SIM / ) NAO" (o Textract quebra as opções em linhas). Só é conduta com o "Sim" marcado. Medido na comparação
# Textract × RapidOCR de 23/11: 7 de 15 divergências de rótulo eram esse campo vazio, lido como "sim" no Textract.
_CAMPO_SIM_NAO = re.compile(r"ENCA?M+I?N?H\w*[^.:]{0,40}?[:\s#]*(?:[(\[]?\s*X?\s*[)\]]?\s*)(SIM|NAO)\b.{0,25}?\b(SIM|NAO)\b")
_SIM_MARCADO = re.compile(r"(?:\(\s*X\s*\)|\[\s*X\s*\]|\bX)\s*SIM\b|\bSIM\s*\(\s*X\s*\)")
_NAO_MARCADO = re.compile(r"(?:\(\s*X\s*\)|\[\s*X\s*\]|\bX)\s*NAO\b|\bNAO\s*\(\s*X\s*\)")


def eh_conduta(norm: list[str], i: int) -> bool:
    """A linha i (já normalizada) traz conduta médica."""
    if not _MARCA.search(_CAIXA_VAZIA.sub(" ", norm[i])) or _LINK_VOUCHER.search(norm[i]):
        return False
    # As 4 primeiras linhas com texto a partir da i (o Textract intercala linhas vazias entre as opções).
    janela = " ".join([x.strip("# ") for x in norm[i:i + 15] if x.strip("# ")][:4])
    campo = _CAMPO_SIM_NAO.search(janela)
    if campo and {campo.group(1), campo.group(2)} == {"SIM", "NAO"} and campo.start() < len(norm[i].strip("# ")):
        opcoes = janela[campo.start():campo.end() + 6]
        return bool(_SIM_MARCADO.search(opcoes)) and not _NAO_MARCADO.search(opcoes)
    # "( ) Encaminhar ao ORL" com o "(" na linha de cima (quebra do Textract): opção vazia.
    if re.match(r"^#*\s*\)\s*ENCA?M", norm[i]):
        anterior = next((norm[k].strip() for k in range(i - 1, max(-1, i - 4), -1) if norm[k].strip("# ")), "")
        if re.search(r"\(\s*$", anterior) or not anterior:
            return False
    # Rodapé impresso do formulário de audiometria: "Conduta: ☐ Prevenção ☐ Acompanhamento ☐ Encaminhamento". O OCR
    # não traz a caixinha, então a palavra solta não diz se foi marcada; no f0ad1333 (PDF conferido em 19/11) nenhuma
    # estava marcada e o laudo tem carimbo "AUDIOMETRIA NORMAL". Opção impressa não é conduta.
    if norm[i].strip("# ") == "ENCAMINHAMENTO":
        anterior = next((norm[k].strip("# ") for k in range(i - 1, max(-1, i - 4), -1) if norm[k].strip("# ")), "")
        if anterior == "ACOMPANHAMENTO":
            return False
    # A frase que desmente a conduta pode ter quebrado de linha ("aos cuidados" / "do Departamento").
    # O título "Guia de encaminhamento" logo acima de "Encaminhamos o colaborador ... para esclarecimentos" é a carta
    # de verdade (2b670dab, conferido em 19/11): ele só desmente a linha que o próprio título contém, não a vizinha.
    if _NAO_E_CONDUTA.search(norm[i]):
        return False
    vizinhas = " ".join(norm[max(0, i - 1):i + 2])
    return not _NAO_E_CONDUTA.search(vizinhas.replace("GUIA DE ENCAMINHAMENTO", " "))


def separar_rotulo(md: str) -> tuple[str, list[str]]:
    """(texto de entrada sem a conduta, blocos de texto da conduta)."""
    linhas = md.splitlines()
    norm = [_norm(l) for l in linhas]
    fora = [False] * len(linhas)
    blocos: list[list[int]] = []

    # Páginas marcadas: a página com encaminhamento sai inteira.
    paginas: list[tuple[int, int]] = []
    inicio = 0
    for i, l in enumerate(linhas):
        if _PAGINA.match(l.strip()):
            if i > inicio:
                paginas.append((inicio, i))
            inicio = i
    paginas.append((inicio, len(linhas)))

    for i in range(len(linhas)):
        if fora[i] or not eh_conduta(norm, i):
            continue
        if len(paginas) > 1:
            a, b = next((a, b) for a, b in paginas if a <= i < b)
            if b - a <= 120:  # página de verdade, não o documento todo
                idx = list(range(a, b))
                for j in idx:
                    fora[j] = True
                blocos.append(idx)
                continue
        if _TITULO.search(norm[i]) and not _CAMPO.search(norm[i]) and _CARTA.search(" ".join(norm[i + 1:i + 16])):
            limite = LINHAS_PAGINA
        elif _CAMPO.search(norm[i]) or _TITULO.search(norm[i]):
            # Título sem carta embaixo é campo de formulário ("Encaminhamento / Data do exame").
            limite = LINHAS_CAMPO
        else:
            limite = LINHAS_FRASE
        idx = [i]
        # Destinatário na linha de cima ("Ao Oftalmologista," / "À UBS" / "Ao Dr.") também é da carta: sem isto a
        # especialidade ficava fora do rótulo e dentro da entrada (caso 28ede010, conferência de 19/11).
        # A carta pode trazer o "Encaminho" só no fim: "CLINICO GERAL/ENDOCRINOLOGISTA / Prezado(a) Dr(a), /
        # ... / ENCAMINHO PARA AVALIAÇÃO" (b8657b55). Volta até 12 linhas atrás da abertura da carta; para em
        # outro documento, em página nova ou em linha que já é de outra carta.
        inicio = None
        k = i - 1
        while k >= 0 and i - k <= 12 and not fora[k] and not _OUTRO_DOC.search(norm[k]) and not _PAGINA.match(linhas[k].strip()):
            if _ABERTURA_CARTA.match(norm[k].lstrip("# ")):
                inicio = k
            k -= 1
        if inicio is not None:
            # Linha só com a especialidade logo acima da abertura ("CLINICO GERAL/ENDOCRINOLOGISTA").
            while inicio - 1 >= 0 and not fora[inicio - 1] and (
                not norm[inicio - 1].strip("# ") or _SO_ESPECIALIDADE.match(norm[inicio - 1].lstrip("# "))
            ):
                inicio -= 1
            while inicio < i and not norm[inicio].strip("# "):
                inicio += 1
            idx = list(range(inicio, i)) + idx
        j = i + 1
        fim_assinatura = None
        parou_no_limite = False
        while j < len(linhas) and not _OUTRO_DOC.search(norm[j]) and not (
            limite != LINHAS_PAGINA and _SECAO.search(norm[j])
        ):
            if j - i > limite:
                parou_no_limite = True
                break
            if fim_assinatura is not None and j > fim_assinatura:
                break
            idx.append(j)
            if fim_assinatura is None and _ASSINATURA.search(norm[j]):
                fim_assinatura = j + 3
            j += 1
        # Formulário "PARA: / Endocrinologia / MOTIVO: / glicemia 102": as linhas em branco do OCR gastam o
        # limite e o bloco fecha no rótulo do campo. Leva junto a primeira linha preenchida depois dele.
        if parou_no_limite and limite == LINHAS_FRASE:
            ultima = next((norm[k] for k in reversed(idx) if norm[k]), "")
            if _CAMPO_ABERTO.search(ultima):
                while j < len(linhas) and not norm[j] and not fora[j]:
                    idx.append(j)
                    j += 1
                # Linha que já é conduta ("MOTIVO: / Encaminho para melhor seguimento") abre o próprio bloco.
                if (j < len(linhas) and not fora[j] and not _OUTRO_DOC.search(norm[j]) and not _SECAO.search(norm[j])
                        and not eh_conduta(norm, j)):
                    idx.append(j)
        for k in idx:
            fora[k] = True
        blocos.append(idx)

    entrada = "\n".join(l for l, f in zip(linhas, fora) if not f)
    # Página que cai como conduta sem ser carta do médico (formulário de drogas e álcool da SBM, e-mail do Pipefy
    # "Comunicado de exame alterado", "Sumário de exames" impresso, caixa de entrada do Outlook): sai do rótulo e
    # continua fora da entrada, porque lista exame alterado e entregaria a resposta (Breno, 23/11).
    textos = ["\n".join(linhas[k] for k in b) for b in blocos]
    cartas = [t for t in textos if not _NAO_E_CARTA.search(_norm(t))
              and not _assistencial_sem_encaminhamento(_norm(t))]
    # Do e-mail da coordenação que saiu do rótulo, volta só a frase da conduta ("apto com encaminhamentos: nefrologia
    # TFG 79; pneumologia...", "encaminhar endócrino e gastro", "solicitar parecer do psiquiatra"): é ali que está a
    # especialidade. A lista de exames do comunicado ("apresentando alteração no(s) exame(s): ...") fica de fora.
    # Sem isto, 44 encaminhados perderam especialidade na v23.12 (conferido em 24/11).
    for t in textos:
        if _EMAIL.search(_norm(t)):
            conduta = _conduta_do_email(_norm(t))
            # Só entra se a conduta encaminha ou nomeia especialista; "pode liberar como apto" sozinho não é rótulo.
            if conduta and (_VERBO.search(conduta) or re.search(r"APTO COM (?:OS )?ENCAMINH", conduta)
                            or any(rx.search(conduta) for rx in ESPECIALIDADES.values())):
                cartas.append(conduta)
    # O e-mail de "Comunicado de exame alterado" sai do rótulo (lista os exames alterados), mas quando marca
    # "(X) COM ENCAMINHAMENTO" ou "aprovar como apto com os encaminhamentos" houve encaminhamento: entra um bloco
    # sem texto da carta, que vira encaminhado=sim sem especialidade (7330520, conferido em 23/11).
    if _EMAIL_COM_ENCAMINHAMENTO.search(_norm(md)):
        cartas.append(MARCA_EMAIL)
    return entrada, cartas


# ---------------------------------------------------------------------------
# Caso (entrada)
# ---------------------------------------------------------------------------

_TIPOS = (
    ("retorno_trabalho", r"RETORNO AO TRABALHO|RETURN TO WORK"),
    ("mudanca_risco", r"MUDANCA DE (?:RISCO|FUNCAO)|CHANGE OF (?:RISK|FUNCTION)"),
    ("demissional", r"DEMISSIONAL|POST-EMPLOYMENT|DISMISSAL"),
    ("admissional", r"ADMISSIONAL|PRE-EMPLOYMENT"),
    ("periodico", r"PERIODICO|PERIODICAL|PERIODIC"),
)
_TIPO_ROTULADO = re.compile(
    r"(?:TIPO DE EXAME|MODO DO EXAME|MOTIVO|FINALIDADE DO EXAME|T\.S\.|EXAM TYPE|FICHA MEDICA)\s*[:\-/]?\s*(.{0,60})"
)
_TIPO_BILINGUE = re.compile(r"^#*\s*(ADMISSIONAL|PERIODICO|DEMISSIONAL|RETORNO AO TRABALHO|MUDANCA DE RISCO[A-Z ]*)\s*/")
_MARCADO = re.compile(r"\(\s*X\s*\)\s*([A-Z][A-Z ]{3,40})|\[\s*X\s*\]\s*([A-Z][A-Z ]{3,40})")


def _tipo(texto: str) -> Optional[str]:
    def mapear(s: str) -> Optional[str]:
        for chave, rx in _TIPOS:
            if re.search(rx, s):
                return chave
        return None

    linhas = [_norm(l) for l in texto.splitlines()]
    for l in linhas:
        m = _TIPO_BILINGUE.search(l)
        if m and (t := mapear(m.group(1))):
            return t
    for l in linhas:
        m = _TIPO_ROTULADO.search(l)
        # Linha com várias opções sem marca ("( ) Admissional ( ) Periódico") não decide.
        if m and "( )" not in m.group(1) and (t := mapear(m.group(1))):
            return t
    for l in linhas:
        for m in _MARCADO.finditer(l):
            if t := mapear(m.group(1) or m.group(2)):
                return t
    return None


_FUNCAO = re.compile(r"^#*\s*(?:CARGO\s*/\s*)?FUNCAO(?:\s*/\s*FUNCTION)?\s*[:\-]?\s+(.{3,60})$")


def _funcao(texto: str) -> Optional[str]:
    for l in texto.splitlines():
        m = _FUNCAO.search(_norm(l))
        if m:
            valor = m.group(1).strip(" :-")
            if "[" not in valor and not re.search(r"\b(?:DATA|SETOR|CPF|CBO|MATRICULA)\b", valor):
                return valor
    return None


_RISCOS_INICIO = re.compile(r"RISCOS?\s+OCUPACIONA|FATORES DE RISCO|^#*\s*\d?\.?\s*RISCOS?\b|OCCUPATIONAL RISKS|RISCOS?\s*:")
_RISCOS_FIM = re.compile(
    r"PROCEDIMENTOS|EXAMES? (?:REALIZADOS|COMPLEMENTARES)|PERFORMED|APTID|CONCLUS|^#*\s*\d\.\s|PARECER|VALIDADE"
)


def _riscos(texto: str) -> Optional[list[str]]:
    linhas = texto.splitlines()
    for i, l in enumerate(linhas):
        n = _norm(l)
        if _RISCOS_INICIO.search(n) and "ANTECEDENTES" not in n:
            trecho = [n]
            for l2 in linhas[i + 1:i + 12]:
                n2 = _norm(l2)
                if _RISCOS_FIM.search(n2):
                    break
                trecho.append(n2)
            return [t for t in trecho if t]
    return None


# Atividade crítica: o ASO lista só as da função ("Trabalho em Altura / Work at Height (NR 35):"). Vale a
# PRESENÇA da linha. O "Apto / Inapto" que vem embaixo é a conclusão do médico (rótulo) e nunca é lido.
# Valores do contrato da API (doc "ProntuAI — API de Normalidade e Conduta Sugerida", enum atividade_critica).
# A NR vale pelo NÚMERO impresso na linha da lista do ASO: "Trabalho Offshore (NR 30)" é NR_30; "Embarque
# Offshore", "Transbordo" e "Brigada de Emergência" vêm com NR 37; "Operação de Veículos Industriais (NR 11)" é
# empilhadeira = operador de equipamento pesado. NR-20 (inflamáveis) não está no contrato e saiu.
ATIVIDADES_NR = {
    "nr_10": 10, "nr_30": 30, "nr_33": 33, "nr_35": 35, "nr_37": 37, "operador_equipamento_pesado": 11,
}
_LINHA_NR = re.compile(r"\(NR ?-?\d{2}\)|\bNR ?-?(?:10|11|30|33|35|37)\b")
_NUMERO_NR = re.compile(r"\bNR ?-?(\d{2})\b")
_ASO_COM_CONCLUSAO = re.compile(r"CONCLUSAO / CONCLUSION|MEDICAL HEALTH CERTIFICATE|ATESTADO DE SAUDE OCUPACIONAL")
# Formulário "Trabalho em altura: ( ) Sim (x) Não": vale a marca ao lado de Sim/Não, se o OCR guardou.
_MARCA_SIM = re.compile(r"\(\s*X\s*\)\s*SIM")
_MARCA_NAO = re.compile(r"\(\s*X\s*\)\s*NAO")
# Condução e máquina móvel não têm linha de NR no ASO: vêm da função e dos riscos.
# "Colisão / abalroamento POR veículo" é risco de ser atingido, não de dirigir: não conta.
_CONDUCAO = re.compile(
    r"MOTORISTA|CONDUTOR|OPERACAO DE VEICULO|VEHICLE OPERATION|DIRECAO DE VEICULO|CONDUCAO DE VEICULO|DIRIGIR"
    r"|RAC ?2\b|VEICULOS AUTOMOTORES|\bCNH\b"
)
# Categoria C/D/E: caminhão, carreta, ônibus, van de passageiros ou a categoria escrita.
_CONDUCAO_CDE = re.compile(
    r"CAMINHAO|CARRET|ONIBUS|MICRO-? ?ONIBUS|\bVAN\b|BITREM|CAVALO MECANICO|TRUCK|CATEGORIA [CDE]\b|CNH[^A-Z]{0,4}[CDE]\b"
)
_MAQUINA_MOVEL = re.compile(r"EMPILHADEIRA|GUINDAST|PONTE ROLANTE|RETROESCAVADEIRA|MUNCK|PA CARREGADEIRA|TRATOR")


# Só a lista de NRs do ASO decide. Laudo psicológico e texto corrido citam a NR sem que ela seja da função
# ("Finalidade: Avaliação psicossocial, conforme NR 33/35", "## NR-33 e NR-35." no fecho do laudo).
_NR_FORA_DO_ASO = re.compile(r"CONFORME|FINALIDADE|PSICO|AVALIACAO|LAUDO|PORTARIA|APTIDAO NR|DE ACORDO")
# Nome da atividade na linha: a linha que só traz o número da NR ("## NR35") não é item da lista.
# Nome da atividade na linha: a linha que só traz o número da NR ("## NR35") não é item da lista.
_NOME_ATIVIDADE = re.compile(
    r"ALTURA|HEIGHT|CONFINAD|CONFINED|ELETRICIDADE|ELECTRICITY|OFFSHORE|TRANSBORDO|TRANSHIPMENT|BRIGADA|EMERGENCIA"
    r"|EMERGENCY|VEICULOS INDUSTRIAIS|INDUSTRIAL VEHICLE|EMBARQUE|AQUAVIARI"
)


def _texto_corrido(bruta: str) -> bool:
    """4+ palavras em minúsculas: frase de laudo, não item de lista ("Trabalho com Eletricidade / Working with
    Electricity" tem 2). Conta palavra de 5+ letras para não pegar "para"/"com" do item de lista de outro ASO
    ("Liberação para a atividade de trabalho em altura (NR35):")."""
    return len(re.findall(r"(?<![^\W\d_])[a-zà-ÿ]{5,}(?![^\W\d_])", bruta)) >= 4


def _atividades(texto: str, funcao: Optional[str], riscos: Optional[list[str]]) -> dict[str, str]:
    brutas = texto.splitlines()
    linhas = [_norm(l) for l in brutas]
    tem_aso = any(_ASO_COM_CONCLUSAO.search(l) for l in linhas)
    achadas: dict[str, str] = {}
    for bruta, l in zip(brutas, linhas):
        if not _LINHA_NR.search(l) or len(l) > 140:
            continue
        formulario = "SIM" in l and "NAO" in l  # "Apto para trabalho em altura (NR-35) ( ) Sim ( ) Não"
        if _NR_FORA_DO_ASO.search(l) or (not formulario and _texto_corrido(bruta)):
            continue
        if not _NOME_ATIVIDADE.search(l):
            continue
        numeros = {int(n) for n in _NUMERO_NR.findall(l)}
        for k, nr in ATIVIDADES_NR.items():
            if nr not in numeros:
                continue
            if formulario:
                if _MARCA_SIM.search(l):
                    achadas[k] = "sim"
                elif _MARCA_NAO.search(l):
                    achadas.setdefault(k, "nao")
            else:
                achadas[k] = "sim"
    out = {}
    for k in ATIVIDADES_NR:
        if k in achadas:
            out[k] = achadas[k]
        else:
            # ASO com conclusão e lista de NRs: a que não aparece não é da função.
            out[k] = "nao" if tem_aso else "nao_informado"
    contexto = " ".join([_norm(funcao or "")] + [_norm(r) for r in riscos or []])
    conhecido = bool(funcao or riscos)
    conduz = bool(re.search(_CONDUCAO, contexto))
    cde = conduz and bool(re.search(_CONDUCAO_CDE, contexto))
    out["condutor_cde"] = "sim" if cde else ("nao" if conhecido else "nao_informado")
    out["condutor_ab"] = "sim" if conduz and not cde else ("nao" if conhecido else "nao_informado")
    if re.search(_MAQUINA_MOVEL, contexto):
        out["operador_equipamento_pesado"] = "sim"
    return out


def _exames_no_texto(texto: str) -> list[str]:
    """Exame citado como título ou item de lista (lista de procedimentos do ASO, título de laudo).
    Completa o `exams_ocr` do ProntuAI, que vem do 4o mini e oscila (conferência de 18/11: acuidade,
    RX de tórax OIT e toxicológico com laudo no PDF e fora da lista). Linha longa (texto corrido) não conta."""
    from montar_features import EXAMES  # mesmos grupos da tabela
    achados = []
    for l in texto.splitlines():
        n = _norm(l).lstrip("# ").strip()
        if not n or len(n) > 80:
            continue
        # Frase da ficha ("Teste de Romberg negativo.") e termo de consentimento ("autorizo a realização do
        # exame toxicológico") citam o exame sem ser a lista nem o laudo dele.
        # Rodapé do laboratório ("R.T. UNIDADE TOXICOLOGICO", "Laboratório de Análises Clínicas e Toxicológicas").
        if re.search(r"NEGATIV|POSITIV|AUTORIZ|DECLARO|CIENTE|CONSENT|\bUNIDADE\b|LABORATORIO|ANALISES CLINICAS|\bCNES\b|CNPJ|^R\.? ?T?\.? |^DB\b", n) or len(re.findall(r"\b[a-zà-ÿ]{3,}\b", l)) >= 3:
            continue
        if any(rx.search(n) for rx in EXAMES.values()):
            achados.append(n)
    return achados


def _conclusoes(entrada: str) -> dict[str, Any]:
    """Conclusão escrita nos laudos de acuidade, audiometria, ECG e espirometria (qual_*.py)."""
    import qual_acuidade, qual_audiometria, qual_ecg, qual_espirometria, qual_rx, qual_eeg, qual_ergometrico, qual_psico, qual_odonto, qual_clinico, qual_urina
    out: dict[str, Any] = {}
    for mod in (qual_acuidade, qual_audiometria, qual_ecg, qual_espirometria, qual_rx, qual_eeg, qual_ergometrico, qual_psico,
                qual_odonto, qual_clinico, qual_urina):
        out.update(mod.ler(entrada))
    return out


def extrair_caso(doc: dict[str, Any], md: str) -> tuple[dict[str, Any], list[str]]:
    """(caso, blocos de conduta). `doc` é a linha do banco (id, data, exames)."""
    entrada, blocos = separar_rotulo(md)
    resultados = []
    for chave, leitura in ne.ler_valores(entrada).items():
        if leitura.valor is None:
            resultados.append({"parametro": chave, "texto": leitura.valor_texto})
        else:
            f = leitura.faixa
            resultados.append({
                "parametro": chave,
                "valor": leitura.valor,
                "ref_min": f.minimo if f else None,
                "ref_max": f.maximo if f else None,
                "teto_exclusivo": bool(f and f.teto_exclusivo),
            })
    caso = {
        "id": doc["document_id"],
        "data": doc.get("data"),
        "tipo_exame": _tipo(entrada),
        "funcao": _funcao(entrada),
        "riscos": _riscos(entrada),
        "atividades": None,  # preenchido abaixo
        "exames_pedidos": doc.get("exams_brnet") or [],
        "exames_realizados": (doc.get("exams_ocr") or []) + _exames_no_texto(entrada),
        "resultados": resultados,
        "ficha": _ficha_plana(doc["document_id"]),
    }
    caso["atividades"] = _atividades(entrada, caso["funcao"], caso["riscos"])
    caso["conclusoes"] = _conclusoes(entrada)
    return caso, blocos


# ---------------------------------------------------------------------------
# Rótulo
# ---------------------------------------------------------------------------

ESPECIALIDADES = {k: re.compile(v) for k, v in {
    # "CARDIOREGISTER"/"CARDICHOSISTER": OCR do manuscrito "cardiologista" na guia da clínica de Itaguaí (24/11).
    "cardiologia": r"CARDIOLOG|CARDI\w*GISTA|\bCARDIO\b|\bCARDI\w*IST\w{0,3}\b",
    "endocrinologia": r"ENDOCRIN|\bEN\w{0,3}OCRI",
    "oftalmologia": r"OFTALM|OFTAM|OPHT?HALM|GLAUCOMA",
    "otorrinolaringologia": r"OTORRINO|\bORL\b|OTOLARYNG|OTORHINO",
    # Só o pedido explícito. Os gatilhos genéricos estão em _CLINICA_GENERICA.
    "clinica_medica": r"CLINIC[OA] (?:GERAL|MEDIC)|CLINICA MEDICA|MEDICINA DE FAMILIA|\b(?:AO|PARA(?: O)?|COM(?: O)?) CLINICO\b"
                      r"|\bCLINICO ?/|/ ?CLINICO\b|OUTROS ?: ?CLINICO\b"
                      r"|INTERNAL ?MEDICINE|GENERAL PRACTITIONER"
                      # OCR de "Clínica médica" na carta impressa: CLMICA, CIINICA, CLTNICA, CLFNICA, CIMICA, "CLINICA IMIEDICA".
                      r"|\bC[LI1][A-Z']{1,3}CA\s*I?M\w{0,2}DICA\b|CLINICAMEDICA"
                      # Guia de Itaguaí "para esclarecimentos com clínico geral" manuscrito: CLINIC/LLINIC/AINIUS/CLININE
                      # GERAL/GENAL/GERUL; cartas "ao CLINICE MEDICA", "ao ULINICA MEDICA", "serviço de CLIMICA" (24/11).
                      r"|ESCLARECIMENTOS COM\s+(?:O |A )?\w{3,9}\s+GE[RN][AU]L\b|\b\w?[LI1]{1,2}NIC\w?\s+GE[RN][AU]L\b"
                      r"|\b(?:AO|A|DE|COM)\s+\w?[LI1]I?[NM]IC[AEO]?\s+M[EI]DIC|SERVICO DE CL[IM]{1,2}ICA\b",  # "ao clínico/endócrino", "Outros: clínico"
    "neurologia": r"NEUROLOG",
    "ortopedia": r"ORTOPED|ORTHOPED",
    "pneumologia": r"PNEUMO|PULMONOL",
    "gastroenterologia": r"GASTRO",
    "hepatologia": r"HEPATO",
    "urologia": r"UROLOG",
    "nefrologia": r"NEFRO|NEPHRO",
    # "Hematócrito" é parâmetro do hemograma citado na carta, não a especialidade (7117798, 24/11).
    "hematologia": r"HEMATO(?!CRITO)|(?<!D)EMATOLOG",  # OCR troca o H: "Orematologista"
    "infectologia": r"INFECTO|DEPARTAMENTO DE DIP\b",
    "dermatologia": r"DERMATO",
    "psiquiatria": r"PSIQUIAT|PSYCHIAT",
    "psicologia": r"PSICOLOGIA|PSYCHOLOG|AVALIACAO PSICOLOGICA COM|AO PSICOLOGO|PARA PSICOLOGO",
    "ginecologia": r"GINECO|GYN(?:A)?ECO",
    "angiologia_vascular": r"ANGIOLOG|VASCULAR|\bANGI\w{2,8}ISTA\b",
    "reumatologia": r"REUMATO|RHEUMATO",
    "fonoaudiologia": r"FONOAUDIOLOGIA|AO FONOAUDIOLOGO|PARA FONOAUDIOLOGO|AVALIACAO FONO",
    "odontologia": r"ODONTO|DENTISTA|DENTIST\b|DENTAL",
    "nutricao": r"NUTRI",
}.items()}

MOTIVOS = {k: re.compile(v) for k, v in {
    "glicemia": r"GLICEMIA|GLICOSE|GLUCOSE|GLYC?EMIA|DIABET|HIPERGLIC|\bDM ?2?\b",
    "hba1c": r"GLICADA|HBA1C",
    # "PRESSAO" só como palavra: DEPRESSAO/IMPRESSAO/COMPRESSAO/EXPRESSAO davam PA em toda carta de psiquiatria (24/11).
    "pressao_arterial": r"\bPA\b|(?<![A-Z])PRESSAO|BLOOD PRESSURE|HYPERTENS|HIPERTENS|\bHAS\b",
    "lipidograma": r"COLESTEROL|TRIGLICER|CHOLESTEROL|TRIGLYCER|DISLIPID|\bLDL\b|\bHDL\b",
    "hemograma": r"HEMOGRAMA|HEMOGLOBINA|ANEMIA|LEUCOCIT|PLAQUET|LEUKOCYT|PLATELET|BLOOD COUNT",
    "funcao_hepatica": r"\bTGO\b|\bTGP\b|\bGGT\b|TRANSAMINASE|HEPATIC",
    "funcao_renal": r"CREATININA|UREIA|RENAL|CREATININE|\bUREA\b",
    # Palavra inteira: "VISAO" dentro de REVISAO/SUPERVISAO/DIVISAO dava acuidade falsa em 27% dos encaminhados da
    # base de 10 mil (Breno, 23/11). "20/40" só fora de data ("20/10/2026") e de dose ("20/10 MG").
    "acuidade_visual": r"ACUIDADE(?!\s+(?:AUDITIVA|TEMPORAL))|\bVISUAL\b|\bVISAO\b|OFTALM"
                       r"|(?<![\d/])20/(?:25|30|40|50|60|70|80|100|200|400)(?![\d/]|\s*MG)",
    "audiometria": r"AUDIOMETR[IY]|HEARING LOSS|AUDITIV|AUDICAO|PAIR\b|DISACUSIA|HIPOACUSIA",
    "ecg": r"ELETROCARDIO|ELECTROCARDIO|\bECG\b|ARRITMIA|BLOQUEIO|TAQUICARD|BRADICARD|RITMO SINUSAL|INTERVALO PR|QRS|REPOLARIZA"
           r"|EXTRASSISTOL|PRE-? ?EXCITACAO|WOLFF|SOBRECARGA VENTRIC|FIBRILACAO|FLUTTER",
    "eeg": r"ELETROENCEFALO|\bEEG\b",
    "espirometria": r"ESPIROMETR|SPIROMETR|RESTRITIV|OBSTRUTIV|DISTURBIO VENTILAT",
    "rx": r"\bRX\b|RAIO|RADIOGRAFIA|X-? ?RAY",
    "imc": r"\bIMC\b|OBESIDADE|SOBREPESO|\bBMI\b|OBESITY|OVERWEIGHT",
}.items()}

# "Médico assistente", "avaliação médica", "exame clínico", PSF/UBS: aparecem na carta para o especialista
# ("Ao Pneumologista/Médico Assistente", "situação médica do paciente ao exame clínico"). Só viram clínica médica
# quando a carta não nomeia outra especialidade.
_CLINICA_GENERICA = re.compile(r"\bCLINICO\b|MEDICO ASSISTENTE|AVALIACAO MEDICA|\bPSF\b|\bUBS\b|AVALIA\W?\w{1,3}O CLINICA\b")

# OCR torto no nome da especialidade ou do exame ("Endorinologia", "gluemia jejum 102"): palavra de 7+ letras a
# distância de edição <= 2 de uma forma canônica, com a primeira letra igual ("CUIDADO" fica a 2 de "ACUIDADE").
# Só para palavra que nenhuma regex reconheceu; empate entre chaves diferentes não decide.
_CANONICAS_ESPECIALIDADE = {
    "endocrinologia": ("ENDOCRINOLOGIA", "ENDOCRINOLOGISTA"),
    "cardiologia": ("CARDIOLOGIA", "CARDIOLOGISTA"),
    "oftalmologia": ("OFTALMOLOGIA", "OFTALMOLOGISTA"),
    "otorrinolaringologia": ("OTORRINOLARINGOLOGIA", "OTORRINOLARINGOLOGISTA", "OTORRINO"),
    "neurologia": ("NEUROLOGIA", "NEUROLOGISTA"),
    "ortopedia": ("ORTOPEDIA", "ORTOPEDISTA"),
    "pneumologia": ("PNEUMOLOGIA", "PNEUMOLOGISTA"),
    "gastroenterologia": ("GASTROENTEROLOGIA", "GASTROENTEROLOGISTA"),
    "hepatologia": ("HEPATOLOGIA", "HEPATOLOGISTA"),
    "urologia": ("UROLOGIA", "UROLOGISTA"),
    "nefrologia": ("NEFROLOGIA", "NEFROLOGISTA"),
    "hematologia": ("HEMATOLOGIA", "HEMATOLOGISTA"),
    "infectologia": ("INFECTOLOGIA", "INFECTOLOGISTA"),
    "dermatologia": ("DERMATOLOGIA", "DERMATOLOGISTA"),
    "psiquiatria": ("PSIQUIATRIA", "PSIQUIATRA"),
    "ginecologia": ("GINECOLOGIA", "GINECOLOGISTA"),
    "angiologia_vascular": ("ANGIOLOGIA", "ANGIOLOGISTA"),
    "reumatologia": ("REUMATOLOGIA", "REUMATOLOGISTA"),
    # Fonoaudiologia fica de fora: "fonoaudióloga" assina o laudo de audiometria e está a 1 de "FONOAUDIOLOGIA".
}
_CANONICAS_MOTIVO = {
    "glicemia": ("GLICEMIA", "GLICOSE"),
    "acuidade_visual": ("ACUIDADE",),
    "audiometria": ("AUDIOMETRIA",),
    "ecg": ("ELETROCARDIOGRAMA",),
    "espirometria": ("ESPIROMETRIA",),
    "hemograma": ("HEMOGLOBINA",),
    "lipidograma": ("COLESTEROL", "TRIGLICERIDEOS"),
}
DISTANCIA_MAX = 2
PALAVRA_MIN = 7
# Palavra certa que fica perto de uma forma canônica: o aparelho do laudo de audiometria não é o exame, e
# "AUDIOLOGIA" (assinatura da fonoaudióloga) fica a 2 de "ANGIOLOGIA".
_NAO_CORRIGIR = {"AUDIOMETRO", "AUDIOMETROS", "AUDIOLOGIA", "AUDIOLOGO", "AUDIOLOGA"}


def _distancia(a: str, b: str, teto: int) -> int:
    """Levenshtein com corte: devolve teto + 1 assim que passa do teto."""
    if abs(len(a) - len(b)) > teto:
        return teto + 1
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        if min(atual) > teto:
            return teto + 1
        anterior = atual
    return anterior[-1]


def _aproximadas(texto: str, canonicas: dict[str, tuple[str, ...]], reconhecida) -> set[str]:
    achadas = set()
    for palavra in set(re.findall(rf"\b[A-Z]{{{PALAVRA_MIN},}}\b", texto)):
        if palavra in _NAO_CORRIGIR or reconhecida(palavra):
            continue
        melhor, chaves = DISTANCIA_MAX + 1, set()
        for chave, formas in canonicas.items():
            for forma in formas:
                if forma[0] != palavra[0]:
                    continue
                d = _distancia(palavra, forma, DISTANCIA_MAX)
                if d < melhor:
                    melhor, chaves = d, {chave}
                elif d == melhor:
                    chaves.add(chave)
        if melhor <= DISTANCIA_MAX and len(chaves) == 1:
            achadas |= chaves
    return achadas


def _reconhecida(palavra: str) -> bool:
    return any(rx.search(palavra) for rx in (*ESPECIALIDADES.values(), *MOTIVOS.values()))


_ACOMPANHAR = {k: re.compile(v) for k, v in {
    "refazer_exame": r"REPETIR|REFAZER|NOVA COLETA|NOVO EXAME|RECOLETA",
    "reavaliar": r"REAVALIA|CONTRA-?REFERENCIA|RETORNO COM|RETORNAR",
    "acompanhamento": r"ACOMPANHAMENTO|CONTROLE|MONITORA|SEGUIMENTO",
}.items()}

_VERBO = re.compile(r"\bI (?:HEREBY )?REFER\b|\bI AM REFERRING\b|\bREFERR?(?:ING)? (?:THIS|THE) (?:ABOVE|PATIENT|EMPLOYEE|WORKER)\b|RECOMENDACAO\s*:\s*AVALIACAO|SOLICITO (?:AVALIACAO|PARECER)|\bENCAMINER\w*|\bENCA?M+I?N?H(?:O|AMOS|AR|EI|ADO|ADA)\b|\bAOS CUIDADOS\b|\(\s*X\s*\)\s*ENCAMINHAD|ENCAMINHAMENTO (?:MEDICO|AO|A |PARA|CLINICO)")


_ROTULO_DE_CAMPO = re.compile(r"<!--[^>]*-->|OBSERVAC\w*|E/OU|ENCAMINHAMENTOS?|CONDUTA|PREVENCAO|ACOMPANHAMENTO|MARCA|\bOBS\b|[^A-Z]")


def _campo_vazio(bloco: str) -> bool:
    """Bloco que é só o rótulo de um campo de formulário, sem conteúdo escrito."""
    return len(_ROTULO_DE_CAMPO.sub("", _norm(bloco))) < 12


# Trechos que citam exame sem ser motivo (pendências do time de dados, 24/11, aba "motivo incoerente"):
# radiografia dentária pedida pelo dentista; "pressão" no sentido de cobrança; histórico/medicação da carta assistencial;
# "ECG 15" = escala de Glasgow.
_NAO_E_MOTIVO = re.compile(
    r"(?:RADIOGRAFI\w*|\bRX\b|RAIO.?X)\W+(?:\w+\W+){0,4}?(?:PERIAPIC\w*|PANORAM\w*|INTERPROXIM\w*|ELEMENTO|DENT\w*|EXODONT\w*)"
    r"|PERIAPIC\w*|PANORAMIC\w*|INTERPROXIM\w*|AVALIACAO RADIOGRAFICA"
    r"|SOB PRESSAO|PRESSAO (?:POR|NO TRABALHO|DE TRABALHO|PSICOLOGIC\w*|EMOCIONAL|SOCIAL|DE METAS|DA CHEFIA)|PRESSAO QUANDO"
    # Histórico só até o fim da frase/item, e nunca por cima dos resultados do exame ("último exame ... neste serviço: IMC 38").
    r"|(?:(?:HISTORIA PATOLOGICA PREGRESSA|ANTECEDENTES? (?:PESSOAIS|PATOLOGICOS)|HISTORICO FAMILIAR|OBSERVA\w* NO HISTORICO FAMILIAR)\s*:?"
    r"|\bMEDICA(?:COES|MENTOS)(?: EM USO)?\s*:)(?:(?!ULTIMO EXAME|NESTE SERVICO|ALTERAC|RESULTADO|HISTORIA DA DOENCA)[^.;]){0,100}"
    r"|\bECG\s*(?:DE\s*)?(?:1[0-5]|[3-9])\b(?![/\d]|[.,]\d)(?:\s*PONTOS)?|GLASGOW\s*\d*"
    # "Encaminho ao PA" = pronto atendimento; "pressão sonora" é do ruído (audiometria).
    r"|\b(?:AO|NO|PARA O|PELO) PA\b(?!\s*:?\s*\d)|PRESSAO SONORA"
    # Aviso em inglês do e-mail ("this email HAS originated from outside"): "HAS" não é hipertensão.
    r"|\bHAS (?:ORIGINATED|BEEN|THE|NOT)\b")
# PA normal citada nos sinais vitais da carta assistencial ("ao exame PA 110x70, SpO2 99%, FC 68"): não é motivo.
_PA_SINAIS = re.compile(r"(?:\bPA\b\s*)+:?\s*(\d{2,3})\s*[X/]\s*(\d{2,3})\s*(?:MM\s*H?G)?\s*[-/,;.]*\s*(?=SPO2|SAT|FC\b|TAX|\d{2,3}\s*BPM)")
_RX_NAO_DENTARIO = re.compile(r"TORAX|COLUNA|\bOIT\b|PULM|LOMBA|CERVIC|JOELHO|OMBRO|SEIOS? DA FACE|AORT")


def _sem_falsos_motivos(texto: str) -> str:
    texto = _NAO_E_MOTIVO.sub(" ", texto)
    return _PA_SINAIS.sub(lambda m: " " if int(m.group(1)) < 140 and int(m.group(2)) < 90 else m.group(0), texto)


def extrair_rotulo(blocos: list[str]) -> dict[str, Any]:
    # Formulário de caixinhas (Protemix): o risco à mão costuma apagar os parênteses da opção marcada, que
    # sai do OCR sem "( )" — e as demais ficam com "( )", removidas abaixo. Conferido no PDF (b3d4b8bc,
    # "Cardiologia" marcada). Não remover as opções sem parênteses.
    texto = _norm("\n".join(blocos))
    # Opções de formulário sem marca ("( ) CARDIOLOGIA") não contam.
    sem_vazias = _CAIXA_VAZIA.sub(" ", texto)
    especialidades = {k for k, rx in ESPECIALIDADES.items() if rx.search(sem_vazias)}
    especialidades |= _aproximadas(sem_vazias, _CANONICAS_ESPECIALIDADE, _reconhecida)
    if not especialidades and _CLINICA_GENERICA.search(sem_vazias):
        especialidades = {"clinica_medica"}
    especialidades = sorted(especialidades)
    # Trechos que citam visão sem ser motivo (anamnese, laudo psicológico, laudo de acuidade anexado à carta).
    limpo = _sem_falsos_motivos(_NAO_E_ACUIDADE.sub(" ", sem_vazias))
    motivos = {k for k, rx in MOTIVOS.items() if rx.search(limpo)}
    if "odontologia" in especialidades and not _RX_NAO_DENTARIO.search(limpo):
        motivos.discard("rx")  # RX citado em carta do dentista é radiografia dentária
    motivos = sorted(motivos | _aproximadas(limpo, _CANONICAS_MOTIVO, _reconhecida))
    acompanhar = sorted(k for k, rx in _ACOMPANHAR.items() if rx.search(sem_vazias))
    if _VERBO.search(sem_vazias) or especialidades or MARCA_EMAIL in texto:
        encaminhado = "sim"
    elif blocos and all(_campo_vazio(b) for b in blocos):
        # Campo de formulário sem nada escrito ("Encaminhamentos:", "Observações e/ou encaminhamentos:", "Conduta:
        # prevenção / acompanhamento / encaminhamento" do laudo de audiometria): na auditoria das pendências do Breno
        # (23/11) os 13 casos assim eram sem encaminhamento.
        encaminhado = "nao"
    elif blocos:
        encaminhado = "incerto"  # só título ou formulário vazio
    else:
        encaminhado = "nao"
    return {
        "rotulo_encaminhado": encaminhado,
        "rotulo_especialidades": "|".join(especialidades),
        "rotulo_exames_motivo": "|".join(motivos),
        "rotulo_acompanhar": "|".join(acompanhar),
        # situacao_aso do contrato em 2 níveis: LIBERADO (sem encaminhamento) e ENCAMINHADO (= LIBERADO_COM_
        # ENCAMINHAMENTO ou RETIDO). O OCR não diz qual dos dois: das 597 cartas, só 9 escrevem se o ASO fica
        # retido ou liberado, e o "Apto / Inapto" do ASO é caixinha que o OCR perde (medido em 18/11).
        "rotulo_conduta": {"sim": "ENCAMINHADO", "nao": "LIBERADO"}.get(encaminhado),
    }
