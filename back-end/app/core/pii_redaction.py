"""Redação de dados cadastrais antes de qualquer saída para a OpenAI.

O OCR devolve o markdown do documento inteiro — cabeçalho cadastral incluído.
Os identificadores (CPF, CNPJ, passaporte) e o nome do paciente já são
extraídos **localmente**, por regex e heurística (`extrair_cpf_regex`,
`patient_name_extractor`), antes de qualquer chamada a LLM. Logo, o que sai
para a OpenAI não precisa carregar nenhum desses campos: a extração de exames
só usa a lista de procedimentos.

Nenhum dado cadastral sai: o CPF também não, porque a extração dele é
exclusivamente local (`extrair_cpf_regex`, `extrair_todos_cpfs_regex`).

Este módulo é a camada que separa as duas coisas. A regra de ouro é preservar
tudo que pareça exame e apagar tudo que pareça cadastro — na dúvida entre
apagar um exame e vazar um dado, o desenho erra para o lado de vazar menos
contexto, nunca para o lado de destruir uma linha de exame.

Estratégia em três passadas, nesta ordem:

1. **Campos rotulados** (`Nome: ...`, `CPF ...`): apaga o *valor* que segue o
   rótulo. É a passada que pega dado cadastral livre, como endereço e nome da
   mãe, que nenhum padrão de valor reconheceria.
2. **Padrões de valor** (CPF, CNPJ, e-mail, telefone, CEP, data): pega o que
   aparece solto, fora de campo rotulado — rodapé, carimbo, cabeçalho repetido.
3. **Valores já conhecidos**: o nome e os identificadores que o pipeline local
   extraiu são apagados em *todas* as ocorrências. É o que cobre a repetição do
   nome em cabeçalho e rodapé de cada página, onde não há rótulo nenhum.
"""

import logging
import re
import unicodedata
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Marcadores. O formato com colchetes é reconhecível pelo modelo como lacuna e
# é filtrado na saída (ver `filtrar_exames`), de modo que um marcador jamais
# vira "exame" mesmo que o modelo o liste por engano.
NOME = "[NOME]"
CPF = "[CPF]"
CNPJ = "[CNPJ]"
IDENTIFICADOR = "[ID]"
DATA = "[DATA]"
TELEFONE = "[TELEFONE]"
EMAIL = "[EMAIL]"
ENDERECO = "[ENDERECO]"
EMPRESA = "[EMPRESA]"
DADO = "[DADO]"

MARCADORES = (
    NOME, CPF, CNPJ, IDENTIFICADOR, DATA,
    TELEFONE, EMAIL, ENDERECO, EMPRESA, DADO,
)

# Rótulos que dispensam dois-pontos: o Textract junta colunas na mesma linha
# ("Nome FULANO DE TAL Empresa ACME LTDA"), então exigir pontuação perderia
# justamente o cabeçalho cadastral. Só entram aqui palavras que não aparecem em
# nome de exame — "FUNÇÃO" e "MÉDICO", por exemplo, ficam de fora de propósito
# (existe "PROVA DE FUNÇÃO PULMONAR" e "CLÍNICO/MÉDICO OCUPACIONAL").
_ROTULOS_ANCORA = {
    "nome do paciente": NOME,
    "nome do funcionario": NOME,
    "nome do colaborador": NOME,
    "nome completo": NOME,
    "nome / name": NOME,
    "nome/name": NOME,
    "nome da mae": NOME,
    "nome do pai": NOME,
    "nome": NOME,
    "paciente": NOME,
    "funcionario": NOME,
    "empresa": EMPRESA,
    "razao social": EMPRESA,
    "empregador": EMPRESA,
    "cpf": CPF,
    "cpf / passport": CPF,
    "cpf/passport": CPF,
    "cnpj": CNPJ,
    "rg": IDENTIFICADOR,
    "identidade": IDENTIFICADOR,
    "id number": IDENTIFICADOR,
    "cns": IDENTIFICADOR,
    "cartao nacional de saude": IDENTIFICADOR,
    "pis": IDENTIFICADOR,
    "pasep": IDENTIFICADOR,
    "ctps": IDENTIFICADOR,
    "matricula": IDENTIFICADOR,
    "passaporte": IDENTIFICADOR,
    "passport": IDENTIFICADOR,
    "data de nascimento": DATA,
    "nascimento / birth": DATA,
    "nascimento": DATA,
    "data nasc": DATA,
    "nasc": DATA,
    "birth": DATA,
    "endereco": ENDERECO,
    "logradouro": ENDERECO,
    "bairro": ENDERECO,
    "cep": ENDERECO,
    "telefone": TELEFONE,
    "celular": TELEFONE,
    "contato": TELEFONE,
    "fone": TELEFONE,
    "tel": TELEFONE,
    "whatsapp": TELEFONE,
    "e-mail": EMAIL,
    "email": EMAIL,
    "crm": IDENTIFICADOR,
    "coren": IDENTIFICADOR,
}

