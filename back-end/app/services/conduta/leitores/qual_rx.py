"""
Laudo de RX de TÓRAX e de COLUNA lido do texto de OCR do prontuário (sem LLM, sem rede). Pedido do Breno (23/11).

Saída, para cada exame (rx_torax, rx_coluna):
  <exame>_laudo     "descritivo" | "so_oit" | None   (None: nenhum laudo no texto)
  <exame>           "normal" | "alterado" | None     (conclusão do laudo descritivo)
  <exame>_achados   "osteofitos|escoliose" ...       (achados afirmados, em ordem alfabética; "" se nenhum)
  rx_torax_oit      "normal" | "alterado" | "ilegivel" | None   (formulário OIT; None = não há formulário)

Regras (medidas em 23/11 numa amostra de 400 + 400 da base de 10 mil):
- Janela do laudo: de uma linha com o título (Radiografia/RX/Raio-X de tórax, Tórax PA, Coluna lombo-sacra...)
  até a mudança de página, o título de outro exame ou 4 linhas depois da assinatura. A linha da lista de
  procedimentos do ASO ("RADIOGRAFIA DE TÓRAX - PADRÃO OIT - 15/09/2025") não abre janela.
- Só é laudo descritivo a janela que tem corpo de laudo (parênquima, seios costofrênicos, área cardíaca; corpos
  vertebrais, espaços discais, lordose...). Sem isso é só o nome do exame.
- Formulário OIT: o OCR traz TODAS as opções impressas ("0/0 0/1 1/0...", "Sim/Não", "placas pleurais") e quase
  sempre perde o X da marcada. Lido pelo próprio formulário, em qualquer parte do texto (nem sempre há título de RX
  perto). Só vale a resposta da 1B "Radiografia normal" com marca explícita — "(X) SIM" → normal, "(X) NÃO" →
  alterado; marca perdida → "ilegivel". O texto do formulário nunca vira achado (as opções impressas dariam
  espessamento/placa pleural falsos).
- Negação: o laudo normal cita os achados para negá-los ("sem opacidades, nódulos ou consolidação", "ausência de
  derrame", "não há sinais de fratura"). Achado depois de SEM/AUSÊNCIA/NÃO HÁ/LIVRE na mesma frase não conta; a
  negação vale até o fim da frase ou até "com", "porém", "observa-se".
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip().lstrip("#* ").strip()


_TITULO = {
    "rx_torax": re.compile(r"(?:RADIOGRAF\w*|RAIOS?[ -]?X|\bRX\b|TELE ?RRADIOGRAF\w*|TELERADIOGRAF\w*)\W{0,3}(?:SIMPLES )?"
                           r"(?:D[OE] |DO )?TORAX|\bTORAX\b\W{0,3}(?:EM |-)?\s*(?:PA|AP)\b|RX-TORAX"),
    "rx_coluna": re.compile(r"(?:RADIOGRAF\w*|RAIOS?[ -]?X|\bRX\b)\W{0,3}(?:SIMPLES )?(?:D[AE] )?COLUNA"
                            r"|\bCOLUNA (?:CERVICAL|DORSAL|TORACICA|LOMBAR|LOMBO|LOMBOSSACRA|SACRAL|TORACO|DORSO)"),
}
_DATA_ASO = re.compile(r"\d{1,2} ?/ ?\d{1,2} ?/ ?\d{2,4}\s*$|-\s*\d{1,2}/\d{1,2}/\d{2,4}")
_NAO_LAUDO = re.compile(r"\?|PROCEDIMENTOS? REALIZADOS|PERFORMED PROCEDURES|EXAMES COMPLEMENTARES|STANDARD OIT RADIOGRAPHY"
                        r"|LUMBAR COLUMN RADIOGRAPHY|CHEST - STANDARD")
_PAGINA = re.compile(r"<!--\s*PAGINA", re.I)
_OUTRO_EXAME = re.compile(
    r"^(?:#+ )?(?:AUDIOMETR|AUDIOLOG|ELETROCARDIO|\bECG\b|ACUIDADE VISUAL|ESPIROMETR|HEMOGRAMA|TESTE ERGOMETRICO"
    r"|ELETROENCEFALO|AVALIACAO PSICO|AVALIACAO ODONTO|FICHA MEDICA|ATESTADO DE SAUDE|GLICEMIA|ULTRASSONOGRAF|ULTRA-SON)")
_ASSINATURA = re.compile(r"\bCRM\b|RADIOLOGISTA|LAUDO EMITIDO POR|ASSINADO (?:DIGITALMENTE|ELETRONICAMENTE)|\bDR\.? \[NOME\]|\bDRA\.? \[NOME\]")
_OIT = re.compile(r"LEITURA OIT|PEQUENAS OPACIDADES|PROFUSAO|QUALIDADE TECNICA|CONSISTENTE COM PNEUMOCONIOSE|GRANDES OPACIDADES")
JANELA = 45

_CORPO = {
    "rx_torax": re.compile(r"PARENQUIMA|CAMPOS PULMONARES|SEIOS? COSTOFRENIC|AREA CARDIACA|INDICE CARDIOTORAC|HILOS? PULMONAR"
                           r"|MEDIASTINO|CUPULAS? DIAFRAGMA|TRAQUEIA|TRAMA (?:BRONCO)?VASCULAR|PULMOES|ARCABOUCO|TRANSPARENCIA"),
    "rx_coluna": re.compile(r"CORPOS? VERTEBR|ESPACOS? (?:INTER ?-?)?(?:DISCA|VERTEBRA)|PEDICULOS|LORDOSE|CIFOSE|ALINHAMENTO"
                            r"|ARTICULACOES? (?:INTER|SACRO|ZIGO)|ALTURA DOS CORPOS|MINERALIZACAO|ESTRUTURAS OSSEAS|ESCOLIOSE"),
}
_ACHADOS = {
    "rx_torax": {
        "nodulo": r"NODUL\w*",
        "opacidade": r"OPACIDADE\w*|INFILTRAD\w*|CONSOLIDA\w*",
        "cardiomegalia": r"CARDIOMEGALIA|AUMENTO D[AO] (?:AREA|SILHUETA) CARDIACA|AREA CARDIACA AUMENTADA|INDICE CARDIOTORACICO AUMENTADO",
        "derrame": r"DERRAME",
        "espessamento_pleural": r"ESPESSAMENTO PLEURAL|ESPESSAMENTO D[AO]S? PLEURA|PLACAS? PLEURA\w*",
        "granuloma": r"GRANULOMA\w*",
        "sequela_fibrose": r"SEQUELA\w*|CICATRI\w*|FIBROS\w*|ESTRIAS? FIBR\w*|TRAVES FIBR\w*",
        "enfisema": r"ENFISEMA\w*|HIPERINSUFLA\w*|HIPERTRANSPAREN\w*|BOLHAS?\b",
        "bronquite_bronquiectasia": r"BRONQUIECTASIA\w*|ESPESSAMENTO (?:PERI)?BRONQU\w*|BRONCOPATIA|ACENTUACAO DA TRAMA",
        "atelectasia": r"ATELECTASIA\w*",
        "aorta": r"ATEROMA\w*|ALONGAMENTO D[AO] AORTA|ECTASIA D[AO] AORTA|CALCIFICACAO (?:D[AO] |N[AO] )?(?:CROSSA|AORTA|BOTAO)",
        "alteracao_ossea": r"OSTEOFIT\w*|ESCOLIOSE|ESPONDILO\w*|FRATURA",
    },
    "rx_coluna": {
        "osteofitos": r"OSTEOFIT\w*|OSTEOCITOS MARGINAIS|BICOS? DE PAPAGAIO",
        "degenerativa": r"ESPONDILOARTROSE|ESPONDILOSE|ARTROSE|ARTROPATIA DEGENERATIVA|ALTERACO\w* DEGENERATIV\w*|DEGENERATIV\w*|UNCOARTROSE",
        "discopatia": r"DISCOPATIA|PINCAMENTO|REDUCAO D[AO]S? (?:ALTURA D[AO]S? )?ESPACOS?|ESPACOS? (?:INTER ?-?)?(?:DISCA|VERTEBRA)\w* (?:COM )?REDU\w*|DIMINUICAO D[AO]S? ESPACO",
        "escoliose": r"ESCOLIOSE|DESVIO LATERAL|ATITUDE ESCOLIOTICA|CURVA ESCOLIOTICA",
        "alteracao_curvatura": r"RETIFICACAO|HIPERLORDOSE|HIPOLORDOSE|ACENTUACAO D[AO] (?:LORDOSE|CIFOSE)|HIPERCIFOSE|LORDOSE (?:ACENTUADA|DIMINUIDA|REDUZIDA|RETIFICADA)",
        "espondilolistese": r"ESPONDILOLISTESE|ANTEROLISTESE|RETROLISTESE|LISTESE|ESPONDILOLISE",
        "anomalia_transicao": r"VERTEBRA DE TRANSICAO|SACRALIZACAO|LOMBARIZACAO|ESPIN[HA]+ BIFIDA|MEGAPOFISE",
        "fratura": r"FRATURA\w*|ACUNHAMENTO|ACHATAMENTO",
        "schmorl_esclerose": r"SCHMORL|ESCLEROSE (?:SUBCONDRAL|D[AO]S? (?:PLACAS|PLATOS))",
    },
}
_ACHADOS = {e: {k: re.compile(r"\b(?:" + v + r")") for k, v in d.items()} for e, d in _ACHADOS.items()}
_NEGA = re.compile(r"\bSEM\b|AUSENCIA|AUSENTES?\b|NAO (?:HA|SE (?:OBSERVA|EVIDENCIA|IDENTIFICA|VISUALIZA|NOTA)|FORAM|OBSERVA|EVIDENC|APRESENTA)"
                   r"|\bLIVRES?\b|NEGATIV|DESCART|AFASTA|INEXIST")
_QUEBRA_NEGA = re.compile(r"\bCOM\b|\bPOREM\b|\bMAS\b|ENTRETANTO|OBSERVA-SE|NOTA-SE|NOTAM-SE|IDENTIFICA-SE|EVIDENCIA-SE")


def _afirmado(frase: str, inicio: int) -> bool:
    antes = frase[:inicio]
    nega = list(_NEGA.finditer(antes))
    if not nega:
        return True
    return bool(_QUEBRA_NEGA.search(antes[nega[-1].end():]))


def _janelas(linhas: list[str], exame: str) -> list[list[str]]:
    out = []
    i = 0
    while i < len(linhas):
        l = linhas[i]
        if _TITULO[exame].search(l) and not _DATA_ASO.search(l) and not _NAO_LAUDO.search(l):
            jan, fim_ass = [l], None
            j = i + 1
            while j < len(linhas) and j - i <= JANELA:
                x = linhas[j]
                if _PAGINA.search(x) or _OUTRO_EXAME.search(x):
                    break
                if fim_ass is not None and j > fim_ass:
                    break
                jan.append(x)
                if fim_ass is None and _ASSINATURA.search(x):
                    fim_ass = j + 4
                j += 1
            out.append(jan)
            i = j
        else:
            i += 1
    return out


_OIT_NORMAL = re.compile(r"RADIOGRAFIA NORMAL[\s:.\-]{0,10}(?:COMENTARIOS?[\s:.\-]{0,5})?(.{0,90})")
_MARCA = r"[(\[]\s*X\s*[)\]]"


def _oit(texto: str) -> Optional[str]:
    if not _OIT.search(texto):
        return None
    for m in _OIT_NORMAL.finditer(texto):
        resp = m.group(1)
        if re.search(_MARCA + r"\s*SIM", resp):
            return "normal"
        if re.search(_MARCA + r"\s*NAO", resp):
            return "alterado"
    return "ilegivel"


def _ler_exame(linhas: list[str], exame: str) -> dict:
    laudo: Optional[str] = None
    achados: set[str] = set()
    for jan in _janelas(linhas, exame):
        texto = " ".join(jan)
        if _OIT.search(texto):
            laudo = laudo or "so_oit"
            # Descritivo antes do formulário na mesma janela ainda vale.
            corte = _OIT.search(texto).start()
            texto = texto[:corte]
        if not _CORPO[exame].search(texto):
            continue
        laudo = "descritivo"
        for frase in re.split(r"[.;:]\s", texto):
            for nome, rx in _ACHADOS[exame].items():
                for m in rx.finditer(frase):
                    if _afirmado(frase, m.start()):
                        achados.add(nome)
                        break
    out = {f"{exame}_laudo": laudo, f"{exame}_achados": "|".join(sorted(achados))}
    oit = _oit(" ".join(linhas)) if exame == "rx_torax" else None
    if exame == "rx_torax":
        out["rx_torax_oit"] = oit
        if laudo is None and oit is not None:
            laudo = out["rx_torax_laudo"] = "so_oit"
    conclusao = None
    if laudo == "descritivo":
        conclusao = "alterado" if achados else "normal"
    elif laudo == "so_oit" and oit in ("normal", "alterado"):
        conclusao = oit
    out[exame] = conclusao
    return out


def ler(texto_entrada: str) -> dict:
    linhas = [_norm(l) for l in (texto_entrada or "").splitlines()]
    linhas = [l for l in linhas if l]
    out = {}
    for exame in ("rx_torax", "rx_coluna"):
        out.update(_ler_exame(linhas, exame))
    return out
