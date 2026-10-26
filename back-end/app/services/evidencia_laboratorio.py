"""
Evidência de resultado para exame de LABORATÓRIO dado como encontrado.

O erro medido: a comparação dá como encontrado um exame cujo nome só aparece na
lista "Procedimentos realizados / Exames complementares" do ASO, sem o laudo. O
markdown traz só `## URÉIA 15/10/2026` e Ureia sai encontrada — a varredura
aceitava a DATA como se fosse valor de resultado.

Para laboratório o laudo tem forma estável: o resultado vem perto do nome do
analito, com unidade ("UREIA ... 32 mg/dL") ou com o rótulo do laudo
("RESULTADO 93", "VALORES DE REFERÊNCIA"). Esta regra procura isso, depois de
APAGAR as datas da janela, e devolve:

  "com_resultado"  alguma ocorrência do nome tem resultado logo depois;
  "so_lista"       o nome aparece, mas nenhuma ocorrência tem resultado;
  None             o nome nem aparece no texto: a regra não opina.

É só um selo. Não muda status, faltantes nem validation_status: o chamador grava
a evidência no item e limita a confiança. Não chama API e não envia dado a
ninguém; roda sobre o markdown local.

Medido por replay no texto gravado da cópia de produção de 22/10/2026, contra o
modal de feedback: pega 7 de 7 exames de laboratório que o revisor marcou "Não
estava" (ENCONTRADO_INCORRETO) e sela à toa 63 exames em 40 de 545 documentos
aprovados corretamente. Mexer nas listas ou na janela sem medir de novo muda
esses números — `scripts/replay_evidencia_laboratorio.py` refaz a conta.
"""
from __future__ import annotations

import os
import re
import unicodedata
from bisect import bisect_right
from typing import Any, Callable, Iterable, Optional

# Desliga a regra sem deploy de código: EVIDENCIA_LABORATORIO=false.
HABILITADA = os.getenv("EVIDENCIA_LABORATORIO", "true").strip().lower() not in ("0", "false", "nao", "no")

SO_LISTA = "so_lista"
COM_RESULTADO = "com_resultado"
# Justificativa do item "so_lista", no lugar da frase da comparação.
JUSTIFICATIVA_SO_LISTA = (
    "O nome do exame só aparece na lista de procedimentos do ASO; nenhum resultado "
    "foi encontrado no PDF. Confira se o laudo foi anexado."
)

# Caracteres do texto normalizado olhados depois de cada ocorrência do nome. O
# laudo de laboratório põe o resultado na mesma linha ou na seguinte; 250 cobre a
# tabela "EXAME / RESULTADO / UNIDADE / REFERÊNCIA" do OCR sem alcançar o exame
# vizinho na maioria dos laudos.
JANELA_RESULTADO = 250
LIMITE_LINHA_ORIGEM = 160
# Termo com menos de 3 caracteres casa por acidente em texto corrido.
MIN_TERMO = 3

# ---------------------------------------------------------------------------
# Quem é laboratório
# ---------------------------------------------------------------------------

# Casa contra o nome normalizado do exame do BRNET. A lista é a do protótipo
# medido; cada entrada é palavra inteira.
_LABORATORIO = re.compile(
    r"\b("
    # função renal e metabólica
    r"UREIA|CREATININA|ACIDO URICO|GLICEMIA|GLICOSE|HEMOGLOBINA GLICADA"
    # lipídios
    r"|COLESTEROL|TRIGLICERIDEOS|HDL|LDL"
    # hematologia
    r"|HEMOGRAMA|RETICULOCITOS|PLAQUETAS|FERRITINA"
    # função hepática: GAMA cobre "GAMA GT"/"GAMA GLUTAMIL"
    r"|TGO|TGP|GAMA|GGT|BILIRRUBINA|FOSFATASE"
    # hormônios e marcadores
    r"|TSH|T4|PSA"
    # eletrólitos e metais
    r"|POTASSIO|SODIO|CALCIO|ZINCO|CHUMBO"
    # sorologia
    r"|VDRL"
    # ACIDO solto pega os indicadores biológicos de urina (hipúrico, metil-hipúrico,
    # trans-mucônico), que também trazem resultado com unidade.
    r"|ACIDO"
    r")\b"
)

