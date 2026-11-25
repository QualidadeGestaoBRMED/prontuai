"""
Sexo e idade do paciente (pedido de 23/11), lidos do texto ORIGINAL do documento.

Por que do original: a redação do .md troca o valor por [DADO] ("SEXO: [DADO]") em milhares de laudos de
laboratório, e o .md não serve. O texto original tem nome e CPF; esta leitura roda só nesta máquina e devolve
só "M"/"F" e a idade em anos — nada do texto sai do processo nem vai para log.

Sexo — só com rótulo explícito, por voto entre as ocorrências do documento:
- "Sexo: M", "Sexo. : Masculino", "Gênero / Genre: Masculine", "Gender: Female", valor na mesma linha ou
  na linha de baixo;
- fora: "pacientes do sexo feminino, anotar DUM" (instrução da ficha) e "Sexo ( ) Masculino ( ) Feminino"
  (as duas opções impressas, sem marca legível);
- voto: a maioria vence só se for pelo menos o triplo da minoria; empate ou conflito forte → vazio;
- sem rótulo legível fica vazio: nada de dedução (data da menstruação, nome) — decisão de 23/11.

Conferência de 23/11: 10 documentos sorteados (6 M, 4 F) contra o PDF — 10/10 no sexo e na idade; nas 858 com
2+ ocorrências, 835 unânimes.

Idade — data de nascimento e data do documento (mais confiável que o número impresso); sem nascimento legível,
"Idade: 45" / "Idade / Age: 45 anos". Fora de 14–90 anos fica vazio.
"""
from __future__ import annotations

import collections
import re
import unicodedata
from datetime import date
from typing import Optional


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()


_MASC = r"MASCUL\w*|MALE|MASC|M"
_FEM = r"FEMIN\w*|FEMALE|FEM|F"
_ROTULO = r"(?<![A-Z])(?:SEXO(?:\s*/\s*SEX)?|GENERO(?:\s*/\s*GENRE)?|GENRE|GENDER)"
# Rótulo, separadores (":", ".", "/", "-", "#" do markdown, quebra de linha) e o valor. "MASCULINN" (OCR) vale.
_RX_SEXO = re.compile(_ROTULO + r"[\s#.:/\-]{0,12}(" + _MASC + "|" + _FEM + r")(?![A-Z])")
# Caixinha marcada logo depois do rótulo: "Sexo: X Masculino ( ) Feminino", "Sexo: (X) Feminino".
_RX_SEXO_MARCADO = re.compile(_ROTULO + r"[\s#.:]{0,6}(?:[^\n]{0,30}?)(?:\(\s*X\s*\)|(?<![A-Z])X)\s*(MASCUL\w*|FEMIN\w*)")
_INSTRUCAO = re.compile(r"PACIENTES? DO SEXO|DO SEXO FEMININO,? ANOTAR|SEXO FEMININO,? ANOTAR")


def sexo(texto: str) -> tuple[Optional[str], int]:
    """("M" | "F" | None, nº de ocorrências que votaram)."""
    t = _norm(texto)
    votos = collections.Counter()
    for m in _RX_SEXO.finditer(t):
        antes = t[max(0, m.start() - 30):m.start()]
        depois = t[m.end():m.end() + 40]
        if _INSTRUCAO.search(antes + t[m.start():m.end() + 20]):
            continue
        valor = m.group(1)
        # "Sexo ( ) Masculino ( ) Feminino" / "Sexo: Masculino Feminino": as duas opções impressas.
        if re.match(r"[\s()X/]*(?:" + (_FEM if valor[0] == "M" else _MASC) + r")(?![A-Z])", depois) and len(valor) > 1:
            continue
        votos["M" if re.fullmatch(_MASC, valor) else "F"] += 1
    for m in _RX_SEXO_MARCADO.finditer(t):
        votos["M" if m.group(1).startswith("MASC") else "F"] += 2  # marca explícita pesa mais que opção impressa
    if not votos:
        return None, 0
    (v1, n1), *resto = votos.most_common()
    n2 = resto[0][1] if resto else 0
    return (v1 if n1 >= 3 * n2 and n1 > n2 else None), n1 + n2


_DATA = r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})"
_RX_NASC = re.compile(r"(?:NASCIMENTO|NASC\w*|DATA DE NASC\w*|DT\.?\s*NASC\w*|BIRTH\w*|DOB|(?<![A-Z])D\.?\s?N\.?(?![A-Z]))\W{0,12}" + _DATA)
_RX_IDADE = re.compile(r"(?<![A-Z])(?:IDADE|AGE)(?:\s*/\s*AGE)?\s*[:\-]?\s*(\d{2})(?:\s*ANOS|\s*A\b|\s*YEARS)?(?!\s*[/\d])"
                       r"|\((\d{2})\s*ANOS\)")


def _anos(nasc: date, ref: date) -> int:
    return ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))


def idade(texto: str, data_doc: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """(idade em anos, fonte: "nascimento" | "impressa")."""
    t = _norm(texto)
    ref = None
    if data_doc:
        try:
            ref = date.fromisoformat(data_doc[:10])
        except ValueError:
            ref = None
    if ref:
        idades = collections.Counter()
        for m in _RX_NASC.finditer(t):
            try:
                n = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                continue
            a = _anos(n, ref)
            if 14 <= a <= 90:
                idades[a] += 1
        if idades:
            return idades.most_common(1)[0][0], "nascimento"
    impressas = collections.Counter(int(m.group(1) or m.group(2)) for m in _RX_IDADE.finditer(t)
                                    if 14 <= int(m.group(1) or m.group(2)) <= 90)
    if impressas:
        return impressas.most_common(1)[0][0], "impressa"
    return None, None
