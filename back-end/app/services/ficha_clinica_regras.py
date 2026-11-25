"""
Leitura determinística (sem LLM) da Ficha Médica da BR MED — STC-1068.

Porta da leitura usada na tabela de treino da STC-1069 (validada em 835 documentos reais) para o modelo
comum `app/models/ficha_clinica.py`. A ficha é um formulário fixo:

    Anamnese: Paciente sem queixas atuais. Não faz uso de medicamentos. Nega doenças crônicas. ...
    História Ocupacional: Nega histórico de acidentes de trabalho. Nega afastamentos ...
    Hábitos de Vida: / Atividade Física: Até 2x por semana. / Nega ... tabagismo / Etilismo: ...
    Observações da Ficha Médica: ...
    Exame Físico ...
    Sinais Vitais: Pressão Sistólica | Pressão Diastólica | Circunferência Abdominal
                   Pulso | Peso | Altura | IMC

Cada item é uma frase de negação ("Nega alergias medicamentosas.") ou "Rótulo: valor"
("Uso de medicamento(s): LOSARTANA 50MG"). A grade de sinais vitais sai do OCR como
"rótulos, depois valores"; a segunda linha da grade vai pelo formato do número, com a trava
IMC = peso/altura².

As regras rodam sobre o texto normalizado (sem acento, maiúsculo, espaço único), mas todo
`trecho` é recortado do texto ORIGINAL por um mapa de posições — o trecho existe literalmente
no texto recebido (até 120 caracteres). Campo que a ficha não traz fica `nao_informado`, com
trecho nulo; nunca vira `nao` por omissão.

Decisões além do ficha.py (campos novos do modelo):
- `nao` das condições segue o ficha.py: vale quando a ficha declara a doença crônica (nega ou
  lista outras). Exceções: gestação nunca vira `nao` por isso (gestar não é doença crônica);
  epilepsia, labirintite/vertigem, transtorno psiquiátrico e gestação também aceitam a negação
  explícita do médico ("Nega convulsão, desmaio, vertigem", "Nega doenças psiquiátricas").
- Epilepsia, labirintite, insuficiência renal, visão monocular e gestação procuram o positivo
  também nas Observações da Ficha Médica, fora de frase de negação. As condições herdadas do
  ficha.py continuam só na doença crônica e na queixa, para manter a equivalência.
- Hérnia: só na doença crônica e na queixa. "Cirurgia(s) prévia(s): HÉRNIA UMBILICAL" é hérnia
  já operada e não conta.
- Diabetes insulinodependente: `sim` por insulina na lista de medicamentos ou por
  INSULINO/INSULINA/tipo 1 na doença declarada; `nao` por "NÃO-INSULINO-DEPENDENTE" (CID E11),
  por diabetes = nao, ou por diabetes declarado com a lista de medicamentos sem insulina.
- Cirurgia há menos de 4 meses: `sim` só com tempo relativo explícito ("HÁ 2 MESES",
  "3 SEMANAS ATRÁS"); `nao` quando a ficha nega cirurgias, ou quando o valor traz UMA cirurgia
  com tempo relativo ≥ 4 meses. Ano/data absolutos ficam `nao_informado`: o texto não traz a
  data de referência. "Pós-operatório" sem tempo também fica `nao_informado`.
- Medicamentos: benzodiazepínicos e hipnóticos-Z saem do psicotrópico para
  `sedativo_benzodiazepinico`. Corticoide (prednisona etc.) NÃO entra em
  `imunossupressor_quimioterapico`: a ficha não diz dose nem duração, e uso curto é comum.
  Antineoplásico hormonal (tamoxifeno, anastrozol) entra, porque indica câncer em tratamento.
  `antidiabetico_oral` herda a lista do ficha.py, que inclui os agonistas de GLP-1 injetáveis
  (semaglutida, liraglutida, tirzepatida) — tudo o que é antidiabético e não é insulina.
- Lactante, fobia de altura/confinamento, doença neurológica e sinais de uso de substância só
  saem com afirmação ou negação explícita ("Nega acrofobia e claustrofobia"), procuradas da
  Anamnese até os Sinais Vitais, fora do histórico familiar (AVC da mãe não é do trabalhador).
  Doença neurológica também vale na doença crônica declarada (CID de AVC, Parkinson).
- Romberg vem do Exame Físico da ficha ("Teste de Romberg negativo."); o laudo de Romberg à
  parte ("## ROMBERG dd/mm/aaaa") fica fora da busca.

Nada aqui sai do processo nem vai para log.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.models.ficha_clinica import (
    AtividadeFisica,
    Campo,
    Etilismo,
    FichaClinica,
    SinaisVitais,
    Tabagismo,
    ficha_vazia,
)

NI = "nao_informado"
TRECHO_MAX = 120

Span = tuple[int, int]


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip()


class _TextoMapeado:
    """Texto normalizado como `_norm`, com a posição de cada caractere no texto original."""

    def __init__(self, original: str, inicio: int, fim: int):
        self.original = original
        self.inicio, self.fim = inicio, fim
        chars: list[str] = []
        mapa: list[int] = []
        for i in range(inicio, fim):
            n = unicodedata.normalize("NFKD", original[i]).encode("ascii", "ignore").decode().upper()
            for ch in n:
                chars.append(ch)
                mapa.append(i)
        bruto = "".join(chars)
        out: list[str] = []
        omapa: list[int] = []
        for m in re.finditer(r"\s+|\S+", bruto):
            if m.group().isspace() or not m.group().strip():
                out.append(" ")
                omapa.append(mapa[m.start()])
            else:
                out.append(m.group())
                omapa.extend(mapa[m.start():m.end()])
        s = "".join(out)
        esq = len(s) - len(s.lstrip(" "))
        dir_ = len(s.rstrip(" "))
        self.n = s[esq:dir_]
        self.mapa = omapa[esq:dir_]

    def trecho(self, span: Optional[Span], foco: Optional[Span] = None, frase: bool = False,
               contexto: bool = False) -> Optional[str]:
        """Pedaço literal do original para o span normalizado (≤ 120 caracteres).

        `frase` estende até o ponto ou a quebra de linha seguinte ("Nega alergias medicamentosas");
        `contexto` recua até o ponto ou a quebra de linha anterior (no máximo 60 caracteres), para o
        termo solto nas Observações não chegar sem o sujeito. Span maior que o limite vira uma
        janela em volta do `foco` (o termo que decidiu), cortada em fronteira de palavra.
        """
        if span is None:
            return None
        a, b = span
        if b <= a:
            return None
        oa, ob = self.mapa[a], self.mapa[b - 1] + 1
        a0, b0 = oa, ob
        if contexto:
            ini = max(self.inicio, oa - 60)
            quebras = [i for i in range(ini, oa) if self.original[i] in ".\n:"]
            oa = quebras[-1] + 1 if quebras else ini
        if frase:
            m = re.compile(r"[.\n]").search(self.original, ob, self.fim)
            ob = max(ob, min(m.start() if m else self.fim, oa + TRECHO_MAX))
        if ob - oa > TRECHO_MAX:
            if foco is not None:
                fa, fb = self.mapa[foco[0]], self.mapa[foco[1] - 1] + 1
                if fb - fa >= TRECHO_MAX:
                    oa, ob = fa, fa + TRECHO_MAX
                else:
                    ini = max(oa, fa - (TRECHO_MAX - (fb - fa)) // 2)
                    ob = min(ob, ini + TRECHO_MAX)
                    oa = max(oa, ob - TRECHO_MAX)
            else:
                ob = oa + TRECHO_MAX
            # Janela cortada no meio da palavra: anda até o espaço, sem perder o termo que decidiu.
            fa, fb = (self.mapa[foco[0]], self.mapa[foco[1] - 1] + 1) if foco else (oa, oa)
            if oa > a0:
                esp = self.original.find(" ", oa, min(fa, oa + 15))
                oa = esp + 1 if esp >= 0 else oa
            if ob < max(b0, self.fim if frase else b0):
                esp = self.original.rfind(" ", max(fb, ob - 15), ob)
                ob = esp if esp > fb else ob
        t = self.original[oa:ob].strip()
        return t or None


# ---------------------------------------------------------------------------
# Vocabulário (herdado do ficha.py; não altere sem medir de novo nos 835)
# ---------------------------------------------------------------------------

_NEGA_VALOR = re.compile(r"^\s*(?:NEGA|NAO|NENHUM|NENHUMA|SEM|AUSENTE|N/?A)\b")

# campo → (frases que dizem "não", rótulo que traz o valor)
_CAMPOS = {
    "queixa_atual": (r"SEM QUEIXAS|NEGA QUEIXAS", r"QUEIXAS?(?:\(S\))?(?: ATUA(?:L|IS))?\s*:"),
    "usa_medicamento": (r"NAO FAZ USO DE MEDICA|NEGA USO DE MEDICA|SEM USO DE MEDICA", r"USO DE MEDICAMENTOS?(?:\(S\))?\s*:|MEDICAMENTOS? EM USO\s*:"),
    "doenca_cronica": (r"NEGA DOENCAS CRONICAS|NEGA COMORBIDADES", r"DOENCAS?(?:\(S\))? CRONICAS?(?:\(S\))?\s*:|COMORBIDADES?\s*:"),
    "cirurgia_previa": (r"NEGA CIRURGIAS", r"CIRURGIAS?(?:\(S\))? PREVIAS?(?:\(S\))?\s*:"),
    "alergia": (r"NEGA ALERGIA", r"ALERGIAS?(?:\(S\))?(?: MEDICAMENTOSAS?(?:\(S\))?)?\s*:"),
    "historico_familiar": (r"NADA DIGNO DE NOTA NA HISTORIA FAMILIAR|NEGA HISTORICO FAMILIAR", r"HISTORICO FAMILIAR\s*:"),
    "internacao": (r"NEGA INTERNAC", r"INTERNACAO(?:\(OES\))?\s*:|INTERNACOES\s*:"),
    "acidente_trabalho": (r"NEGA HISTORICO DE ACIDENTES|NEGA ACIDENTES", r"ACIDENTES? DE TRABALHO\s*:"),
    "afastamento_inss": (r"NEGA AFASTAMENTOS", r"AFASTAMENTOS?(?:\(S\))?(?: PELO INSS| PELA PREVIDENCIA)?\s*:"),
    "doenca_psiquiatrica": (r"NEGA DOENCAS PSIQUIATRICAS", r"DOENCAS?(?:\(S\))? PSIQUIATRICAS?(?:\(S\))?\s*:"),
    "uso_drogas": (r"NEGA USO DE DROGAS|NEGA ETILISMO, NEGA USO DE DROGAS", r"USO DE DROGAS\s*:"),
}

# Doença declarada (doença crônica + queixa). Chave = campo de `Condicoes`.
_DOENCAS = {
    "hipertensao": r"HIPERTENS|\bHAS\b|\bHA\b|PRESSAO ALTA",
    "diabetes": r"DIABET|\bDM\b|\bDM ?[12]\b",
    "dislipidemia": r"DISLIPID|COLESTEROL|TRIGLICER|HIPERCOLEST|LIPIDEMI|LIPOPROTEIN",
    "cardiopatia": r"CARDIOPAT|INFARTO|\bIAM\b|ARRITMIA|INSUFICIENCIA CARDIACA|CORONARI",
    "tireoide": r"TIREOID|TIROID|HIPOTIREO|HIPERTIREO",
    "respiratoria": r"ASMA|BRONQUITE|\bDPOC\b|ENFISEMA",
    # saude_mental no ficha.py
    "transtorno_psiquiatrico": r"DEPRESS|ANSIEDADE|BIPOLAR|ESQUIZO|PSIQUIATR|TRANSTORNO (?:MENTAL|DE ANSIEDADE|DEPRESSIVO|AFETIVO|DO PANICO)",
    "obesidade": r"OBESIDADE",
    "anemia": r"ANEMIA",
    "cancer": r"CANCER|NEOPLASIA|TUMOR|CA DE|CARCINOMA",
    # campos novos
    "hernia": r"HERNIA",
}
# Campos novos que também valem nas Observações da Ficha Médica (fora de frase de negação).
_DOENCAS_OBS = {
    "epilepsia_convulsao": r"EPILEP|CONVULS",
    "labirintite_vertigem": r"LABIRINT|VERTIG|MENIERE|VESTIBUL",
    "insuficiencia_renal_cronica": r"INSUFICIENCIA RENAL|DOENCA RENAL CRONICA|\bIRC\b|\bDRC\b|NEFROPATIA|DIALISE",
    "visao_monocular": r"MONOCULAR|CEGUEIRA (?:EM|DE) UM OLHO|VISAO SUBNORMAL EM UM OLHO|PROTESE OCULAR|ENUCLEAC|ANOFTALM",
}
# "Gravidez" sozinho não conta: aparece em CID de doença já passada ("induzida pela gravidez") e
# "História Gestacional: Data da última menstruação" é só campo do formulário.
_GESTACAO = r"\bGESTANTE\b|\bGRAVIDA\b|\d+ ?SEMANAS? DE (?:GESTACAO|GRAVIDEZ)|\bGESTACAO ATUAL\b"
# Negação explícita do médico ("Nega convulsão, desmaio, vertigem, sonolência").
_NEGACAO_EXPLICITA = {
    "epilepsia_convulsao": r"\bNEGA (?:[A-Z]+,? (?:E |OU )?){0,5}?(?:HISTORICO DE |CRISES? )?(?:CONVULS|EPILEP)",
    "labirintite_vertigem": r"\bNEGA (?:[A-Z]+,? (?:E |OU )?){0,5}?(?:VERTIG|LABIRINT|TONTEIRA|TONTURA)",
    "transtorno_psiquiatrico": r"\bNEGA DOENCAS PSIQUIATRICAS",
    "gestacao": r"\bNEGA (?:GESTACAO|GRAVIDEZ)\b|\bNAO (?:ESTA )?(?:GESTANTE|GRAVIDA)\b",
}
# Só afirmado ou negado explicitamente (sem o "nao" da doença crônica). Positivo procurado da
# Anamnese até os Sinais Vitais (Observações e Exame Físico incluídos), fora de frase de negação.
_EXPLICITOS = {
    "fobia_altura_ou_confinamento": r"ACROFOBI|CLAUSTROFOBI|MEDO DE ALTURA",
    "lactante": r"\bLACTANTE\b|AMAMENTANDO|EM AMAMENTACAO|ALEITAMENTO MATERNO|\bNUTRIZ\b|\bLACTACAO\b",
    "doenca_neurologica": r"DOENCAS? NEUROLOGICAS?|PARKINSON|ESCLEROSE MULTIPLA|\bAVC\b|ACIDENTE VASCULAR (?:CEREBRAL|ENCEFALICO)|"
                          r"MIASTENIA|POLINEUROPATIA|NEUROPATIA PERIFERICA|DEMENCIA|ALZHEIMER|DEFICIT MOTOR",
    "sinais_uso_substancia": r"HALITO ETILICO|EMBRIAGUEZ|\bEBRIO\b|ALCOOLIZAD[OA]\b|SINAIS DE (?:USO DE (?:SUBSTANCIA|DROGA|ALCOOL)|INTOXICACAO)",
}
_NEGACAO_EXPLICITA.update({
    "fobia_altura_ou_confinamento": r"\bNEGA (?:[A-Z]+,? (?:E |OU )?){0,3}?(?:ACROFOBIA|CLAUSTROFOBIA|MEDO DE ALTURA)",
    "lactante": r"\bNAO (?:ESTA )?(?:LACTANTE|AMAMENTANDO)\b|\bNEGA (?:LACTACAO|AMAMENTACAO|ALEITAMENTO)",
    "doenca_neurologica": r"\bNEGA (?:[A-Z]+,? (?:E |OU )?){0,5}?(?:DOENCAS?|ALTERACOES|PROBLEMAS|DEFICITS?) NEUROLOGIC",
    "sinais_uso_substancia": r"\b(?:SEM|AUSENCIA DE) (?:SINAIS DE (?:EMBRIAGUEZ|INTOXICACAO|USO DE)|HALITO ETILICO)",
})
# Romberg do Exame Físico da ficha ("Teste de Romberg negativo.", "ROMBERG- NEGATIVO"). O laudo
# de Romberg à parte ("## ROMBERG dd/mm/aaaa") fica fora: a busca vai só da Anamnese aos Sinais Vitais.
_ROMBERG = re.compile(r"ROMBERG\b[^.:]{0,6}?\b(?:(POSITIV|ALTERAD)|NEGATIV|NORMAL|SEM ALTERAC)")

# Trecho que começa uma negação: positivo dentro dela não conta.
_FRASE_NEGACAO = re.compile(r"\b(?:NEGA|NAO (?:TEM|APRESENTA|POSSUI|REFERE|RELATA)|SEM|AUSENCIA DE)\b[^.:]{0,80}")

_MEDICAMENTOS = {
    "anti_hipertensivo": r"LOSARTANA|ENALAPRIL|CAPTOPRIL|ANLODIPINO|HIDROCLOROTIAZIDA|ATENOLOL|PROPRANOLOL|VALSARTANA|OLMESARTANA|"
                         r"CARVEDILOL|METOPROLOL|NIFEDIPINO|INDAPAMIDA|CLORTALIDONA|ESPIRONOLACTONA|FUROSEMIDA|TELMISARTANA|NAPRIX|"
                         r"ANTI-?HIPERTENS|NIFEDIPIN|ATENALOL|BENICAR|CORUS|ACERTIL|PERINDOPRIL|DIAQUA|VARTAZ|PRESSAT|ARADOIS|COZAAR|"
                         r"DIOVAN|MICARDIS|OLMETEC|SELOZOK|CONCOR|BISOPROLOL|RAMIPRIL|LISINOPRIL|AMLODIPIN|NEBIVOLOL|CANDESARTANA|IRBESARTANA",
    "antidiabetico_oral": r"METFORMINA|GLIBENCLAMIDA|GLICLAZIDA|SITAGLIPTINA|DAPAGLIFLOZINA|EMPAGLIFLOZINA|VILDAGLIPTINA|GLIMEPIRIDA|"
                          r"OZEMPIC|SEMAGLUTIDA|LIRAGLUTIDA|TIRZEPATIDA|GLIFAGE|JARDIANCE|FORXIGA|JANUVIA|GALVUS|DIAMICRON|XIGDUO|MOUNJARO",
    "insulina": r"INSULINA",
    "hipolipemiante": r"SINVASTATINA|ATORVASTATINA|ROSUVASTATINA|PRAVASTATINA|EZETIMIBA|FENOFIBRATO|CIPROFIBRATO|CRESTOR|LIPITOR|VYTORIN",
    "antiagregante": r"\bAAS\b|ACIDO ACETILSALICILICO|CLOPIDOGREL|SOMALGIN|ASPIRINA",
    "anticoagulante": r"VARFARINA|RIVAROXABANA|APIXABANA|DABIGATRANA|MAREVAN|XARELTO",
    # ficha.py menos benzodiazepínicos e zolpidem, que foram para sedativo_benzodiazepinico.
    "psicotropico": r"SERTRALINA|FLUOXETINA|ESCITALOPRAM|CITALOPRAM|PAROXETINA|VENLAFAXINA|DESVENLAFAXINA|DULOXETINA|"
                    r"AMITRIPTILINA|BUPROPIONA|QUETIAPINA|RISPERIDONA|LITIO|CARBAMAZEPINA|"
                    r"VALPROATO|LAMOTRIGINA|TRAZODONA|MIRTAZAPINA",
    "sedativo_benzodiazepinico": r"CLONAZEPAM|ALPRAZOLAM|DIAZEPAM|LORAZEPAM|BROMAZEPAM|CLOBAZAM|CLOXAZOLAM|MIDAZOLAM|NITRAZEPAM|"
                                 r"FLUNITRAZEPAM|FLURAZEPAM|ESTAZOLAM|CLORDIAZEPOXIDO|ZOLPIDEM|ZOPICLONA|"
                                 r"RIVOTRIL|FRONTAL|LEXOTAN|VALIUM|STILNOX|DORMONID|OLCADIL|\bPATZ\b|\bLORAX\b|\bAPRAZ\b",
    "anticonvulsivante": r"FENITOINA|FENOBARBITAL|TOPIRAMATO|LEVETIRACETAM|GABAPENTINA|PREGABALINA|OXCARBAZEPINA",
    "opioide": r"TRAMADOL|CODEINA|MORFINA|OXICODONA|METADONA|FENTANIL|BUPRENORFINA|TAPENTADOL|HIDROMORFONA|NALBUFINA|"
               r"PETIDINA|MEPERIDINA|TRAMAL|TYLEX|PALEXIA|OXYCONTIN|DIMORF|ULTRACET|\bCODEX\b",
    "imunossupressor_quimioterapico": r"METOTREXATO|AZATIOPRINA|CICLOSPORINA|TACROLIMO|SIROLIMO|EVEROLIMO|MICOFENOLATO|LEFLUNOMIDA|"
                                      r"CICLOFOSFAMIDA|HIDROXIUREIA|CAPECITABINA|TAMOXIFENO|ANASTROZOL|LETROZOL|IMATINIBE|"
                                      r"RITUXIMABE|ADALIMUMABE|INFLIXIMABE|ETANERCEPTE|CERTOLIZUMABE|GOLIMUMABE|TOCILIZUMABE|"
                                      r"SECUQUINUMABE|USTEQUINUMABE|HUMIRA|REMICADE|ENBREL|CELLCEPT|PROGRAF|SANDIMMUN|IMURAN|"
                                      r"\bARAVA\b|QUIMIOTERAPI",
    "levotiroxina": r"LEVOTIROXINA|PURAN|SYNTHROID|EUTHYROX",
}

_HISTORICO_FAMILIAR = ("hipertensao", "diabetes", "cardiopatia", "cancer")


# ---------------------------------------------------------------------------
# Anamnese
# ---------------------------------------------------------------------------

def _secao_anamnese(texto: str) -> Optional[_TextoMapeado]:
    """Da "Anamnese:" até "Exame Físico"/"Sinais Vitais" (a ficha da BR MED)."""
    m = re.search(r"(?ms)^\s*(?:##\s*)?Anamnese\s*:(.*?)(?=^\s*(?:##\s*)?(?:Exame F[ií]sico|Sinais Vitais)\b)", texto)
    if not m:
        return None
    return _TextoMapeado(texto, m.start(1), m.end(1))


def _ficha_ate_sinais_vitais(texto: str) -> Optional[_TextoMapeado]:
    """Da "Anamnese:" até a grade de Sinais Vitais: anamnese, observações e Exame Físico."""
    m = re.search(r"(?m)^\s*(?:##\s*)?Anamnese\s*:", texto)
    if not m:
        return None
    f = re.compile(r"(?m)^\s*(?:##\s*)?Sinais Vitais\b").search(texto, m.end())
    return _TextoMapeado(texto, m.end(), f.start() if f else min(len(texto), m.end() + 3500))


def _valor_do_rotulo(sec: str, rotulo: str) -> Optional[tuple[str, Span, Span]]:
    """(valor, span do valor, span rótulo+valor). O valor acaba no ponto, no próximo "RÓTULO:" ou
    na próxima frase padrão."""
    m = re.search(
        rf"(?:{rotulo})\s*(.*?)(?=\.\s|$|\s[A-Z][A-Z()/]+(?:\s[A-Z()/]+){{0,3}}\s*:|"
        rf"\b(?:HISTORIA OCUPACIONAL|HABITOS DE VIDA|OBSERVACOES|NEGA|NAO FAZ|NADA DIGNO|ATIVIDADE FISICA|ETILISMO)\b)",
        sec,
    )
    if not m:
        return None
    g = m.group(1)
    va = m.start(1) + (len(g) - len(g.lstrip(" .,;")))
    vb = m.end(1) - (len(g) - len(g.rstrip(" .,;")))
    if vb < va:
        vb = va
    return sec[va:vb], (va, vb), (m.start(), max(vb, m.end(1) if vb == va else vb))


class _Leitura:
    """Estado de um campo da anamnese: valor, span do valor e o Campo com trecho."""

    def __init__(self, estado: str, valor: Optional[str] = None, span_valor: Optional[Span] = None,
                 span_rotulo: Optional[Span] = None, campo: Optional[Campo] = None):
        self.estado = estado
        self.valor = valor
        self.span_valor = span_valor
        self.span_rotulo = span_rotulo
        self.campo = campo or Campo(valor="nao_informado", trecho=None)


def _campo(valor: str, trecho: Optional[str]) -> Campo:
    if valor == NI or not trecho:
        return Campo(valor="nao_informado", trecho=None)
    return Campo(valor=valor, trecho=trecho)


def _tri(tm: _TextoMapeado, nega: str, rotulo: str) -> _Leitura:
    sec = tm.n
    lido = _valor_do_rotulo(sec, rotulo)
    if lido is not None:
        valor, sv, sr = lido
        if not valor or _NEGA_VALOR.match(valor):
            return _Leitura("nao", campo=_campo("nao", tm.trecho(sr, frase=not valor)))
        return _Leitura("sim", valor, sv, sr, _campo("sim", tm.trecho(sr, foco=sv)))
    m = re.search(nega, sec)
    if m:
        return _Leitura("nao", campo=_campo("nao", tm.trecho((m.start(), m.end()), frase=True)))
    return _Leitura(NI)


def _atividade(tm: _TextoMapeado) -> AtividadeFisica:
    m = re.search(r"ATIVIDADE FISICA\s*:\s*([^.]{0,60})", tm.n)
    if not m:
        return AtividadeFisica(valor="nao_informado", trecho=None)
    v = m.group(1)
    if re.search(r"NUNCA|SEDENTAR|NAO PRATICA|NEGA", v):
        valor = "sedentario"
    elif re.search(r"ATE 2|1 ?X|2 ?X|UMA|DUAS|ESPORADIC|EVENTUAL", v):
        valor = "ate_2x_semana"
    elif re.search(r"3|4|5|6|7|MAIS|DIARI|TODOS", v):
        valor = "3x_ou_mais_semana"
    else:
        valor = "outro"
    trecho = tm.trecho((m.start(), max(m.end(1), m.end())))
    return AtividadeFisica(valor=valor, trecho=trecho) if trecho else AtividadeFisica(valor="nao_informado", trecho=None)


def _etilismo(tm: _TextoMapeado) -> Etilismo:
    sec = tm.n
    m = re.search(r"ETILISMO\s*:\s*([^.]{0,60})", sec)
    if m:
        v = m.group(1)
        if _NEGA_VALOR.match(v):
            valor = "nao"
        elif re.search(r"EVENTUAL|SOCIAL|RARAMENTE|OCASIONAL|FINAL DE SEMANA|FINS DE SEMANA", v):
            valor = "eventual"
        else:
            valor = "sim"
        trecho = tm.trecho((m.start(), max(m.end(1), m.end())))
    elif (m := re.search(r"NEGA ETILISMO", sec)):
        valor, trecho = "nao", tm.trecho((m.start(), m.end()), frase=True)
    else:
        return Etilismo(valor="nao_informado", trecho=None)
    return Etilismo(valor=valor, trecho=trecho) if trecho else Etilismo(valor="nao_informado", trecho=None)


def _tabagismo(tm: _TextoMapeado) -> Tabagismo:
    sec = tm.n
    if (m := re.search(r"EX-? ?TABAGIST|PAROU DE FUMAR|EX FUMANTE|EX-FUMANTE", sec)):
        valor = "ex"
    elif (m := re.search(r"(?:VOLUME|TEMPO) DE TABAGISMO\s*:|TABAGISMO\s*:\s*(?!NEGA|NAO)|TABAGISTA|FUMANTE", sec)):
        valor = "sim"
    elif (m := re.search(r"NEGA (?:[A-Z ,]*?)TABAGISMO|TABAGISMO\s*:\s*(?:NEGA|NAO)", sec)):
        valor = "nao"
    else:
        return Tabagismo(valor="nao_informado", trecho=None)
    trecho = tm.trecho((m.start(), m.end()), foco=(m.start(), m.end()), frase=True)
    return Tabagismo(valor=valor, trecho=trecho) if trecho else Tabagismo(valor="nao_informado", trecho=None)


def _no_valor(tm: _TextoMapeado, rx: str, leituras: list[_Leitura]) -> Optional[Campo]:
    """`sim` se o termo aparece no valor de algum dos campos (na ordem dada)."""
    for le in leituras:
        if le.estado != "sim" or le.span_valor is None:
            continue
        va, vb = le.span_valor
        m = re.compile(rx).search(tm.n, va, vb)
        if m:
            t = tm.trecho(le.span_rotulo, foco=(m.start(), m.end()))
            if t:
                return Campo(valor="sim", trecho=t)
    return None


# Histórico familiar (e as observações dele): doença da mãe não é do trabalhador.
_FAMILIA = re.compile(
    r"HISTORICO FAMILIAR\s*:.*?(?=HISTORIA OCUPACIONAL|INTERNACAO|OBSERVACOES DA FICHA|HABITOS DE VIDA|"
    r"OBSERVACOES NO HISTORICO FAMILIAR|$)|HISTORIA FAMILIAR"
)


def _fora_de_negacao(tm: _TextoMapeado, rx: str, inicio: int) -> Optional[Campo]:
    """Positivo (do `inicio` ao fim da seção) fora de frase de negação e fora do histórico familiar."""
    fora = [(m.start(), m.end()) for m in _FRASE_NEGACAO.finditer(tm.n, inicio)]
    fora += [(m.start(), m.end()) for m in _FAMILIA.finditer(tm.n)]
    for m in re.compile(rx).finditer(tm.n, inicio):
        if any(a <= m.start() < b for a, b in fora):
            continue
        t = tm.trecho((m.start(), m.end()), foco=(m.start(), m.end()), frase=True, contexto=True)
        if t:
            return Campo(valor="sim", trecho=t)
    return None


_TEMPO_REL = re.compile(
    r"\b(?:HA|A) (?:MAIS DE |MENOS DE |CERCA DE )?(\d{1,3}|UM|UMA|DOIS|DUAS|TRES|QUATRO|CINCO|SEIS) (DIAS?|SEMANAS?|MES(?:ES)?|ANOS?)\b"
    r"|\b(\d{1,3}|UM|UMA|DOIS|DUAS|TRES) (DIAS?|SEMANAS?|MES(?:ES)?|ANOS?) ATRAS\b"
)
_POR_EXTENSO = {"UM": 1, "UMA": 1, "DOIS": 2, "DUAS": 2, "TRES": 3, "QUATRO": 4, "CINCO": 5, "SEIS": 6}


def _meses(qtd: str, unidade: str) -> float:
    n = int(qtd) if qtd.isdigit() else _POR_EXTENSO[qtd]
    if unidade.startswith("DIA"):
        return n / 30
    if unidade.startswith("SEMANA"):
        return n / 4.3
    if unidade.startswith("MES"):
        return n
    return n * 12


def _cirurgia_recente(tm: _TextoMapeado, cir: _Leitura) -> Campo:
    if cir.estado == "nao":
        return cir.campo  # nega cirurgias: nenhuma, logo nenhuma recente
    if cir.estado != "sim" or cir.span_valor is None:
        return Campo(valor="nao_informado", trecho=None)
    va, vb = cir.span_valor
    tempos = []
    for m in _TEMPO_REL.finditer(tm.n, va, vb):
        qtd, un = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        tempos.append((_meses(qtd, un), m))
    if not tempos:
        return Campo(valor="nao_informado", trecho=None)
    recente = next(((meses, m) for meses, m in tempos if meses < 4 and "MAIS DE" not in m.group(0)), None)
    if recente:
        t = tm.trecho(cir.span_rotulo, foco=(recente[1].start(), recente[1].end()))
        return _campo("sim", t)
    # "nao" só quando o valor é uma cirurgia só (sem lista que esconda outra sem data).
    lista = re.search(r",|;|/|\bE\b|\d{4}", tm.n[va:vb])
    if len(tempos) == 1 and not lista:
        return _campo("nao", tm.trecho(cir.span_rotulo, foco=(tempos[0][1].start(), tempos[0][1].end())))
    return Campo(valor="nao_informado", trecho=None)


# ---------------------------------------------------------------------------
# Sinais vitais (porta literal do ficha.py)
# ---------------------------------------------------------------------------

_ROTULOS_VITAIS = (
    ("pa_sistolica", r"SISTOLICA"),
    ("pa_diastolica", r"DIASTOLICA"),
    ("circ_abdominal", r"CIRCUNF|CIRC\.?\s*ABD|^ABDOMINAL"),
    ("freq_cardiaca", r"PULSO|FREQUENCIA CARDIACA|\bFC\b"),
    ("peso", r"\bPESO\b"),
    ("altura", r"ALTURA"),
    ("imc", r"\bIMC\b"),
)
_FAIXA = {  # o que é possível; fora disso o número é de outro campo
    "pa_sistolica": (70, 260), "pa_diastolica": (35, 160), "circ_abdominal": (45, 200),
    "freq_cardiaca": (30, 200), "peso": (30, 250), "altura": (120, 220), "imc": (12, 70),
}
_NUM_CRU = re.compile(r"^(?:##\s*)?(\d{1,3}(?:[.,]\d{1,3})?)\s*\.?\s*(?:CM|KG|BPM|MMHG|M)?\s*[-.]?$", re.I)
_LINHA1 = ("pa_sistolica", "pa_diastolica", "circ_abdominal")
# Pedaço de rótulo partido pelo OCR que sobra sem nome: só a unidade, "(cm):". Vale só a unidade
# do próprio campo — "(mmHg):" depois de "Peso (kg):" é da diastólica, e o número abaixo é dela.
_UNIDADE = re.compile(r"^\(?\s*(CM|KG|BPM|MMHG|M|KG/M2?)\s*\)?\s*:?$", re.I)
_UNIDADES_DO_CAMPO = {
    "pa_sistolica": {"MMHG"}, "pa_diastolica": {"MMHG"}, "circ_abdominal": {"CM"},
    "freq_cardiaca": {"BPM"}, "peso": {"KG"}, "altura": {"CM", "M"}, "imc": {"KG/M2", "KG/M"},
}


def _numero(s: str) -> Optional[tuple[float, str]]:
    """(valor, formato): "70,00" → peso ("virgula2"), "24.80" → IMC ("ponto"), "168" → "inteiro"."""
    m = _NUM_CRU.match(s.strip())
    if not m:
        return None
    cru = m.group(1)
    v = float(cru.replace(",", "."))
    if re.fullmatch(r"\d{2,3},\d{2}", cru):
        return v, "virgula2"
    if "." in cru:
        return v, "ponto"
    if "," in cru:
        return v, "virgula"
    return v, "inteiro"


def _por_formato(nums: list[tuple[float, str]], chaves: list[str]) -> dict[str, float]:
    """Segunda linha da grade (pulso, peso, altura, IMC): o OCR não mantém a ordem; o formato decide."""
    out: dict[str, float] = {}
    livres = []
    for v, f in nums:
        if f == "virgula2" and "peso" in chaves and "peso" not in out:
            out["peso"] = v
        elif f == "ponto" and "imc" in chaves and "imc" not in out and 12 <= v <= 70:
            out["imc"] = v
        else:
            livres.append((v, f))
    for v, f in livres:
        if f == "virgula" and v < 3 and "altura" in chaves and "altura" not in out:
            out["altura"] = v  # metros
        elif f == "inteiro" and 120 <= v <= 220 and "altura" in chaves and "altura" not in out:
            out["altura"] = v
        elif f == "inteiro" and 30 <= v < 120 and "freq_cardiaca" in chaves and "freq_cardiaca" not in out:
            out["freq_cardiaca"] = v
        elif "peso" in chaves and "peso" not in out and 30 <= v <= 250:
            out["peso"] = v
    return out


def _sinais_vitais(texto: str) -> dict[str, Optional[float]]:
    linhas = texto.splitlines()
    inicio = next((i for i, l in enumerate(linhas) if re.search(r"PRESSAO SISTOLICA", _norm(l))), None)
    out: dict[str, Optional[float]] = {k: None for k, _ in _ROTULOS_VITAIS}
    if inicio is None:
        return out
    janela = [l.strip() for l in linhas[inicio:inicio + 32] if l.strip()]
    fim = next((i for i, l in enumerate(janela) if re.search(r"OBSERVAC", _norm(l))), len(janela))
    janela = janela[:fim]

    def rotulo(l):
        n = _norm(l).lstrip("# ")
        return next((k for k, rx in _ROTULOS_VITAIS if re.search(rx, n)), None)

    em_linha = any(rotulo(l) and l.rstrip().endswith(":") or re.search(r"\):\s*\d", l) for l in janela)
    if em_linha:
        # "Rótulo: valor" — o valor está na mesma linha ou logo abaixo. Rótulo partido pelo OCR
        # ("Abdominal" / "(cm):" / "62") empurra o valor até 3 linhas: pula só pedaço do mesmo
        # rótulo ou a unidade do campo e para em outro rótulo, para não roubar o valor dele.
        for i, l in enumerate(janela):
            k = rotulo(l)
            if not k or out[k] is not None:
                continue
            m = re.search(r":\s*(\d{1,3}(?:[.,]\d{1,3})?)", l)
            if m:
                out[k] = float(m.group(1).replace(",", "."))
                continue
            for seg in janela[i + 1:i + 4]:
                k2 = rotulo(seg)
                if k2 and k2 != k:
                    break
                if n := _numero(seg):
                    out[k] = n[0]
                    break
                u = _UNIDADE.match(seg)
                if re.search(r"\d", seg) or not (k2 or u and u.group(1).upper() in _UNIDADES_DO_CAMPO[k]):
                    break
    else:
        # Grade: rótulos e depois valores. Linha 1 (PA sistólica, diastólica, circunferência) mantém
        # a ordem; linha 2 (pulso, peso, altura, IMC) vai pelo formato do número.
        rot = [k for l in janela if (k := rotulo(l))]
        nums = [n for l in janela if not rotulo(l) and (n := _numero(l))]
        linha1 = [k for k in rot if k in _LINHA1]
        linha2 = [k for k in rot if k not in _LINHA1]
        for k, (v, _) in zip(linha1, nums[: len(linha1)]):
            out[k] = v
        out.update(_por_formato(nums[len(linha1):], linha2))
    if out["altura"] is not None and out["altura"] < 3:
        out["altura"] = round(out["altura"] * 100, 1)
    for k, (lo, hi) in _FAIXA.items():
        if out[k] is not None and not lo <= out[k] <= hi:
            out[k] = None
    if out["pa_sistolica"] is not None and out["pa_diastolica"] is not None and out["pa_sistolica"] <= out["pa_diastolica"]:
        out["pa_sistolica"] = out["pa_diastolica"] = None
    # IMC tem que fechar com peso/altura²: se não fecha, algum dos três foi trocado e os três saem.
    p, a, i = out["peso"], out["altura"], out["imc"]
    if p and a and i and abs(p / (a / 100) ** 2 - i) > 1.0:
        out["peso"] = out["altura"] = out["imc"] = None
    elif p and a and i is None:
        out["imc"] = round(p / (a / 100) ** 2, 2)
    return out


# ---------------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------------

def ler_ficha_regras(texto: str) -> FichaClinica:
    """Lê a Ficha Médica da BR MED sem LLM. Fora do formulário, devolve a ficha vazia
    (com os sinais vitais, se a grade estiver no texto)."""
    ficha = ficha_vazia("regras")
    texto = texto or ""

    v = _sinais_vitais(texto)
    ficha.sinais_vitais = SinaisVitais(
        pa_sistolica=v["pa_sistolica"], pa_diastolica=v["pa_diastolica"], freq_cardiaca=v["freq_cardiaca"],
        peso_kg=v["peso"], altura_cm=v["altura"], imc=v["imc"], circ_abdominal_cm=v["circ_abdominal"],
    )

    tm = _secao_anamnese(texto)
    if tm is None:
        return ficha
    sec = tm.n

    le = {campo: _tri(tm, nega, rotulo) for campo, (nega, rotulo) in _CAMPOS.items()}
    an = ficha.anamnese
    for campo in ("queixa_atual", "usa_medicamento", "doenca_cronica", "cirurgia_previa", "alergia",
                  "internacao", "acidente_trabalho", "afastamento_inss", "uso_drogas"):
        setattr(an, campo, le[campo].campo)
    an.cirurgia_ha_menos_de_4_meses = _cirurgia_recente(tm, le["cirurgia_previa"])
    an.tabagismo = _tabagismo(tm)
    an.etilismo = _etilismo(tm)
    an.atividade_fisica = _atividade(tm)

    # Condições: da doença crônica declarada (e da queixa); "nao" só quando a ficha declara a
    # doença crônica (nega ou lista outra).
    dc = le["doenca_cronica"]
    fontes_doenca = [dc, le["queixa_atual"]]
    nao_cronica = _campo("nao", dc.campo.trecho) if dc.estado in ("nao", "sim") else None
    m_obs = re.search(r"OBSERVACOES DA FICHA MEDICA\s*:", sec)
    inicio_obs = m_obs.end() if m_obs else None

    cond = ficha.condicoes
    for d, rx in _DOENCAS.items():
        achado = _no_valor(tm, rx, fontes_doenca)
        if achado is None and d == "transtorno_psiquiatrico":
            achado = _no_valor(tm, r".", [le["doenca_psiquiatrica"]])
        setattr(cond, d, achado or _negacao(tm, d) or nao_cronica or Campo(valor="nao_informado", trecho=None))
    for d, rx in _DOENCAS_OBS.items():
        achado = _no_valor(tm, rx, fontes_doenca)
        if achado is None and inicio_obs is not None:
            achado = _fora_de_negacao(tm, rx, inicio_obs)
        setattr(cond, d, achado or _negacao(tm, d) or nao_cronica or Campo(valor="nao_informado", trecho=None))
    gest = _no_valor(tm, _GESTACAO, fontes_doenca) or _fora_de_negacao(tm, _GESTACAO, 0)
    cond.gestacao = gest or _negacao(tm, "gestacao") or Campo(valor="nao_informado", trecho=None)

    # Só explícito: afirmado (fora de negação) ou negado.
    reg = _ficha_ate_sinais_vitais(texto) or tm
    for d, rx in _EXPLICITOS.items():
        achado = None
        if d == "doenca_neurologica":
            achado = _no_valor(tm, rx, fontes_doenca)
        achado = achado or _fora_de_negacao(reg, rx, 0)
        valor = achado or _negacao(reg, d) or Campo(valor="nao_informado", trecho=None)
        if d == "sinais_uso_substancia":
            ficha.exame_fisico.sinais_uso_substancia = valor
        else:
            setattr(cond, d, valor)
    ficha.exame_fisico.romberg_positivo = _romberg(reg)

    # Histórico familiar.
    hf = le["historico_familiar"]
    nao_familia = _campo("nao", hf.campo.trecho) if hf.estado in ("nao", "sim") else None
    for d in _HISTORICO_FAMILIAR:
        achado = _no_valor(tm, _DOENCAS[d], [hf])
        setattr(ficha.historico_familiar, d, achado or nao_familia or Campo(valor="nao_informado", trecho=None))

    # Medicamentos: classe pelo princípio ativo ou nome comercial na lista declarada.
    um = le["usa_medicamento"]
    nao_med = _campo("nao", um.campo.trecho) if um.estado in ("nao", "sim") else None
    med = ficha.medicamentos
    for c, rx in _MEDICAMENTOS.items():
        achado = _no_valor(tm, rx, [um])
        setattr(med, c, achado or nao_med or Campo(valor="nao_informado", trecho=None))

    cond.diabetes_insulinodependente = _diabetes_insulino(tm, cond.diabetes, med.insulina, fontes_doenca, nao_med)

    # Medição da STC-1070 (50 fichas revisadas à mão): "nega doenças crônicas" virava "nao" em
    # obesidade com IMC 30–43 impresso na própria ficha (10 de 50) e em visão monocular sem acuidade
    # nenhuma no documento. Obesidade passa a vir do IMC; visão monocular, só do que está escrito.
    cond.obesidade = _obesidade(texto, ficha.sinais_vitais.imc, cond.obesidade)
    if cond.visao_monocular.valor == "nao" and not _negacao(tm, "visao_monocular"):
        cond.visao_monocular = Campo(valor="nao_informado", trecho=None)
    return ficha


def _obesidade(texto: str, imc: Optional[float], declarada: Campo) -> Campo:
    """Sim com IMC >= 30, não com IMC < 30. Sem IMC, só o que a ficha afirma (nunca a negação genérica)."""
    if imc is not None:
        trecho = None
        for forma in (f"{imc:.2f}", f"{imc:.2f}".replace(".", ","), f"{imc:.1f}", f"{imc:.1f}".replace(".", ",")):
            if forma in texto:
                trecho = forma
                break
        return Campo(valor="sim" if imc >= 30 else "nao", trecho=trecho)
    if declarada.valor == "sim":
        return declarada
    return Campo(valor="nao_informado", trecho=None)


def _negacao(tm: _TextoMapeado, campo: str) -> Optional[Campo]:
    rx = _NEGACAO_EXPLICITA.get(campo)
    if not rx:
        return None
    m = re.search(rx, tm.n)
    if not m:
        return None
    return _campo("nao", tm.trecho((m.start(), m.end()), foco=(m.start(), m.end()), frase=True))


def _romberg(reg: _TextoMapeado) -> Campo:
    achados = list(_ROMBERG.finditer(reg.n))
    m = next((m for m in achados if m.group(1)), None) or (achados[0] if achados else None)
    if m is None:
        return Campo(valor="nao_informado", trecho=None)
    return _campo("sim" if m.group(1) else "nao", reg.trecho((m.start(), m.end()), frase=True))


def _diabetes_insulino(tm: _TextoMapeado, diabetes: Campo, insulina: Campo,
                       fontes: list[_Leitura], nao_med: Optional[Campo]) -> Campo:
    if insulina.valor == "sim":
        return insulina
    if diabetes.valor == "sim":
        # Só no valor que fala de diabetes: "NAO-INSULINO-DEPENDENTE" (CID E11) é o oposto.
        for le in fontes:
            if le.estado != "sim" or le.span_valor is None:
                continue
            va, vb = le.span_valor
            for m in re.compile(r"(NAO[- ]?)?INSULINO|INSULINA|\bDM ?(?:TIPO )?(?:1|I)\b|DIABETES (?:MELLITUS )?TIPO (?:1|I)\b").finditer(tm.n, va, vb):
                t = tm.trecho(le.span_rotulo, foco=(m.start(), m.end()))
                if t:
                    return Campo(valor="nao" if m.group(1) else "sim", trecho=t)
        # Diabetes declarado e a lista de medicamentos conhecida, sem insulina.
        return nao_med or Campo(valor="nao_informado", trecho=None)
    if diabetes.valor == "nao":
        return diabetes
    return Campo(valor="nao_informado", trecho=None)