# Termos extras que provam o exame pelo laudo dos componentes. A glicemia de
# jejum sai no laudo como "Glicose"; o hemograma, pelas séries. Os outros são o
# nome que o laboratório imprime e o BRNET não usa — cada um veio de um selo à
# toa conferido no texto (26/10/2026): "Gama glutamil transferase", a grafia
# "Triglicerides" e o "HbA1c" do laudo de hemoglobina glicada.
_TERMOS_EXTRAS: tuple[tuple[str, frozenset[str]], ...] = (
    ("GLICEMIA", frozenset({"GLICOSE"})),
    ("HEMOGRAMA", frozenset({"ERITROGRAMA", "LEUCOGRAMA", "HEMACIAS", "HEMATOCRITO", "PLAQUETAS"})),
    ("GGT", frozenset({"GAMA GLUTAMIL", "GAMA GLUTAMILTRANSFERASE"})),
    ("TRIGLICERIDEOS", frozenset({"TRIGLICERIDES", "TRIGLICERIDIOS"})),
    ("HEMOGLOBINA GLICADA", frozenset({"HBA1C", "A1C"})),
)

# ---------------------------------------------------------------------------
# O que é resultado
# ---------------------------------------------------------------------------

# Datas saem da janela antes de procurar resultado: "UREIA 15/10/2026" não pode
# virar "15" seguido de unidade nem número solto.
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}/\d{2,4}\b")
# O texto normalizado só tem A-Z, 0-9, "/" e espaço. O "%" vira a palavra PCT em
# `normalizar`, senão o "5,6%" da hemoglobina glicada não seria resultado.
_RESULTADO = re.compile(
    r"RESULTADO\s+\d|VALOR(ES)? DE REFERENCIA"
    r"|\d+([.,]\d+)?\s*(MILHOES|MIL/MM3|/MM3|/UL|UI/ML|UI ML|MUI/L|UUI/ML|PUI/ML|UI|MG/DL|MG DL"
    r"|G/DL|G DL|U/L|U L|UI/L|MUI|NG/ML|NG ML|UG/DL|UG DL|%|MM3|MIL|MMOL|MEQ|PG|FL|UG/G|MG/G|PCT)\b"
)

_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")


