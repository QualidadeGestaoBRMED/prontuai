"""
Laudo ODONTOLÓGICO ocupacional no texto de OCR do prontuário (regex, sem LLM, sem rede). STC-1065, 23/11.

Saída de ler(texto_entrada):
  odonto             "apto" | "apto_com_restricao" | "inapto" | None   (None: sem laudo ou resultado ilegível)
  odonto_tratamento  "sim" | "nao" | None    (o laudo indica/sugere tratamento odontológico)
  odonto_urgencia    "sim" | "nao" | None    (risco iminente de dor / tratamento urgente)

Formatos (amostra de 400 da base de 10 mil e 400 da nossa):
  A) "LAUDO ODONTOLÓGICO / Atesto ... ( ) APTO ao exercício profissional, SEM risco iminente de dor /
     (X) INAPTO ao exercício profissional, COM risco iminente de dor" (NR-30 / trabalho embarcado).
  B) "FICHA DE AVALIAÇÃO ODONTOLÓGICA": perguntas com a resposta na linha ("Há alguma alteração no exame que
     indique o risco iminente de dor? NÃO", "Outras alterações ... com indicação de tratamento eletivo? SIM") e
     "Resultado: ... RECOMENDADO / NÃO RECOMENDADO para o trabalho marítimo".
  C) Texto: "Paciente está apto para o exercício de sua profissão", "Apto com necessidade de tratamento".
Regras:
- Janela: título (LAUDO ODONTOLÓGICO, AVALIAÇÃO/FICHA DE AVALIAÇÃO ODONTOLÓGICA, ATESTADO ODONTOLÓGICO) até a
  mudança de página, outro exame/ASO ou 70 linhas. Item da lista do ASO (com data) e "DENTAL ASSESSMENT" do ASO
  bilíngue não abrem janela.
- Opção sem marca não conta. Caixa explícita vazia "( )" numa opção e a outra opção SEM caixa: a sem caixa é a
  marcada (o OCR comeu o X). As duas sem caixa nem marca: não decide.
- odonto: inapto (INAPTO marcado, "NÃO RECOMENDADO") > apto_com_restricao ("apto com necessidade de tratamento",
  "apto com restrição", "recomendado com ressalva") > apto (APTO marcado, "RECOMENDADO", "está apto").
- odonto_urgencia: sim com "risco iminente de dor? SIM", INAPTO/COM risco iminente marcado, "urgente/urgência"
  afirmado; nao com "risco iminente de dor? NÃO" ou APTO/SEM risco iminente marcado.
- odonto_tratamento: sim com "tratamento eletivo? SIM", "sugiro (avaliação e) tratamento/intervenção/exodontia/
  restauração/endodontia", "necessidade de tratamento", "requer cuidados", inapto; nao com "tratamento eletivo?
  NÃO" sem sugestão de tratamento, ou "sem alterações / saúde bucal satisfatória".
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#*>| ").strip()


_TITULO = re.compile(r"LAUDO ODONTOLOGIC|AVALIA\w{0,4}O ODONTOLOGIC|FICHA DE AVALIA\w* ODONTO|ATESTADO ODONTOLOGIC|EXAME ODONTOLOGIC"
                     r"|PARECER ODONTOLOGIC")
_DATA = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}")
_NAO_TITULO = re.compile(r"\?|DENTAL ASSESSMENT|PROCEDIMENTOS|EXAMES COMPLEMENTARES|PREPARO|AGENDA")
# Título de outro exame só no começo da linha ("Descrição: sugiro avaliação RADIOGRÁFICA" não fecha a janela).
_FIM = re.compile(r"<!--\s*PAGINA|CONCLUSAO ?/ ?CONCLUSION|ANALYSIS REPORT|^(?:\d+\W*)?(?:ATESTADO DE SAUDE OCUPACIONAL|AUDIOMETR"
                  r"|AVALIACAO AUDIOLOG|ACUIDADE VISUAL|ESPIROMETR|HEMOGRAMA|RADIOGRAF|ELETROCARDIOGRAM|LAUDO DE ELETRO|TESTE ERGOMETRICO"
                  r"|ELETROENCEFALO|LAUDO PSICOLOG|AVALIACAO PSICO|FICHA MEDICA|FICHA CLINICA|EXAME CLINICO|GLICEMIA|PARASITOLOG|TOXICOLOG)")
JANELA = 70

_MARCA = r"[\(\[\{]\s*[XK]\s*[\)\]\}]"
_VAZIA = r"[\(\[\{]\s*[\)\]\}]"
_OPC_APTO = re.compile(r"(?<!IN)\bAPTO (?:AO|PARA O) EXERCICIO|SEM RISCO IMINENTE")
_OPC_INAPTO = re.compile(r"\bINAPTO (?:AO|PARA O) EXERCICIO|COM RISCO IMINENTE")

_PERGUNTA_DOR = re.compile(r"RISCO IMINENTE DE DOR\s*\?\s*(SIM|N.?O)\b")
_PERGUNTA_TRAT = re.compile(r"TRATAMENTO ELETIVO\s*\?\s*(SIM|N.?O)\b")
_INAPTO_TXT = re.compile(r"NAO RECOMENDAD\w* PARA O TRAB|NAO (?:ESTA )?APTO PARA O EXERCICIO|\bINAPTO PARA O EXERCICIO DE SUA")
_RESTRICAO_TXT = re.compile(r"APTO COM (?:NECESSIDADE DE TRATAMENTO|RESTRIC|RESSALV|RECOMENDAC)|RECOMENDADO COM RESSALV")
_APTO_TXT = re.compile(r"(?<!NAO )RECOMENDAD\w* PARA O TRAB|(?<!NAO )(?<!NAO ESTA )\bESTA APTO PARA O EXERCICIO|CONSIDERADO APTO"
                       r"|^(?:RESULTADO\W*)?APTO\.?$")
_TRAT_SIM = re.compile(r"SUGIRO (?:A )?(?:AVALIACAO E )?(?:TRATAMENTO|INTERVENCAO|EXODONTIA|RESTAURA|ENDODON|RASPAGEM|PROFILAXIA|REABILITA)"
                       r"|SUGIRO TRATAMENTO|NECESSIDADE DE TRATAMENTO|NECESSITA (?:DE )?TRATAMENTO|REQUER CUIDADOS"
                       r"|RECOMENDA-SE (?:AVALIACAO E )?TRATAMENTO|INDICAD\w* (?:PARA )?TRATAMENTO|CONDENADO A EXODONTIA|CARIES? ATIVA")
_TRAT_NAO = re.compile(r"SEM (?:NECESSIDADE DE )?TRATAMENTO|NAO (?:FORAM )?(?:ENCONTRAD|CONSTATAD|OBSERVAD|IDENTIFICAD)\w* (?:ALTERAC|LES)"
                       r"|SEM ALTERAC\w* (?:BUCA|ODONTO|DIGNAS)|SAUDE BUCAL (?:SATISFATORIA|ADEQUADA|BOA)|CONDICOES BUCAIS (?:SATISFATORIAS|ADEQUADAS)")
_URG_SIM = re.compile(r"(?<!SEM )(?<!NAO HA )URGEN\w*|ATENDIMENTO IMEDIATO")


def _janelas(linhas: list[str]) -> list[list[str]]:
    out, i = [], 0
    while i < len(linhas):
        l = linhas[i]
        if not (_TITULO.search(l) and not _DATA.search(l) and not _NAO_TITULO.search(l) and len(l) <= 90):
            i += 1
            continue
        j = i + 1
        while j < len(linhas) and j - i <= JANELA and not _FIM.search(linhas[j]):
            j += 1
        out.append(linhas[i:j])
        i = j
    return out


def _opcao(jan: list[str]) -> Optional[str]:
    """APTO/INAPTO do formulário A, pela marca (ou pela opção sem caixa quando a outra tem caixa vazia)."""
    apto = [l for l in jan if _OPC_APTO.search(l) and not _OPC_INAPTO.search(l)]
    inapto = [l for l in jan if _OPC_INAPTO.search(l) and not _OPC_APTO.search(l)]
    if any(re.match(r"\W*" + _MARCA, l) for l in inapto):
        return "inapto"
    if any(re.match(r"\W*" + _MARCA, l) for l in apto):
        return "apto"
    vazia = lambda l: re.match(r"\W*" + _VAZIA, l) is not None
    sem_caixa = lambda l: not re.match(r"\W*[\(\[\{]", l)
    if apto and inapto:
        if all(vazia(l) for l in inapto) and any(sem_caixa(l) for l in apto):
            return "apto"
        if all(vazia(l) for l in apto) and any(sem_caixa(l) for l in inapto):
            return "inapto"
    return None


def debug_janelas(texto_entrada: str) -> list[list[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    return _janelas(linhas)


def ler(texto_entrada: str) -> dict[str, Optional[str]]:
    linhas = [n for n in (_norm(l) for l in (texto_entrada or "").splitlines()) if n]
    out: dict[str, Optional[str]] = {"odonto": None, "odonto_tratamento": None, "odonto_urgencia": None}
    res, trat, urg = set(), set(), set()
    for jan in _janelas(linhas):
        texto = " | ".join(jan)
        op = _opcao(jan)
        if op:
            res.add(op)
            # Urgência só pelo "COM risco iminente de dor" marcado: "INAPTO, menos de 20 elementos dentários" não é dor.
            marcada = [l for l in jan if re.match(r"\W*" + _MARCA, l)]
            if op == "inapto" and any("RISCO IMINENTE" in l for l in marcada):
                urg.add("sim")
            elif op == "apto":
                urg.add("nao")
        # Opção de texto com caixa vazia ("( ) NÃO RECOMENDADO PARA O TRABALHO MARÍTIMO") não conta.
        # Linha com as duas opções impressas ("RECOMENDADO PARA O TRABALHO MARÍTIMO ( NÃO RECOMENDADO ...") não decide.
        sem_vazias = [l for l in jan if not re.match(r"\W*" + _VAZIA, l)
                      and not (re.search(r"NAO RECOMEND", l) and re.search(r"(?<!NAO )\b\w?ECOMENDAD\w* PARA", l))]
        for l in sem_vazias:
            if _INAPTO_TXT.search(l):
                res.add("inapto")
            elif _RESTRICAO_TXT.search(l):
                res.add("apto_com_restricao")
            elif _APTO_TXT.search(l):
                res.add("apto")
        m = _PERGUNTA_DOR.search(texto)
        if m:
            urg.add("sim" if m.group(1) == "SIM" else "nao")
        if _URG_SIM.search(texto):
            urg.add("sim")
        m = _PERGUNTA_TRAT.search(texto)
        if _TRAT_SIM.search(texto) or (m and m.group(1) == "SIM"):
            trat.add("sim")
        elif (m and m.group(1) == "NAO") or _TRAT_NAO.search(texto):
            trat.add("nao")
    for r in ("inapto", "apto_com_restricao", "apto"):
        if r in res:
            out["odonto"] = r
            break
    if out["odonto"] in ("inapto", "apto_com_restricao"):
        trat.add("sim")
    out["odonto_tratamento"] = "sim" if "sim" in trat else "nao" if "nao" in trat else None
    out["odonto_urgencia"] = "sim" if "sim" in urg else "nao" if "nao" in urg else None
    return out
