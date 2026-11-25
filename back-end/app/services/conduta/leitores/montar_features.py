"""
STC-1069 — tabela de features da conduta sugerida.

`montar_features(caso)` recebe o JSON de um caso e devolve um dicionário plano: uma
linha da tabela. É função pura (não lê arquivo, banco nem relógio) para ser a mesma
no treino e no serviço de checagem (STC-1077).

O caso só traz o que existe em produção antes da decisão do médico: exames pedidos
e realizados, valores e faixas lidos no laudo, tipo de exame, função, riscos e ficha.
A conduta (rótulo) nunca entra aqui: ela é montada à parte, em `extrair_caso.py`.

Formato do caso:

    {
      "id": "…",                       # só o ID, sem nome nem CPF
      "data": "2026-09-14",
      "tipo_exame": "periodico" | None,
      "funcao": "COZINHEIRO" | None,
      "riscos": ["RUÍDO", "CALOR", …] | None,   # None = seção de riscos não achada
      "exames_pedidos": ["HEMOGRAMA COMPLETO", …],    # pedido do BR NET
      "exames_realizados": ["HEMOGRAMA COMPLETO", …], # lidos no documento
      "resultados": [
        {"parametro": "glicemia", "valor": 132.0, "ref_min": 70.0, "ref_max": 99.0,
         "teto_exclusivo": false},
        {"parametro": "vdrl", "texto": "Não reagente"}
      ],
      "ficha": {}                      # STC-1068
    }
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

VERSAO = "2026-11-23.18"

# Valores do enum atividade_critica do contrato da API (NR_10, NR_30, ... em minúsculas).
ATIVIDADES = ("nr_10", "nr_30", "nr_33", "nr_35", "nr_37", "condutor_ab", "condutor_cde", "operador_equipamento_pesado")

# Campos da ficha (ficha.py). Números ficam vazios quando faltam; o resto é categoria.
FICHA_NUMEROS = ("pa_sistolica", "pa_diastolica", "freq_cardiaca", "peso", "altura", "imc", "circ_abdominal")
FICHA_CATEGORIAS = (
    # anamnese e hábitos
    "queixa_atual", "usa_medicamento", "doenca_cronica", "cirurgia_previa", "cirurgia_ha_menos_de_4_meses", "alergia",
    "internacao", "acidente_trabalho", "afastamento_inss", "uso_drogas", "tabagismo", "etilismo", "atividade_fisica",
    # condições (artefato da Karine + Ficha Médica da BR MED)
    "doenca_hipertensao", "doenca_diabetes", "doenca_diabetes_insulinodependente", "doenca_dislipidemia", "doenca_cardiopatia",
    "doenca_tireoide", "doenca_respiratoria", "doenca_epilepsia_convulsao", "doenca_labirintite_vertigem",
    "doenca_transtorno_psiquiatrico", "doenca_insuficiencia_renal_cronica", "doenca_cancer", "doenca_obesidade",
    "doenca_anemia", "doenca_hernia", "doenca_visao_monocular", "doenca_gestacao", "doenca_lactante",
    "doenca_fobia_altura_ou_confinamento", "doenca_neurologica",
    # exame físico
    "exame_romberg_positivo", "exame_sinais_uso_substancia",
    # histórico familiar
    "familiar_hipertensao", "familiar_diabetes", "familiar_cardiopatia", "familiar_cancer",
    # medicamento por classe
    "medicamento_anti_hipertensivo", "medicamento_antidiabetico_oral", "medicamento_insulina", "medicamento_hipolipemiante",
    "medicamento_antiagregante", "medicamento_anticoagulante", "medicamento_psicotropico",
    "medicamento_sedativo_benzodiazepinico", "medicamento_anticonvulsivante", "medicamento_opioide",
    "medicamento_imunossupressor_quimioterapico", "medicamento_levotiroxina",
)

NAO_INFORMADO = "nao_informado"

# Grupo de exame → como o nome aparece (pedido do BR NET ou lido no documento).
# Ordem importa só para leitura; um nome pode cair em mais de um grupo ("TGO/TGP").
EXAMES: dict[str, re.Pattern] = {k: re.compile(v) for k, v in {
    "clinico": r"\bCLINIC[OA]\b|\bEXAME MEDICO\b|\bANAMNESE\b|\bCLINICAL\b",
    "audiometria": r"AUDIOMETRI|AUDIOLOG|PURE TONE|AUDIOGRAM",
    "ecg": r"ELETROCARDIO|\bECG\b|ELECTROCARDIO",
    "eeg": r"ELETROENCEFALO|\bEEG\b|ELECTROENCEPHALO",
    "espirometria": r"ESPIROMETRI|SPIROMETR|PROVA DE FUNCAO PULMONAR",
    "acuidade_visual": r"ACUIDADE|VISUAL ACUITY|SNELLEN|OFTALMOLOGIC",
    "rx_torax": r"(?:\bRX\b|RAIO|RADIOGRAFIA|X-RAY|XRAY).*(?:TORAX|CHEST)|\bOIT\b",
    "rx_coluna": r"(?:\bRX\b|RAIO|RADIOGRAFIA|X-RAY).*(?:COLUNA|LOMB|SPINE)",
    "romberg": r"ROMBERG",
    "avaliacao_psicologica": r"PSICOLOGIC|PSYCHOLOG",
    "avaliacao_psicossocial": r"PSICOSSOCIAL|PSICOSOCIAL|PSYCHOSOCIAL",
    "avaliacao_odontologica": r"ODONTOLOG|DENTAL",
    "teste_ergometrico": r"ERGOMETRIC",
    "glicemia": r"^(?!.*(?:CURVA|TOLERANCIA|MEDIA|URINA)).*(?:GLICEMIA|GLICOSE|GLUCOSE)",
    "hba1c": r"GLICADA|HBA1C|\bA1C\b",
    "hemograma": r"HEMOGRAMA|BLOOD COUNT",
    "lipidograma": r"COLESTEROL|LIPID|TRIGLICER",
    "creatinina": r"^(?!.*(?:URINA|CLEARANCE)).*CREATININA",
    "ureia": r"^(?!.*URINA).*\bUREIA\b",
    "tgo": r"\bTGO\b|\bAST\b|ASPARTATO|OXALAC",
    "tgp": r"\bTGP\b|\bALT\b|ALANINA|PIRUV",
    "ggt": r"\bGGT\b|\bGAMA\b",
    "vdrl": r"\bVDRL\b",
    "toxicologico": r"TOXICOLOG",
    "parasitologico": r"PARASITOLOG|\bEPF\b",
    "urina_tipo1": r"\bEAS\b|URINA TIPO|SUMARIO DE URINA|URINALISE|URINA ROTINA",
}.items()}

# Parâmetro de laboratório (chaves de normalidade_exames) → grupo de exame.
# Parâmetro de laboratório (chaves de normalidade_exames, staging #111) → grupo de exame.
_HEMOGRAMA = ("hemoglobina", "leucocitos", "plaquetas", "eritrocitos", "hematocrito", "vcm", "hcm", "chcm", "rdw", "vpm",
              "bastonetes", "bastonetes_abs", "segmentados", "segmentados_abs", "neutrofilos", "neutrofilos_abs",
              "eosinofilos", "eosinofilos_abs", "basofilos", "basofilos_abs", "linfocitos", "linfocitos_abs",
              "monocitos", "monocitos_abs")
_TOX = ("tox_anfetaminas", "tox_metanfetamina", "tox_mdma", "tox_barbituricos", "tox_benzodiazepinicos", "tox_cocaina",
        "tox_maconha", "tox_fenciclidina", "tox_opiaceos", "tox_morfina", "tox_metadona", "tox_triciclicos")
PARAMETROS: dict[str, str] = {
    "glicemia": "glicemia", "hba1c": "hba1c",
    "colesterol": "lipidograma", "hdl": "lipidograma", "ldl": "lipidograma", "triglic": "lipidograma",
    "creatinina": "creatinina", "ureia": "ureia", "tgo": "tgo", "tgp": "tgp", "ggt": "ggt", "vdrl": "vdrl",
    **{p: "hemograma" for p in _HEMOGRAMA},
    **{p: "toxicologico" for p in _TOX},
}

# Faixa fisiologicamente possível de cada parâmetro (adulto em exame ocupacional), na unidade em que o leitor grava
# (leucócitos e plaquetas por mm³, diferencial em %, *_abs por mm³). Fora dela o valor FICA e o parâmetro entra em
# alertas_laboratorio — quase sempre erro de leitura (monócitos 0% ou 100%, basófilos 40%, plaquetas 5.140).
# Pedido do Breno (23/11): marcar, nunca corrigir em silêncio. Faixas tiradas da distribuição das duas bases.
PLAUSIVEL: dict[str, tuple[float, float]] = {
    "glicemia": (30, 600), "hba1c": (3.5, 18), "colesterol": (70, 600), "hdl": (10, 150), "ldl": (10, 500),
    "triglic": (20, 3000), "creatinina": (0.3, 10), "ureia": (5, 200), "tgo": (3, 2000), "tgp": (3, 2000),
    "ggt": (3, 2000), "hemoglobina": (6, 22), "eritrocitos": (2, 8), "hematocrito": (20, 65), "vcm": (55, 130),
    "hcm": (15, 45), "chcm": (25, 40), "rdw": (9, 30), "vpm": (5, 15), "leucocitos": (1000, 50000),
    "plaquetas": (20000, 1000000), "bastonetes": (0, 20), "segmentados": (10, 95), "neutrofilos": (10, 95),
    "eosinofilos": (0, 40), "basofilos": (0, 5), "linfocitos": (3, 80), "monocitos": (0.5, 30),
    "bastonetes_abs": (0, 2000), "segmentados_abs": (300, 20000), "neutrofilos_abs": (300, 20000),
    "eosinofilos_abs": (0, 3000), "basofilos_abs": (0, 500), "linfocitos_abs": (200, 8000), "monocitos_abs": (0, 3000),
}

TIPOS_EXAME = ("admissional", "periodico", "retorno_trabalho", "mudanca_risco", "demissional")

# Risco → como aparece na seção de riscos do ASO (texto normalizado).
RISCOS: dict[str, re.Pattern] = {k: re.compile(v) for k, v in {
    "ruido": r"RUIDO|NOISE",
    "calor": r"CALOR|\bHEAT\b",
    "frio": r"\bFRIO\b|\bCOLD\b",
    "vibracao": r"VIBRAC|VIBRATION",
    "radiacao": r"RADIAC|RADIATION",
    "altura": r"ALTURA|HEIGHT|NR\s?-?\s?35",
    "espaco_confinado": r"CONFINAD|CONFINED|NR\s?-?\s?33",
    "eletricidade": r"ELETRICIDADE|ELETRIC|ELECTRIC|NR\s?-?\s?10",
    "quimico": r"QUIMIC|CHEMICAL|BENZENO|TOLUENO|XILENO|SOLVENTE|HIDROCARBONET|POEIRA|FUMOS|VAPOR|GASES|CHUMBO",
    "biologico": r"BIOLOGIC|VIRUS|BACTERIA|FUNGO|MICRORGANISMO",
    "ergonomico": r"ERGONOMIC|POSTURA|POSTURE|LEVANTAMENTO|REPETITIV",
    "acidente": r"ACIDENTE|MECANIC|QUEDA|FALLS|CORTANTE",
}.items()}
_SEM_RISCO = re.compile(r"AUSENCIA DE (?:FATOR(?:ES)? DE )?RISCO|ABSENCE OF RISK|SEM RISCO|NAO HA RISCO|NO OCCUPATIONAL RISK|RISCOS? AUSENTES?")


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", texto).strip()


def _grupos(nomes: Optional[list[str]]) -> set[str]:
    achados: set[str] = set()
    for nome in nomes or []:
        n = _norm(nome)
        achados.update(k for k, rx in EXAMES.items() if rx.search(n))
    return achados


def _desvio(valor: float, minimo: Optional[float], maximo: Optional[float], teto_exclusivo: bool) -> tuple[str, Optional[float]]:
    """Situação e desvio relativo ao limite ultrapassado (0 dentro da faixa)."""
    if minimo is None and maximo is None:
        return "sem_referencia", None
    if maximo is not None and (valor > maximo or (teto_exclusivo and valor == maximo)):
        return "acima", round((valor - maximo) / maximo, 4) if maximo else None
    if minimo is not None and valor < minimo:
        return "abaixo", round((valor - minimo) / minimo, 4) if minimo else None
    return "normal", 0.0


def montar_features(caso: dict[str, Any]) -> dict[str, Any]:
    linha: dict[str, Any] = {}

    # Contexto do ASO
    tipo = caso.get("tipo_exame")
    linha["tipo_exame"] = tipo if tipo in TIPOS_EXAME else NAO_INFORMADO
    funcao = _norm(caso.get("funcao") or "")
    linha["funcao"] = funcao or NAO_INFORMADO

    riscos = caso.get("riscos")
    texto_riscos = _norm(" ".join(riscos)) if riscos else ""
    for k, rx in RISCOS.items():
        if riscos is None:
            linha[f"risco_{k}"] = NAO_INFORMADO
        else:
            linha[f"risco_{k}"] = "sim" if rx.search(texto_riscos) else "nao"
    linha["risco_ausencia_declarada"] = (
        NAO_INFORMADO if riscos is None else ("sim" if _SEM_RISCO.search(texto_riscos) else "nao")
    )

    # Atividade crítica da função (a regra de conduta muda com ela). Só a presença, nunca a aptidão.
    atividades = caso.get("atividades") or {}
    for k in ATIVIDADES:
        v = atividades.get(k)
        linha[f"atividade_{k}"] = v if v in ("sim", "nao") else NAO_INFORMADO

    # Exames: pedido (obrigatório para o caso) e realizado
    pedidos = _grupos(caso.get("exames_pedidos"))
    realizados = _grupos(caso.get("exames_realizados"))
    # Valor de laboratório lido = o exame foi feito, mesmo fora da lista.
    realizados |= {PARAMETROS[r.get("parametro")] for r in caso.get("resultados") or []
                   if isinstance(r, dict) and r.get("parametro") in PARAMETROS}
    for k in EXAMES:
        linha[f"{k}__obrigatorio"] = "sim" if k in pedidos else "nao"
        linha[f"{k}__realizado"] = "sim" if k in realizados else "nao"
    linha["n_exames_obrigatorios"] = len(pedidos)
    linha["n_obrigatorios_ausentes"] = len(pedidos - realizados)

    # Parâmetros de laboratório: situação e desvio pela faixa do laudo
    resultados = {r.get("parametro"): r for r in caso.get("resultados") or [] if isinstance(r, dict)}
    # Laboratório que só escreve "Segmentados" (e "Bastonetes"): neutrófilos = segmentados + bastonetes, como no
    # laudo dos outros laboratórios. A faixa só vem junto quando não há bastonete somando (24/11).
    for suf in ("", "_abs"):
        seg, bast = resultados.get(f"segmentados{suf}"), resultados.get(f"bastonetes{suf}")
        if f"neutrofilos{suf}" in resultados or not seg or seg.get("valor") is None:
            continue
        b = float(bast["valor"]) if bast and bast.get("valor") is not None else 0.0
        resultados[f"neutrofilos{suf}"] = {**seg, "parametro": f"neutrofilos{suf}", "valor": float(seg["valor"]) + b,
                                           **({} if b == 0 else {"ref_min": None, "ref_max": None})}
    n_alterados = 0
    alertas = []
    for p, exame in PARAMETROS.items():
        r = resultados.get(p)
        if r is None:
            status = "sem_resultado" if exame in realizados else "ausente"
            desvio = None
        elif r.get("valor") is None:
            texto = _norm(r.get("texto") or "")
            status = "normal" if texto.startswith(("NAO REAGENTE", "NEGATIVO")) else ("alterado" if texto else "sem_resultado")
            desvio = None
        else:
            status, desvio = _desvio(float(r["valor"]), r.get("ref_min"), r.get("ref_max"), bool(r.get("teto_exclusivo")))
        linha[f"{p}__status"] = status
        linha[f"{p}__desvio"] = desvio
        # Valor lido no laudo e a faixa impressa pelo laboratório (vazia quando o laudo não traz). Só parâmetro numérico.
        if p in PLAUSIVEL:
            valor = float(r["valor"]) if r is not None and r.get("valor") is not None else None
            linha[f"{p}__valor"] = valor
            linha[f"{p}__ref_min"] = r.get("ref_min") if valor is not None else None
            linha[f"{p}__ref_max"] = r.get("ref_max") if valor is not None else None
            minimo, maximo = PLAUSIVEL[p]
            if valor is not None and not minimo <= valor <= maximo:
                alertas.append(p)
        n_alterados += status in ("acima", "abaixo", "alterado")
    linha["n_parametros_alterados"] = n_alterados
    linha["alertas_laboratorio"] = "|".join(alertas)

    # Conclusão escrita no laudo dos exames sem valor (qual_*.py). Sem laudo: "ausente" se o exame não
    # foi feito, "sem_laudo" se foi feito mas o laudo não está no texto.
    conclusoes = caso.get("conclusoes") or {}
    for exame in ("acuidade_visual", "audiometria", "ecg", "espirometria"):
        v = conclusoes.get(exame)
        linha[f"{exame}__conclusao"] = v if v else ("sem_laudo" if exame in realizados else "ausente")
    # Laudo de RX (qual_rx.py, 23/11). laudo: descritivo | so_oit | sem_laudo (feito, laudo fora do texto) | ausente.
    # conclusao: normal | alterado (do laudo descritivo ou da OIT legível) | sem_conclusao (só OIT com a marca perdida).
    # oit: normal | alterado | ilegivel (formulário sem o X legível) | sem_oit.
    for exame in ("rx_torax", "rx_coluna"):
        laudo = conclusoes.get(f"{exame}_laudo")
        feito = exame in realizados
        linha[f"{exame}__laudo"] = laudo or ("sem_laudo" if feito else "ausente")
        if laudo:
            linha[f"{exame}__conclusao"] = conclusoes.get(exame) or "sem_conclusao"
        else:
            linha[f"{exame}__conclusao"] = "sem_laudo" if feito else "ausente"
        linha[f"{exame}__achados"] = conclusoes.get(f"{exame}_achados") or ""
    linha["rx_torax__oit"] = conclusoes.get("rx_torax_oit") or "sem_oit"
    # Detalhe do ECG (qual_ecg.detalhes, 23/11): ritmo, FC, intervalos em ms quando impressos como valor, achados.
    linha["ecg__ritmo"] = conclusoes.get("ecg_ritmo") or ("nao_informado" if conclusoes.get("ecg") else "")
    for k in ("fc", "pr_ms", "qrs_ms", "qtc_ms"):
        v = conclusoes.get(f"ecg_{k}")
        linha[f"ecg__{k}"] = float(v) if isinstance(v, (int, float)) else None
    linha["ecg__achados"] = conclusoes.get("ecg_achados") or ""
    # EEG (qual_eeg, 23/11): conclusão do neurologista e tipo da alteração.
    feito = "eeg" in realizados
    linha["eeg__conclusao"] = conclusoes.get("eeg") or ("sem_laudo" if feito else "ausente")
    linha["eeg__tipo"] = conclusoes.get("eeg_tipo") or ("nao_informado" if conclusoes.get("eeg") else "")
    # Teste ergométrico (qual_ergometrico, sessão do PC, 23/11).
    feito = "teste_ergometrico" in realizados
    laudo = conclusoes.get("ergometrico_laudo")
    linha["teste_ergometrico__laudo"] = laudo or ("sem_laudo" if feito else "ausente")
    linha["teste_ergometrico__conclusao"] = (conclusoes.get("ergometrico") or "sem_conclusao") if laudo else ("sem_laudo" if feito else "ausente")
    m = conclusoes.get("ergometrico_mets")
    linha["teste_ergometrico__mets"] = float(m) if isinstance(m, (int, float)) else None
    linha["teste_ergometrico__resposta_pressorica"] = conclusoes.get("ergometrico_resposta_pressorica") or ("nao_informado" if laudo else "")
    # Avaliação psicológica e psicossocial (qual_psico, sessão do PC, 23/11): SÓ o resultado, nenhum conteúdo clínico.
    for exame, chave in (("avaliacao_psicologica", "psicologica"), ("avaliacao_psicossocial", "psicossocial")):
        linha[f"{exame}__resultado"] = conclusoes.get(chave) or ("sem_resultado" if exame in realizados else "ausente")
    # Avaliação odontológica (qual_odonto, sessão do PC, 23/11).
    feito = "avaliacao_odontologica" in realizados
    linha["avaliacao_odontologica__resultado"] = conclusoes.get("odonto") or ("sem_resultado" if feito else "ausente")
    for k in ("tratamento", "urgencia"):
        linha[f"avaliacao_odontologica__{k}"] = conclusoes.get(f"odonto_{k}") or ("nao_informado" if conclusoes.get("odonto") else "")
    # Urina tipo 1 / EAS (qual_urina, sessão do PC, 23/11): tira e sedimento contra a referência do próprio laudo.
    feito = "urina_tipo1" in realizados
    for k in ("proteina", "glicose", "sangue", "leucocitos", "nitrito"):
        linha[f"urina__{k}"] = conclusoes.get(f"urina_{k}") or ("sem_resultado" if feito else "ausente")
    # Exame físico da ficha (qual_clinico, 23/11): achados por sistema; a conduta escrita no meio é cortada antes.
    linha["exame_fisico__resultado"] = conclusoes.get("exame_fisico") or "sem_exame_fisico"
    linha["exame_fisico__achados"] = conclusoes.get("exame_fisico_achados") or ""
    # Detalhe da espirometria (23/11): padrão, grau, resposta ao broncodilatador (índices CVF/VEF1 não: tabela embaralhada no OCR).
    for k in ("padrao", "grau", "broncodilatador"):
        linha[f"espirometria__{k}"] = conclusoes.get(f"espirometria_{k}") or ("nao_informado" if conclusoes.get("espirometria") else "")
    # Detalhe da audiometria (qual_audiometria, sessão do PC, 23/11): tipo, grau, lado, agravamento (NR-7 Anexo II).
    for k in ("tipo", "grau", "lado", "agravamento"):
        linha[f"audiometria__{k}"] = conclusoes.get(f"audiometria_{k}") or ("nao_informado" if conclusoes.get("audiometria") else "")
    pior = conclusoes.get("acuidade_pior_olho")
    linha["acuidade_pior_olho"] = int(pior) if isinstance(pior, (int, float)) else None
    linha["senso_cromatico__conclusao"] = conclusoes.get("senso_cromatico") or NAO_INFORMADO
    # Acuidade por olho (qual_acuidade, sessão do PC, 23/11): denominador do pior valor de LONGE (20/40 -> 40), correção.
    for k in ("od", "oe"):
        v = conclusoes.get(f"acuidade_{k}")
        linha[f"acuidade_visual__{k}"] = float(v) if isinstance(v, (int, float)) else None
    linha["acuidade_visual__correcao"] = conclusoes.get("acuidade_correcao") or ("nao_informado" if conclusoes.get("acuidade_visual") else "")
    v = conclusoes.get("senso_cromatico_erros")
    linha["senso_cromatico__erros"] = float(v) if isinstance(v, (int, float)) else None

    # Ficha: o que a ficha não traz fica vazio (número) ou nao_informado — nunca "nao".
    ficha = caso.get("ficha") or {}
    for k in FICHA_NUMEROS:
        v = ficha.get(k)
        linha[f"ficha_{k}"] = float(v) if isinstance(v, (int, float)) else None
    for k in FICHA_CATEGORIAS:
        linha[f"ficha_{k}"] = ficha.get(k) or NAO_INFORMADO
    n = ficha.get("n_outros_achados")
    linha["ficha_n_outros_achados"] = float(n) if isinstance(n, (int, float)) else None
    return linha