def normalizar(texto: str) -> str:
    """Sem acento, maiúsculo, só A-Z, 0-9 e "/" (para as unidades), espaço simples.
    O "%" vira " PCT " para continuar contando como unidade."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    texto = texto.replace("%", " PCT ")
    return re.sub(r"[^A-Z0-9/]+", " ", texto).strip()


def chave_catalogo(texto: str) -> str:
    """Nome no formato de `name_normalized` do catálogo (sem a "/")."""
    return re.sub(r"\s+", " ", normalizar(texto).replace("/", " ")).strip()


def eh_laboratorio(exame: str) -> bool:
    return bool(_LABORATORIO.search(normalizar(exame)))


def termos_do_exame(exame: str, sinonimos: Iterable[str] = ()) -> set[str]:
    """
    Termos de busca: o nome do BRNET, o nome sem parênteses, cada parte entre
    parênteses, as variações do catálogo e os extras de `_TERMOS_EXTRAS`.
    """
    nome = normalizar(exame)
    termos = {nome, normalizar(re.sub(r"\(.*?\)", "", exame or ""))}
    termos |= {normalizar(p) for p in re.findall(r"\((.*?)\)", exame or "")}
    termos |= {normalizar(s) for s in sinonimos}
    for gatilho, extras in _TERMOS_EXTRAS:
        if gatilho in nome:
            termos |= extras
    return {t for t in termos if len(t) >= MIN_TERMO}


def mascarar_linha(linha: str) -> str:
    """Linha do markdown pronta para gravar: CPF mascarado, no máximo 160 caracteres."""
    linha = _CPF.sub("***.***.***-**", re.sub(r"\s+", " ", linha or "").strip())
    return linha[:LIMITE_LINHA_ORIGEM]


class MarkdownIndexado:
    """
    O markdown normalizado inteiro, com o mapa de volta para a linha crua.

    Normalizar linha a linha e juntar com espaço dá o mesmo texto que normalizar
    o documento de uma vez (quebra de linha também vira espaço), e permite saber
    de que linha veio cada ocorrência. Montado uma vez por documento.
    """

    def __init__(self, markdown: str):
        partes: list[str] = []
        self._inicios: list[int] = []
        self._linhas: list[str] = []
        posicao = 0
        for crua in (markdown or "").splitlines():
            norm = normalizar(crua)
            if not norm:
                continue
            self._inicios.append(posicao)
            self._linhas.append(crua)
            partes.append(norm)
            posicao += len(norm) + 1
        self.texto = " ".join(partes)

    def linha_em(self, posicao: int) -> str:
        return self._linhas[bisect_right(self._inicios, posicao) - 1]

    def ocorrencias(self, termos: Iterable[str]) -> list[re.Match]:
        """Ocorrências de qualquer termo, por palavra inteira, em ordem de posição."""
        achados = []
        for termo in sorted(termos):
            achados.extend(re.finditer(rf"(?<![A-Z0-9]){re.escape(termo)}(?![A-Z0-9])", self.texto))
        return sorted(achados, key=lambda m: (m.start(), -m.end()))


def _indexar(markdown: "str | MarkdownIndexado") -> MarkdownIndexado:
    return markdown if isinstance(markdown, MarkdownIndexado) else MarkdownIndexado(markdown)


def avaliar(
    markdown: "str | MarkdownIndexado", exame: str, termos: Optional[Iterable[str]] = None
) -> tuple[Optional[str], Optional[str]]:
    """
    Evidência do exame de laboratório no markdown e a linha de origem.

    A linha de origem é a da primeira ocorrência com resultado; sem resultado,
    a da primeira ocorrência. `(None, None)` quando o nome não aparece.
    """
    doc = _indexar(markdown)
    ocorrencias = doc.ocorrencias(termos if termos is not None else termos_do_exame(exame))
    if not ocorrencias:
        return None, None
    for m in ocorrencias:
        janela = _DATA.sub(" ", doc.texto[m.end():m.end() + JANELA_RESULTADO])
        if _RESULTADO.search(janela):
            return COM_RESULTADO, mascarar_linha(doc.linha_em(m.start()))
    return SO_LISTA, mascarar_linha(doc.linha_em(ocorrencias[0].start()))


def linha_de_origem(markdown: "str | MarkdownIndexado", termos: Iterable[str]) -> Optional[str]:
    """Linha da primeira ocorrência do nome, para exame que não é laboratório."""
    doc = _indexar(markdown)
    ocorrencias = doc.ocorrencias(termos)
    return mascarar_linha(doc.linha_em(ocorrencias[0].start())) if ocorrencias else None


def anotar_comparativo(
    comparativo: list[dict[str, Any]],
    markdown: str,
    sinonimos_de: Callable[[str], Iterable[str]] = lambda _chave: (),
) -> list[str]:
    """
    Grava a evidência nos itens "encontrado" do comparativo, no próprio dict.

    Laboratório ganha `evidencia` ("so_lista" | "com_resultado") e `linha_origem`;
    os demais, só `linha_origem`, quando o nome aparece. Item cujo nome não
    aparece fica sem nada. `sinonimos_de` recebe a chave do catálogo
    (`chave_catalogo`) e devolve as variações. Devolve os nomes "so_lista".
    """
    doc = MarkdownIndexado(markdown)
    so_lista: list[str] = []
    for item in comparativo:
        if item.get("status") != "encontrado" or not item.get("exame"):
            continue
        exame = item["exame"]
        chaves = {chave_catalogo(exame), chave_catalogo(re.sub(r"\(.*?\)", "", exame))}
        sinonimos: set[str] = set()
        for chave in chaves:
            sinonimos |= set(sinonimos_de(chave) or ())
        termos = termos_do_exame(exame, sinonimos)
        if eh_laboratorio(exame):
            evidencia, linha = avaliar(doc, exame, termos)
            if evidencia is None:
                continue
            item["evidencia"] = evidencia
            item["linha_origem"] = linha
            if evidencia == SO_LISTA:
                so_lista.append(exame)
                # A justificativa da comparação dizia "foi encontrado", o que
                # contradiz o que a tela mostra. A frase dela fica guardada à
                # parte, uma vez só, para a anotação poder rodar de novo.
                item.setdefault("justificativa_comparacao", item.get("justificativa"))
                item["justificativa"] = JUSTIFICATIVA_SO_LISTA
        else:
            linha = linha_de_origem(doc, termos)
            if linha is not None:
                item["linha_origem"] = linha
    return so_lista