# Rótulos que só valem com dois-pontos logo depois. São os que colidem com
# vocabulário de exame, e a exigência de pontuação é o que separa os dois usos:
# "Médico: Dr. Fulano" é cadastro, mas "## Laudo Médico - ELETROCARDIOGRAMA" e
# "## MÉDICO OCUPACIONAL" são exame — sem essa regra, o nome do exame era
# apagado junto. Mesma lógica para "FUNÇÃO" ("PROVA DE FUNÇÃO PULMONAR").
# O nome do médico que escapa daqui é pego pelo padrão "Dr./Dra." mais abaixo.
_ROTULOS_COM_SEPARADOR = {
    "medico": NOME,
    "medico examinador": NOME,
    "medico responsavel": NOME,
    "medico do trabalho": NOME,
    "mae": NOME,
    "pai": NOME,
    "responsavel": NOME,
    "colaborador": NOME,
    "trabalhador": NOME,
    "funcao": DADO,
    "cargo": DADO,
    "setor": DADO,
    "idade": DADO,
    "sexo": DADO,
    "genero": DADO,
    "nacionalidade": DADO,
    "estado civil": DADO,
}


def _normalizar_rotulo(texto: str) -> str:
    """Caixa baixa sem acento — a chave com que os dicionários acima são lidos."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def _alternativa_de_rotulos(rotulos: Iterable[str]) -> str:
    """Alternação regex dos rótulos, do mais longo para o mais curto.

    A ordem importa: sem ela, "nome" casaria antes de "nome do paciente" e o
    valor redigido começaria em "do paciente:", deixando o nome no texto.
    """
    padroes = []
    for rotulo in sorted(rotulos, key=len, reverse=True):
        # O rótulo é normalizado (sem acento); o texto real pode ter acento e
        # espaçamento irregular do OCR, daí a classe por caractere.
        partes = []
        for palavra in rotulo.split(" "):
            partes.append("".join(_classe_de_caractere(c) for c in palavra))
        padroes.append(r"\s*".join(partes))
    return "|".join(padroes)


_VARIANTES_ACENTUADAS = {
    "a": "aáàâãä",
    "e": "eéèêë",
    "i": "iíìîï",
    "o": "oóòôõö",
    "u": "uúùûü",
    "c": "cç",
    "n": "nñ",
}


def _classe_de_caractere(caractere: str) -> str:
    """Classe regex que aceita o caractere com e sem acento, em qualquer caixa.

    O mesmo nome aparece acentuado numa página e sem acento na outra conforme o
    OCR lê o documento; casar só a forma literal deixaria metade das ocorrências
    no texto enviado.
    """
    base = _normalizar_rotulo(caractere)
    variantes = _VARIANTES_ACENTUADAS.get(base)
    if not variantes:
        return re.escape(caractere)
    return f"[{variantes}{variantes.upper()}]"


# O preenchimento com pontos é o padrão dos laudos de laboratório
# ("Paciente....:", "CPF.........:"). Tolerar só um ponto fazia a regra de campo
# não disparar nessas páginas, e era por aí que o nome do paciente escapava.
_PREENCHIMENTO = r"[ \t._]*"
_SEPARADOR = rf"{_PREENCHIMENTO}[:\-–][ \t]*|[ \t]+"

_ROTULO_ANCORA_RE = re.compile(
    rf"(?<![0-9A-Za-zÀ-ÿ])(?:{_alternativa_de_rotulos(_ROTULOS_ANCORA)})"
    rf"(?![0-9A-Za-zÀ-ÿ])(?:{_SEPARADOR})",
    flags=re.IGNORECASE,
)

_ROTULO_COM_SEPARADOR_RE = re.compile(
    rf"(?<![0-9A-Za-zÀ-ÿ])(?:{_alternativa_de_rotulos(_ROTULOS_COM_SEPARADOR)})"
    rf"(?![0-9A-Za-zÀ-ÿ]){_PREENCHIMENTO}:[ \t]*",
    flags=re.IGNORECASE,
)

# Padrões de valor soltos, aplicados fora de campo rotulado.
# "Dr." / "Dra." seguido de nome próprio: cobre a assinatura do laudo, onde o
# nome do médico aparece sem rótulo de campo. Não colide com exame — nenhum
# nome de procedimento começa por "Dr".
# Token de nome próprio: aceita ponto interno ("J.C.", "F.dos") porque é assim
# que a assinatura do laudo sai do OCR — sem isso o padrão parava na inicial e
# o sobrenome do médico ficava no texto.
_TOKEN_DE_NOME = r"(?:[A-ZÀ-Ý][A-Za-zÀ-ÿ'`´^~.]*|d[aeo]s?|e)"
_DOUTOR_RE = re.compile(
    # Espaço explícito em vez de \s: o nome não atravessa quebra de linha, ou o
    # padrão engoliria o rótulo da linha seguinte junto com o nome.
    rf"\bDr[a]?\.?[ \t]+{_TOKEN_DE_NOME}(?:[ \t.]*{_TOKEN_DE_NOME}){{0,6}}"
)
_LOGRADOURO_RE = re.compile(
    r"(?im)^[ \t>*#|]*(?:rua|av\.?|avenida|travessa|trav\.?|rodovia|rod\.?|estrada|"
    r"alameda|al\.?|praca|praça|largo|quadra|qd\.?)\b[^\n]*"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_CEP_RE = re.compile(r"\b\d{5}[-\s]?\d{3}\b")
_TELEFONE_RE = re.compile(r"(?:\(\d{2}\)[ \t]*|\b(?:\+55[ \t]*)?\d{2}[ \t])9?\d{4}[-\s]?\d{4,5}")
_DATA_RE = re.compile(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b")
_CPF_SOLTO_RE = re.compile(r"\b\d{3}[.\s-]{0,3}\d{3}[.\s-]{0,3}\d{3}[.\s-]{0,3}\d{2}\b")
_CNPJ_SOLTO_RE = re.compile(r"\b\d{2}[.\s-]{0,3}\d{3}[.\s-]{0,3}\d{3}[/\s-]{0,3}\d{4}[-\s]{0,3}\d{2}\b")


def _apenas_digitos(valor: Optional[str]) -> str:
    return re.sub(r"\D", "", valor or "")


def _redigir_campos_rotulados(linha: str) -> str:
    """Apaga o valor que segue cada rótulo de campo encontrado na linha.

    O valor vai do fim do rótulo até o início do próximo rótulo da mesma linha
    (ou até o fim dela). É o que resolve a coluna dupla do Textract, em que
    "Nome FULANO Empresa ACME" é uma linha só com dois campos.
    """
    ocorrencias = []
    for regex in (_ROTULO_ANCORA_RE, _ROTULO_COM_SEPARADOR_RE):
        for match in regex.finditer(linha):
            rotulo = _normalizar_rotulo(match.group(0).rstrip(" \t:-–."))
            marcador = _ROTULOS_ANCORA.get(rotulo) or _ROTULOS_COM_SEPARADOR.get(rotulo)
            if marcador:
                ocorrencias.append((match.start(), match.end(), marcador))

    if not ocorrencias:
        return linha

    # Ordena e descarta sobreposições: "nome do paciente" e "paciente" casam no
    # mesmo trecho, e vale a que começa antes (a mais específica).
    ocorrencias.sort(key=lambda item: (item[0], -item[1]))
    selecionadas = []
    limite = -1
    for inicio, fim, marcador in ocorrencias:
        if inicio < limite:
            continue
        selecionadas.append((inicio, fim, marcador))
        limite = fim

    partes = []
    cursor = 0
    for indice, (inicio, fim, marcador) in enumerate(selecionadas):
        proximo_inicio = (
            selecionadas[indice + 1][0] if indice + 1 < len(selecionadas) else len(linha)
        )
        valor = linha[fim:proximo_inicio]
        partes.append(linha[cursor:fim])
        if not valor.strip():
            partes.append(valor)
        else:
            # Preserva o espaçamento final para não colar o marcador no rótulo
            # seguinte quando o OCR juntou colunas.
            sufixo = valor[len(valor.rstrip()):]
            partes.append(marcador + sufixo)
        cursor = proximo_inicio

    partes.append(linha[cursor:])
    return "".join(partes)


def _redigir_valores_soltos(texto: str, preservar_datas: bool) -> str:
    """Apaga identificadores que aparecem fora de campo rotulado."""
    texto = _LOGRADOURO_RE.sub(ENDERECO, texto)
    texto = _DOUTOR_RE.sub(f"Dr. {NOME}", texto)
    texto = _EMAIL_RE.sub(EMAIL, texto)
    texto = _CNPJ_SOLTO_RE.sub(CNPJ, texto)
    texto = _CPF_SOLTO_RE.sub(CPF, texto)
    texto = _TELEFONE_RE.sub(TELEFONE, texto)
    texto = _CEP_RE.sub(ENDERECO, texto)
    # A data entra por último: o padrão dela casaria pedaços de CPF/CNPJ
    # pontuados se rodasse antes.
    #
    # `preservar_datas` existe por uma medição, não por gosto: trocar a data
    # solta por marcador fazia o modelo **descartar a linha inteira** do exame,
    # porque "NOME DO EXAME - DATA" é uma das âncoras do prompt de extração.
    # Nos documentos reais isso derrubava "CLÍNICO OCUPACIONAL". A data que é
    # dado cadastral — a de nascimento — vem sempre rotulada ("Dt. Nasc.:",
    # "Data de Nascimento:") e continua sendo apagada pela passada de campos;
    # o que sobrevive aqui é data de realização de exame e de emissão de laudo.
    if not preservar_datas:
        texto = _DATA_RE.sub(DATA, texto)
    return texto


# Partículas de nome não valem como evidência: "DA SILVA" não identifica ninguém
# e sozinhas causariam redação de texto comum.
_PARTICULAS_DE_NOME = {"da", "de", "do", "das", "dos", "e", "di", "du", "van", "von"}


def _regex_de_valor_conhecido(valor: str) -> Optional[re.Pattern]:
    """Regex tolerante para apagar um valor já extraído em todas as ocorrências."""
    valor = (valor or "").strip()
    if len(valor) < 3:
        return None

    digitos = _apenas_digitos(valor)
    if digitos and len(digitos) == len(valor.replace(" ", "")):
        # Identificador numérico: aceita qualquer pontuação entre os dígitos,
        # porque o mesmo CPF sai "123.456.789-09" numa página e "12345678909"
        # na outra.
        return re.compile(r"[.\-/\s]{0,3}".join(re.escape(d) for d in digitos))

    tokens = [_regex_de_token(token) for token in valor.split()]
    if not tokens:
        return None
    # IGNORECASE é obrigatório: o nome sai em caixa alta no cabeçalho e em caixa
    # mista na assinatura ("YANE NUNES ALMEIDA" vs "Yane Nunes Almeida"), e sem
    # a flag a segunda forma escapava inteira.
    return re.compile(r"\s+".join(tokens), re.IGNORECASE)


def _regex_de_token(token: str) -> str:
    return "".join(_classe_de_caractere(c) for c in token)


def _regexes_tolerantes_a_espaco(valor: str) -> list[re.Pattern]:
    """Sequência completa de letras do nome, mais um prefixo longo.

    O prefixo existe porque o OCR corrompe o fim do nome na área de assinatura
    ("Severo dos Serntor" em vez de "Severo dos Santos"): a sequência inteira
    deixa de casar e a ocorrência sobrevive inteira. Com o prefixo, o que resta
    no texto é a cauda já ilegível.
    """
    padroes = []
    completo = _regex_tolerante_a_espaco(valor)
    if completo:
        padroes.append(completo)

    letras = [c for c in valor if c.isalpha()]
    if len(letras) >= 16:
        prefixo = _regex_tolerante_a_espaco("".join(letras[:12]))
        if prefixo:
            padroes.append(prefixo)
    return padroes


def _regex_tolerante_a_espaco(valor: str) -> Optional[re.Pattern]:
    """Casa o nome independentemente de como o OCR separou as letras.

    O mesmo documento traz o nome colado na página do voucher
    ("DARLANSEVERODOSSANTOS") e espaçado nas páginas de laudo
    ("DARLAN SEVERO DOS SANTOS"). Comparar a forma extraída letra a letra,
    com separador opcional entre elas, cobre as duas — e também o preenchimento
    por pontos.

    Só para valores longos: numa sequência curta o separador opcional casaria
    letras avulsas espalhadas por texto comum.
    """
    letras = [c for c in valor if c.isalpha()]
    if len(letras) < 8:
        return None
    # Uma quebra de linha é tolerada entre letras porque o OCR parte o nome em
    # duas linhas na área de assinatura ("Darlan" / "Severo dos Santos"). Uma
    # só, e não `\s*`, para o padrão não varrer letras avulsas página afora.
    separador = r"[ \t.\-]*\n?[ \t.\-]*"
    return re.compile(
        separador.join(_classe_de_caractere(c) for c in letras), re.IGNORECASE
    )


def _regexes_de_nome(valor: str) -> list[re.Pattern]:
    """Nome completo mais cada par de tokens vizinhos.

    O par existe porque o OCR corrompe um pedaço do nome ("Yane Nunes Almeidc"),
    e aí o nome completo não casa e a ocorrência inteira sobrevive. Com o par,
    o que resta é um token solto e truncado.

    É par, e não token isolado, de propósito: "ROSA" sozinho apagaria o exame
    "ROSA DE BENGALA". Duas palavras seguidas do nome da pessoa não acontecem
    por acaso num nome de exame.
    """
    tokens = [t for t in valor.split() if t]
    if len(tokens) < 2:
        return []

    padroes = []
    for primeiro, segundo in zip(tokens, tokens[1:]):
        if primeiro.lower() in _PARTICULAS_DE_NOME and segundo.lower() in _PARTICULAS_DE_NOME:
            continue
        if len(primeiro) < 2 or len(segundo) < 2:
            continue
        padroes.append(
            re.compile(
                rf"{_regex_de_token(primeiro)}\s+{_regex_de_token(segundo)}",
                re.IGNORECASE,
            )
        )
    return padroes


def _marcador_para_valor(valor: str) -> str:
    digitos = _apenas_digitos(valor)
    if len(digitos) == 11 and digitos == valor.replace(".", "").replace("-", "").replace(" ", ""):
        return CPF
    if len(digitos) == 14 and not re.search(r"[A-Za-z]", valor):
        return CNPJ
    if re.search(r"[A-Za-z]", valor) and not digitos:
        return NOME
    return IDENTIFICADOR


def redigir_para_llm(
    texto: str,
    valores_conhecidos: Iterable[Optional[str]] = (),
    preservar_datas: bool = False,
) -> str:
    """Devolve o texto sem dados cadastrais, pronto para sair para a OpenAI.

    `valores_conhecidos` recebe o que o pipeline local já extraiu (nome do
    paciente, CPF, CNPJ, passaporte): são apagados em todas as ocorrências,
    inclusive onde não há rótulo. `preservar_datas=True` mantém datas soltas (a
    de nascimento continua caindo pela regra de campo rotulado); ver o
    comentário em `_redigir_valores_soltos` para o motivo medido.
    """
    if not texto:
        return texto

    redigido = "\n".join(
        _redigir_campos_rotulados(linha) for linha in texto.splitlines()
    )
    redigido = _redigir_valores_soltos(redigido, preservar_datas)

    for valor in valores_conhecidos:
        if not valor:
            continue
        texto_valor = str(valor)
        marcador = _marcador_para_valor(texto_valor)
        regex = _regex_de_valor_conhecido(texto_valor)
        if regex:
            redigido = regex.sub(marcador, redigido)
        if marcador == NOME:
            for tolerante in _regexes_tolerantes_a_espaco(texto_valor):
                redigido = tolerante.sub(marcador, redigido)
            for par in _regexes_de_nome(texto_valor):
                redigido = par.sub(marcador, redigido)

    return redigido


def contem_marcador(valor: Optional[str]) -> bool:
    """True se o valor for (ou contiver) um marcador de redação.

    Usado para descartar da resposta do modelo qualquer item que seja eco de um
    marcador, em vez de conteúdo real do documento.
    """
    if not valor:
        return False
    return any(marcador in valor.upper() for marcador in MARCADORES)


# Dígito verificador, reimplementado aqui de propósito: `ocr_service` importa
# este módulo, então importar de lá fecharia um ciclo. São ~15 linhas estáveis
# (a regra do CPF/CNPJ não muda) e o custo da duplicação é menor que o de
# inverter a dependência só por isso.
def _digito_verificador_de_cpf_valido(valor: str) -> bool:
    digitos = _apenas_digitos(valor)
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    numeros = [int(d) for d in digitos]
    for indice in (9, 10):
        soma = sum(numeros[pos] * (indice + 1 - pos) for pos in range(indice))
        esperado = (soma * 10) % 11
        if esperado == 10:
            esperado = 0
        if numeros[indice] != esperado:
            return False
    return True


def _digito_verificador_de_cnpj_valido(valor: str) -> bool:
    digitos = _apenas_digitos(valor)
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False
    numeros = [int(d) for d in digitos]
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(numeros[i] * pesos[i] for i in range(tamanho))
        resto = soma % 11
        esperado = 0 if resto < 2 else 11 - resto
        if numeros[tamanho] != esperado:
            return False
    return True


class VazamentoDeDadoCadastral(RuntimeError):
    """Payload reprovado na conferência antes de sair para a OpenAI."""


# Conferência de saída. As regras de redação são heurísticas e um layout novo
# pode trazer um campo em forma que nenhuma delas alcança; esta função é o que
# transforma "as regras provavelmente pegaram" em "foi conferido nesta chamada".
#
# Confere duas classes:
#   - o que é verificável sozinho (CPF/CNPJ com dígito válido, e-mail, telefone,
#     CEP), independente de rótulo, layout ou emissor;
#   - o que o pipeline local já extraiu daquele documento (nome, CPF, CNPJ,
#     passaporte) — se está no payload, a redação falhou naquele caso concreto.
#
# Falha fechada de propósito: `extrair_exames_ia` já converte exceção em
# "sem exames", e o filtro determinístico do `workflow_service` recupera os
# exames do markdown cru, que é local. Ou seja, o pior caso é perder a sugestão
# do LLM — nunca vazar.
def verificar_payload(texto: str, valores_conhecidos: Iterable[Optional[str]] = ()) -> None:
    """Levanta `VazamentoDeDadoCadastral` se sobrou cadastro no texto."""
    if not texto:
        return

    achados: list[str] = []

    for rotulo, regex, validador in (
        ("CPF", _CPF_SOLTO_RE, _digito_verificador_de_cpf_valido),
        ("CNPJ", _CNPJ_SOLTO_RE, _digito_verificador_de_cnpj_valido),
    ):
        for encontrado in regex.findall(texto):
            if validador(encontrado):
                achados.append(rotulo)
                break

    for rotulo, regex in (
        ("e-mail", _EMAIL_RE),
        ("telefone", _TELEFONE_RE),
        ("CEP", _CEP_RE),
    ):
        if regex.search(texto):
            achados.append(rotulo)

    for valor in valores_conhecidos:
        if not valor or len(str(valor)) < 4:
            continue
        regex = _regex_de_valor_conhecido(str(valor))
        if regex and regex.search(texto):
            achados.append("valor extraído do documento")
            continue
        if any(t.search(texto) for t in _regexes_tolerantes_a_espaco(str(valor))):
            achados.append("nome extraído do documento")
            continue
        for par in _regexes_de_nome(str(valor)):
            if par.search(texto):
                achados.append("nome extraído do documento")
                break

    if achados:
        # A mensagem nomeia o tipo, nunca o valor: ela vai para log.
        raise VazamentoDeDadoCadastral(
            "Dado cadastral sobreviveu à redação: " + ", ".join(sorted(set(achados)))
        )
