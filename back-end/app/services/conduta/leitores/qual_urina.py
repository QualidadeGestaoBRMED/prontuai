"""
URINA TIPO 1 / EAS (sumário de urina) no texto de OCR do prontuário (regex, sem LLM, sem rede). STC-1065, 23/11.

Saída de ler(texto_entrada), cada uma "normal" | "alterado" | None (None: sem laudo de urina ou valor ilegível):
  urina_proteina, urina_glicose, urina_sangue, urina_leucocitos, urina_nitrito

Regras (amostra de 400 da base de 10 mil):
- Janela: título do laudo (URINA TIPO I, EXAME DE URINA DE ROTINA, SUMÁRIO DE URINA, ELEMENTOS ANORMAIS - LEITURA DE
  TIRAS, URINÁLISE, EAS) até o título de outro exame do laboratório ou 90 linhas. Item da lista do ASO (com data) e a
  lista de exames do pedido ("HEMOGRAMA; URINA TIPO I; TRIAGEM...") não abrem janela.
- A referência sai antes da leitura: "PROTEÍNA: AUSENTE", "LEUCÓCITOS: 0 A 27 /UL", "MASCULINO: 0 A 16".
- Tiras (proteína, glicose, hemoglobina, nitrito, esterase): o valor é o que vem depois do rótulo na mesma linha ou na
  linha seguinte. AUSENTE / NEGATIVO / NORMAL -> normal; TRAÇOS, +, ++, POSITIVO, PRESENTE, número com mg/dL -> alterado
  (nitrito positivo = alterado; "traços" = alterado).
- OCR que embaralha a tabela (bloco de rótulos separado do bloco de valores): sem nenhum valor anormal na janela (fora
  das referências), todo rótulo presente é normal; com valor anormal que não dá para atribuir, fica None.
- Contagens (sedimento): LEUCÓCITOS e HEMÁCIAS "/µL" (ou /mL) acima do máximo da referência do próprio laudo -> alterado
  (sem referência legível: leucócitos > 25/µL ou > 10.000/mL; hemácias > 20/µL ou > 10.000/mL). "Inferior a 10.000/mL"
  -> normal.
- urina_sangue = hemoglobina da tira e hemácias do sedimento (qualquer alterado -> alterado).
- urina_leucocitos = esterase leucocitária da tira e leucócitos do sedimento (qualquer alterado -> alterado).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#*>| ").strip()


_TITULO = re.compile(r"URINA (?:TIPO ?(?:I|1)\b|DE ROTINA|ROTINA)|EXAME DE URINA|SUMARIO DE URINA|ELEMENTOS ANORMAIS|URINALISE"
                     r"|URINALYSIS|\bEAS\b|PARCIAL DE URINA|URINA I\b|URINA 1\b")
_NAO_TITULO = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}|;|\?|PREPARO|ORIENTAC|JATO|COLETA DE|FRASCO")
_FIM = re.compile(r"^(?:\d+\W*)?(?:HEMOGRAMA|ERITROGRAMA|LEUCOGRAMA|PARASITOLOG|COPROLOG|CREATININA|UREIA|COLESTEROL|TRIGLICER"
                  r"|GLICEMIA|GLICOSE (?:EM JEJUM|DE JEJUM|PLASMATICA)|TGO|TGP|TRANSAMINASE|GAMA|HEMOGLOBINA GLICADA|TSH|PSA"
                  r"|ATESTADO DE SAUDE|AUDIOMETR|ACUIDADE|ESPIROMETR|ELETROCARDIO|RADIOGRAF|TOXICOLOG|TRIAGEM TOXICOLOG|VDRL"
                  r"|GRUPO SANGUINEO|TIPAGEM|ACIDO URICO|FERRITINA)|CONCLUSAO ?/ ?CONCLUSION")
JANELA = 90

_ROTULO = {
    "proteina": re.compile(r"\bPROTEINAS?\b"),
    "glicose": re.compile(r"\bGLICOSE\b|\bGLUCOSE\b"),
    "hemoglobina": re.compile(r"\bHEMOGLOBINA\b|\bSANGUE\b(?! OCULTO)|\bBLOOD\b"),
    "nitrito": re.compile(r"\bNITRITOS?\b|\bNITRITE\b"),
    "esterase": re.compile(r"ESTERASE"),
}
_CONTAGEM = {"leucocitos": re.compile(r"\bLEUC\w{2,4}TOS\b|PIOCITOS"), "hemacias": re.compile(r"\bHEM\w?CIAS\b|ERITROCITOS")}
_LIMITE = {"leucocitos": (25.0, 10000.0), "hemacias": (20.0, 10000.0)}

_NORMAL = re.compile(r"^\W*(?:AUSENTES?|NEGATIV[OAE]S?|NORMAL|NAO REAGENTE|ABSENT|NEGATIVE|INDETECTAVEL)\b")
_ANORMAL = re.compile(r"^\W*(?:TRACOS?|TRACES?|\(?\+{1,4}\)?|[1-4] ?\+|POSITIV\w*|PRESENTES?|REAGENTE|\d+(?:[.,]\d+)? ?MG ?/ ?DL"
                      r"|RAROS?|POUCOS?|NUMEROSOS?|INUMEROS)\b|^\W*\(?\+")
_REF = re.compile(r"[A-Z]{3,}\s*:\s*(?:AUSENTE|NEGATIV|NORMAL|NAO REAG|\d+\s*A\s*\d+|INFERIOR|ATE)|^\W*(?:MASC|FEM)\w*\s*[.:]"
                  r"|INTERVALO DE REFERENCIA|VALOR(?:ES)? DE REFERENCIA|CONFIRA NA TABELA")
_RE_REF_INLINE = re.compile(r"\b[A-Z]{3,}\s*:\s*[A-Z0-9 ,.A/]*$")


def _janelas(linhas: list[str]) -> list[list[str]]:
    out, i = [], 0
    while i < len(linhas):
        l = linhas[i]
        if not (_TITULO.search(l) and not _NAO_TITULO.search(l) and len(l) <= 90):
            i += 1
            continue
        j = i + 1
        while j < len(linhas) and j - i <= JANELA and not _FIM.search(linhas[j]):
            j += 1
        jan = linhas[i:j]
        if any(_ROTULO[k].search(x) for x in jan for k in _ROTULO) or any(rx.search(x) for x in jan for rx in _CONTAGEM.values()):
            out.append(jan)
        i = j
    return out


def _sem_ref(l: str) -> str:
    """Tira a referência da linha: "PROTEINA AUSENTE PROTEINA: AUSENTE" -> "PROTEINA AUSENTE"."""
    m = re.search(r"\b[A-Z]{3,}\s*:", l)
    if m and m.start() > 0:
        return l[:m.start()].strip()
    return "" if _REF.search(l) else l


def _valor_tira(jan: list[str], rx: re.Pattern) -> tuple[Optional[str], bool]:
    """(normal|alterado|None, rótulo presente fora da referência)."""
    presente = False
    for k, l in enumerate(jan):
        s = _sem_ref(l)
        m = rx.search(s)
        if not m:
            continue
        presente = True
        cands = [s[m.end():]]
        if k + 1 < len(jan):
            prox = _sem_ref(jan[k + 1])
            if not any(r.search(prox) for r in list(_ROTULO.values()) + list(_CONTAGEM.values())) or _NORMAL.match(prox) or _ANORMAL.match(prox):
                cands.append(prox)
        for c in cands:
            c = c.strip(" :.-")
            if _ANORMAL.match(c):
                return "alterado", True
            if _NORMAL.match(c):
                return "normal", True
    return None, presente


def _ref_max(jan: list[str], rx: re.Pattern) -> Optional[float]:
    vals = []
    for k, l in enumerate(jan):
        if rx.search(l) or (k and rx.search(jan[k - 1])) or re.match(r"^\W*(?:MASC|FEM)", l):
            for m in re.finditer(r"\b\d+\s*A\s*(\d+(?:[.,]\d+)?)\s*(?:/?\s*[UuΜ]?L|/ ?ML|L\b)?", l):
                try:
                    vals.append(float(m.group(1).replace(".", "").replace(",", ".")))
                except ValueError:
                    pass
    return max(vals) if vals else None


def _contagem(jan: list[str], chave: str) -> Optional[str]:
    rx = _CONTAGEM[chave]
    ref = _ref_max(jan, rx)
    for k, l in enumerate(jan):
        s = _sem_ref(l)
        m = rx.search(s)
        if not m:
            continue
        resto = s[m.end():]
        if k + 1 < len(jan) and not re.search(r"\d", resto):
            resto += " " + _sem_ref(jan[k + 1])
        resto = resto.strip()
        if re.match(r"\W*(?:INFERIOR|MENOR|<|ABAIXO)", resto):
            return "normal"
        if re.match(r"\W*(?:RAROS?|AUSENTES?)\b", resto):
            return "normal"
        if re.match(r"\W*(?:NUMEROSOS?|INUMEROS|INCONTAVEIS|CAMPOS? (?:REPLETOS|CHEIOS))", resto):
            return "alterado"
        n = re.match(r"\W*(\d{1,3}(?:\.\d{3})+|\d+)(?:[,]\d+)?\s*(/\s*ML|/?\s*[UuΜ]?L\b|L\b|/\s*CAMPO|P/C)?", resto)
        if not n:
            continue
        x = float(n.group(1).replace(".", ""))
        if re.match(r"\W*\d+,\d", resto):
            x = float(re.match(r"\W*(\d+,\d+)", resto).group(1).replace(",", "."))
        unid = (n.group(2) or "").replace(" ", "")
        por_ml = unid.endswith("ML") and "U" not in unid
        # Referência na própria linha: "ERITROCITOS: 21,2 /µL INFERIOR A 23,0 /µL", "LEUCOCITOS 19/UL LEUCOCITOS: 0 A 27".
        prox = jan[k + 1] if k + 1 < len(jan) else ""
        if any(r.search(prox) for r in list(_ROTULO.values()) + list(_CONTAGEM.values())):
            prox = ""  # referência de outro parâmetro
        r_l = re.search(r"(?:INFERIOR|MENOR|ATE|<)\s*(?:A|QUE|DE)?\s*(\d+(?:[.,]\d+)?)|\b\d+\s*A\s*(\d+(?:[.,]\d+)?)",
                        l[m.end():] + " " + prox)
        if r_l:
            v = (r_l.group(1) or r_l.group(2))
            por_ml = por_ml or bool(re.search(r"\d\.\d{3}", v))
            ref = float(v.replace(".", "").replace(",", ".")) if not re.fullmatch(r"\d+,\d+", v) else float(v.replace(",", "."))
        if por_ml:
            lim = ref if ref and ref >= 1000 else _LIMITE[chave][1]
        else:
            lim = ref if ref and ref < 1000 else _LIMITE[chave][0]
        if "CAMPO" in unid or "P/C" in unid:
            lim = 5.0 if chave == "leucocitos" else 3.0
        return "alterado" if x > lim else "normal"
    return None


def debug_janelas(texto_entrada: str) -> list[list[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    return _janelas(linhas)


def ler(texto_entrada: str) -> dict[str, Optional[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    out: dict[str, Optional[str]] = {"urina_proteina": None, "urina_glicose": None, "urina_sangue": None,
                                     "urina_leucocitos": None, "urina_nitrito": None}
    for jan in _janelas(linhas):
        vals, presentes = {}, set()
        for nome, rx in _ROTULO.items():
            v, p = _valor_tira(jan, rx)
            vals[nome] = v
            if p:
                presentes.add(nome)
        # Tabela embaralhada: sem nenhum valor anormal na janela, rótulo presente sem valor atribuído é normal.
        algum_anormal = any(_ANORMAL.match(_sem_ref(l).strip(" :.-")) or re.search(r"\b(?:TRACOS?|POSITIV\w*|\+{1,4})", _sem_ref(l))
                            for l in jan)
        for nome in _ROTULO:
            if vals[nome] is not None:
                continue
            # "PROTEINAS: NEGATIVO NEGATIVO" (resultado e referência depois dos dois-pontos): o 1º valor é o resultado.
            for l in jan:
                m = re.match(r"\W*(?:" + _ROTULO[nome].pattern + r")\s*:\s*(.+)$", l)
                if m:
                    v = m.group(m.lastindex).strip(" :.-")
                    if _ANORMAL.match(v):
                        vals[nome] = "alterado"
                        break
                    if _NORMAL.match(v):
                        presentes.add(nome)
                        if re.fullmatch(r"\w+\s+\w+", v):  # dois valores = resultado + referência: atribuído
                            vals[nome] = "normal"
                            break
            if vals[nome] is None and nome in presentes and not algum_anormal:
                vals[nome] = "normal"
        leuc, hem = _contagem(jan, "leucocitos"), _contagem(jan, "hemacias")

        def junta(*xs):
            xs = [x for x in xs if x]
            return "alterado" if "alterado" in xs else ("normal" if xs else None)

        novo = {"urina_proteina": vals["proteina"], "urina_glicose": vals["glicose"], "urina_nitrito": vals["nitrito"],
                "urina_sangue": junta(vals["hemoglobina"], hem), "urina_leucocitos": junta(vals["esterase"], leuc)}
        for k, v in novo.items():
            out[k] = junta(out[k], v)
    return out
