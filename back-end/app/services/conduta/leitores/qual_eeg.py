"""
Laudo de ELETROENCEFALOGRAMA (EEG) lido do texto de OCR do prontuário (sem LLM, sem rede). Pedido do Breno (23/11).

    ler(texto_entrada) -> {"eeg": "normal" | "alterado" | "sem_conclusao" | None,
                           "eeg_tipo": "normal" | "epileptiforme" | "lentificacao" | "inespecifico" | None}

None = não há laudo de EEG no texto (só o nome na lista do ASO não conta).
- Janela: linha com ELETROENCEFALOGRAMA/EEG (sem data — a da lista do ASO tem) até a página seguinte, o título de outro
  exame ou 3 linhas depois da assinatura. É laudo se tiver corpo de EEG: atividade de base, ritmo alfa, ondas de N c/s,
  fotoestimulação, hiperpneia, "eletroencefalográfico".
- Negação: "não mostraram anormalidades", "sem paroxismos", "ausência de atividade epileptiforme" não contam.
- Alterado: atividade epileptiforme/irritativa, paroxismos, espículas, ponta-onda, ondas agudas, lentificação, disfunção,
  foco, "anormal", "alterado". Tipo: epileptiforme vence lentificação; alterado sem classe → inespecifico.
- Normal: "traçado (eletroencefalográfico) normal", "dentro dos limites/padrões da normalidade", "sem anormalidades".
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#* ").strip()


_TITULO = re.compile(r"ELETROENCEFALOGRA|ELECTROENCEPHALOGRA|\bEEG\b")
_DATA = re.compile(r"\d{1,2} ?/ ?\d{1,2} ?/ ?\d{2,4}")
_NAO_LAUDO = re.compile(r"\?|PROCEDIMENTOS? REALIZADOS|PERFORMED PROCEDURES|EXAMES COMPLEMENTARES")
_PAGINA = re.compile(r"<!--\s*PAGINA")
_OUTRO_EXAME = re.compile(
    r"^(?:#+ )?(?:AUDIOMETR|AUDIOLOG|ELETROCARDIO|\bECG\b|ACUIDADE VISUAL|ESPIROMETR|HEMOGRAMA|TESTE ERGOMETRICO"
    r"|RADIOGRAF|RAIO|AVALIACAO PSICO|AVALIACAO ODONTO|FICHA MEDICA|ATESTADO DE SAUDE|GLICEMIA)")
_ASSINATURA = re.compile(r"\bCRM\b|NEUROLOGIST|NEUROFISIOLOG|ASSINADO (?:DIGITALMENTE|ELETRONICAMENTE)|\bDR\.? \[NOME\]")
_CORPO = re.compile(r"ATIVIDADE DE BASE|RITMO (?:ALFA|DE BASE|POSTERIOR)|ONDAS? DE \d|\d ?C/?S\b|FOTOESTIMUL|HIPERPNEIA|HIPERVENTIL"
                    r"|ELETROENCEFALOGRAFIC|ELETROGENESE|TRACADO (?:DE |DO )?(?:EEG|ELETROENCEFAL)|SONOLENCIA|VIGILIA")
JANELA = 40

_CAIXA_VAZIA = re.compile(r"[\[\(]\s*[\]\)]\s*[A-Z][A-Z ]{2,30}")
_NEGACAO = re.compile(r"\b(?:SEM|AUSENCIA D[EOA]S?|[NK]AO\W{1,3}(?:HA|SE OBSERV\w*|FORAM (?:OBSERVAD|EVIDENCIAD|REGISTRAD|VISUALIZAD|DETECTAD)\w*"
                      r"|MOSTR\w*|EVIDENCI\w*|APRESENT\w*|REGISTR\w*)"
                      r"|NENHUM\w*|INEXISTENCIA DE|NEGATIV[AO] PARA)\b[^.;:|]{0,70}")
_EPILEPTIFORME = re.compile(r"EPILEPTIFORM|IRRITATIV|PAROXISM|ESPICUL|PONTA[ -]?ONDA|POLIPONTA|ONDAS? AGUDAS?|\bFOCO\b|COMICIAL")
_LENTO = re.compile(r"LENTIFICA|ONDAS? LENTAS?|ATIVIDADE LENTA|DISFUNCAO|ENCEFALOPAT|ASSIMETRI")
_ALTERADO = re.compile(r"\bANORMAL\b|ALTERAD[OA]|ALTERACAO|FORA D[AO]S? (?:LIMITES|PADROES)")
_NORMAL = re.compile(r"(?:TRACADO|EXAME|EEG|ELETROENCEFALOGRAMA)\w* (?:\w+ ){0,2}NORMAL\b|DENTRO D[OA]S? (?:LIMITES|PADROES)"
                     r"|\bNORMAL PARA A IDADE|PADROES NORMAIS|SEM ANORMALIDADES|LIMITES DA NORMALIDADE|CONCLUSAO:? NORMAL")


def _janelas(linhas: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(linhas):
        l = linhas[i]
        if _TITULO.search(l) and not _DATA.search(l) and not _NAO_LAUDO.search(l):
            jan, fim_ass, j = [l], None, i + 1
            while j < len(linhas) and j - i <= JANELA:
                x = linhas[j]
                if _PAGINA.search(x) or (_OUTRO_EXAME.search(x) and not _TITULO.search(x)):
                    break
                if fim_ass is not None and j > fim_ass:
                    break
                jan.append(x)
                if fim_ass is None and _ASSINATURA.search(x):
                    fim_ass = j + 3
                j += 1
            texto = " | ".join(jan)
            if _CORPO.search(texto):
                out.append(texto)
            i = j
        else:
            i += 1
    return out


_CONCLUSAO = re.compile(r"CONCLUS\w*|IMPRESSAO(?: DIAGNOSTICA)?")
_FIM_CONCLUSAO = re.compile(r"\bDR\.?A?\b|IMPORTANTE|O ELETROENCEFALOGRAMA E UM|A CORRETA INTERPRETACAO|TODO EXAME|OBS\b|NEUROLOGIST"
                            r"|ASSINAD|EMITIDO|<!--")
_NORMAL_CONC = re.compile(r"(?<!A)NORMA(?:L|IS|LS|I)\b|(?:SEM|[NK]AO APRESENTA|[NK]AO MOSTR\w*|AUSENCIA DE) ?(?:\w+ )?ANORMALIDADES"
                          r"|SEM ?ALTERAC|[NK]AO (?:HA|APRESENTA) ALTERAC|[NK]AO EVIDENCIAND\w*[\w| ]{0,40}PATOLOGIC"
                          r"|DENT?R?O D[OA]S? \w{0,3}[IL]\w{0,2}MITES|NORMAL\w{0,2}DADE|NORMALDEDE"
                          r"|DENTRO D[OA]S? (?:LIMITES|PADROES)|NADA DIGNO")


def _decidir(texto: str, conclusao: bool) -> Optional[str]:
    texto = _CAIXA_VAZIA.sub(" ", texto)
    afirmado = _NEGACAO.sub(" ", texto)
    if _EPILEPTIFORME.search(afirmado):
        return "epileptiforme"
    if _LENTO.search(afirmado):
        return "lentificacao"
    if _ALTERADO.search(afirmado):
        return "inespecifico"
    if (_NORMAL_CONC if conclusao else _NORMAL).search(texto):
        return "normal"
    return None


def _tipo_da_janela(t: str) -> Optional[str]:
    # A conclusão do neurologista decide (a descrição técnica cita "ondas agudas", "paroxismos" em formas de negação
    # variadas); sem conclusão que decida, vale a janela inteira.
    # Vale a ÚLTIMA conclusão ("Conclusões: A) especificações... B) resultados... C) Conclusão: EEG digital normal").
    for m in reversed(list(_CONCLUSAO.finditer(t))):
        if re.match(r"\s*(?:DIAGNOSTICA )?SAO ATOS", t[m.end():m.end() + 30]):
            continue  # "a conclusão diagnóstica são atos médicos" (texto-padrão)
        trecho = t[m.end():m.end() + 600]
        fim = _FIM_CONCLUSAO.search(trecho)
        trecho = trecho[:fim.start()] if fim and fim.start() > 15 else trecho[:300]
        r = _decidir(trecho, True)
        if r:
            return r
    return _decidir(t, False)


def ler(texto_entrada: str) -> dict:
    linhas = [_norm(l) for l in (texto_entrada or "").splitlines()]
    linhas = [l for l in linhas if l]
    js = _janelas(linhas)
    if not js:
        return {"eeg": None, "eeg_tipo": None}
    tipos = [x for x in (_tipo_da_janela(t) for t in js) if x]
    for tipo in ("epileptiforme", "lentificacao", "inespecifico"):
        if tipo in tipos:
            return {"eeg": "alterado", "eeg_tipo": tipo}
    if "normal" in tipos:
        return {"eeg": "normal", "eeg_tipo": "normal"}
    return {"eeg": "sem_conclusao", "eeg_tipo": None}
