"""
Onde cada linha do OCR está na página do PDF — para a checagem levar o revisor
direto ao exame no documento, com o trecho destacado.

O Textract devolve, para cada LINE e cada WORD, a caixa em coordenadas relativas
à página (0 a 1, origem no canto superior esquerdo). O markdown guarda só o
texto; este módulo guarda o resto, numa tabela à parte (`documento_layout`,
migração 018) para não pesar na listagem de documentos.

Formato gravado (versão 1), compacto porque são centenas de linhas por documento:

    {"versao": 1, "linhas": [[pagina, x, y, w, h, [[x, w], ...]], ...]}

- uma entrada por LINE com texto, na MESMA ordem e com o mesmo filtro de
  `ocr_service.textract_to_markdown`. É isso que permite parear cada linha do
  markdown com a sua caixa sem gravar o texto de novo: o texto tem nome e CPF,
  já está no `ocr_markdown` e não precisa de uma segunda cópia;
- coordenadas em décimos de milésimo da página (inteiro de 0 a 10000);
- `[[x, w], ...]` é a faixa horizontal de cada WORD da linha, na ordem do
  texto. Serve para destacar só um pedaço da linha (o valor de um exame) em vez
  dela inteira.

Só o Textract tem coordenada. Documento lido pelo Docling (fallback local) e
documento processado antes deste módulo não têm layout: a tela segue sem o
atalho, como era.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

VERSAO = 1
ESCALA = 10000

# Comentários que o OCR acrescenta ao markdown (`<!-- pagina N -->`). Não são
# linha do documento e não têm caixa.
_RE_COMENTARIO = re.compile(r"^<!--.*-->$")
# Página que abre a lista de exames do ASO: o nome do exame lido ali não é o
# laudo. Mesmo critério de `workflow_service._RE_ABERTURA_LISTA_ASO`.
_RE_LISTA_ASO = re.compile(r"Procedimentos\s+Realizados|Exames\s+complementares", re.I)

# Quantas ocorrências de um exame a tela recebe. O revisor alterna entre elas
# clicando de novo; mais que isso é o nome repetido em cabeçalho de página.
MAX_OCORRENCIAS = 5


# ---------------------------------------------------------------------------
# Captura (no OCR)
# ---------------------------------------------------------------------------

def _caixa(bloco: dict) -> list[int]:
    bb = (bloco.get("Geometry") or {}).get("BoundingBox") or {}
    return [
        max(0, min(ESCALA, round(float(bb.get(k) or 0) * ESCALA)))
        for k in ("Left", "Top", "Width", "Height")
    ]


def linhas_textract(resposta: dict, pagina: Optional[int] = None) -> list[list]:
    """
    As linhas de uma resposta do Textract, no formato gravado.

    `pagina` vale para todos os blocos quando a resposta é de uma página só (o
    síncrono, chamado página a página, não traz `Page`); sem ela, vale o `Page`
    de cada bloco (assíncrono).
    """
    blocos = resposta.get("Blocks", []) or []
    palavras_por_id = {b.get("Id"): b for b in blocos if b.get("BlockType") == "WORD"}
    linhas: list[list] = []
    for bloco in blocos:
        if bloco.get("BlockType") != "LINE":
            continue
        # Mesmo filtro de `textract_to_markdown`: linha vazia não vira markdown.
        if not (bloco.get("Text") or "").strip():
            continue
        palavras = []
        for relacao in bloco.get("Relationships") or []:
            if relacao.get("Type") != "CHILD":
                continue
            for id_palavra in relacao.get("Ids") or []:
                palavra = palavras_por_id.get(id_palavra)
                if palavra:
                    x, _, w, _ = _caixa(palavra)
                    palavras.append([x, w])
        numero = pagina if pagina is not None else bloco.get("Page")
        linhas.append([int(numero or 1), *_caixa(bloco), palavras])
    return linhas


def montar(linhas: list[list]) -> Optional[dict]:
    """O layout a gravar, ou None quando não há nenhuma linha."""
    return {"versao": VERSAO, "linhas": linhas} if linhas else None


# Chave do layout no resultado do `workflow_service`. Ele viaja ali só até quem
# grava o documento, que o tira com `separar` ANTES de gravar o payload ou
# devolvê-lo ao cliente: são centenas de linhas que só a checagem lê, e o
# payload é carregado em toda listagem.
CHAVE_RESULTADO = "ocr_layout"


def separar(resultado: Any) -> Optional[dict]:
    """Tira o layout do resultado do processamento e o devolve."""
    if not isinstance(resultado, dict):
        return None
    return resultado.pop(CHAVE_RESULTADO, None)


# ---------------------------------------------------------------------------
# Leitura (na checagem)
# ---------------------------------------------------------------------------

@dataclass
class LinhaPosicionada:
    # Texto da linha como está no markdown, sem o "## " de cabeçalho.
    texto: str
    pagina: int
    caixa: tuple[int, int, int, int]
    palavras: list[list[int]] = field(default_factory=list)
    # `textract_to_markdown` marca como cabeçalho a linha curta em maiúsculas —
    # o título do laudo costuma ser uma.
    cabecalho: bool = False
    # Índice da linha em `markdown.split("\n")`: liga a caixa a quem lê o
    # markdown por posição (a normalidade).
    linha_markdown: int = -1


def alinhar(markdown: str, layout: Any) -> Optional[list[LinhaPosicionada]]:
    """
    Pareia as linhas do markdown com as caixas do layout, na ordem.

    None quando não dá para parear com segurança: sem layout, versão
    desconhecida ou quantidade de linhas diferente (markdown que não saiu do
    mesmo OCR). Nesse caso a tela não oferece o atalho — destacar a linha errada
    é pior do que não destacar.
    """
    if not markdown or not isinstance(layout, dict) or layout.get("versao") != VERSAO:
        return None
    caixas = layout.get("linhas") or []
    textos: list[tuple[str, bool, int]] = []
    for indice, bruta in enumerate(markdown.split("\n")):
        linha = bruta.strip()
        if not linha or _RE_COMENTARIO.match(linha):
            continue
        cabecalho = linha.startswith("## ")
        textos.append((linha[3:] if cabecalho else linha, cabecalho, indice))
    if not caixas or len(textos) != len(caixas):
        return None
    return [
        LinhaPosicionada(
            texto=texto,
            pagina=int(c[0]),
            caixa=(int(c[1]), int(c[2]), int(c[3]), int(c[4])),
            palavras=c[5] if len(c) > 5 and isinstance(c[5], list) else [],
            cabecalho=cabecalho,
            linha_markdown=indice,
        )
        for (texto, cabecalho, indice), c in zip(textos, caixas)
    ]


def caixa_do_trecho(linha: LinhaPosicionada, inicio: int, fim: int) -> tuple[int, int, int, int]:
    """
    Caixa do trecho [inicio, fim) do texto da linha: a união das palavras que ele
    toca. Sem as caixas das palavras (ou com contagem diferente do texto), estima
    pela proporção de caracteres.
    """
    x, y, w, h = linha.caixa
    tokens = [(m.start(), m.end()) for m in re.finditer(r"\S+", linha.texto)]
    if tokens and len(tokens) == len(linha.palavras):
        tocadas = [linha.palavras[i] for i, (a, b) in enumerate(tokens) if a < fim and b > inicio]
        if tocadas:
            x0 = min(p[0] for p in tocadas)
            x1 = max(p[0] + p[1] for p in tocadas)
            return (x0, y, max(x1 - x0, 1), h)
    n = max(len(linha.texto), 1)
    inicio, fim = max(0, min(inicio, n)), max(0, min(fim, n))
    return (x + w * inicio // n, y, max(w * (fim - inicio) // n, 1), h)


def caixa_json(caixa: tuple[int, int, int, int]) -> dict[str, float]:
    """Caixa para a API, em fração da página (0 a 1)."""
    x, y, w, h = caixa
    return {"x": x / ESCALA, "y": y / ESCALA, "w": w / ESCALA, "h": h / ESCALA}


def paginas_da_lista_aso(linhas: list[LinhaPosicionada]) -> set[int]:
    """Páginas que abrem a lista de exames do ASO."""
    return {l.pagina for l in linhas if _RE_LISTA_ASO.search(l.texto)}


def normalizar_linhas(linhas: list[LinhaPosicionada], normalizar: Callable[[str], str]) -> list[str]:
    """O texto de cada linha normalizado e cercado de espaço, para a busca por
    palavra inteira de `localizar_termos`. Calculado uma vez por documento."""
    return [f" {normalizar(l.texto)} " for l in linhas]


def localizar_termos(
    linhas: list[LinhaPosicionada],
    normalizadas: list[str],
    termos: Iterable[str],
    paginas_aso: set[int],
) -> list[dict[str, Any]]:
    """
    Linhas onde algum dos termos aparece como palavra inteira, já na ordem em
    que a tela deve oferecer.

    `termos` e `normalizadas` passam pelo mesmo normalizador da comparação, para
    os sinônimos do catálogo casarem. A ordem põe primeiro o que tem mais cara
    de laudo: fora da página da lista do ASO, depois a linha de título, depois a
    ordem do documento. A linha destacada é a linha inteira: o nome do exame
    costuma ser ela toda, e o objetivo é levar até o laudo.
    """
    # Termo de 1 ou 2 letras ("RX") casaria com qualquer abreviação solta.
    alvos = [f" {t} " for t in {t for t in termos if t and len(t) >= 3}]
    if not alvos:
        return []
    achados = []
    for ordem, (linha, texto) in enumerate(zip(linhas, normalizadas)):
        if any(alvo in texto for alvo in alvos):
            achados.append((linha.pagina in paginas_aso, not linha.cabecalho, ordem, linha))
    achados.sort(key=lambda a: a[:3])
    return [
        {"pagina": linha.pagina, "caixas": [caixa_json(linha.caixa)]}
        for *_, linha in achados[:MAX_OCORRENCIAS]
    ]
