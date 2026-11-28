"""Conduta sugerida de um documento: features do texto do OCR → serviço de ML (ml-exams) → objeto Conduta da API.

- Features: os mesmos leitores da tabela de treino (pasta `leitores`, cópia de conduta_treino/features; versão em
  `leitores/montar_features.VERSAO`). Ficha pelas regras da produção (ficha_clinica.extrair_ficha, sem LLM) com as
  travas de coerência do treino (coerencia_ficha.py). Exames pedidos/realizados vêm do documento (exams_brnet/exams_ocr),
  como no casos_banco do treino.
- Modelo: serviço HTTP do ml-exams (ML_SERVICE_URL). Só as features saem daqui: nada de nome, CPF ou PDF.
- Zonas do modelo → situacao_aso: liberar → LIBERADO; encaminhar → LIBERADO_COM_ENCAMINHAMENTO; revisão → sem
  sugestão (CONFIANCA_BAIXA). O modelo atual não separa RETIDO de LIBERADO_COM_ENCAMINHAMENTO.
- Regras de uso da API (exame previsto ausente nunca libera; INAPTO nunca é sugerido) aplicadas no fim.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import time
import uuid
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional, Protocol

import httpx

_LEITORES = str(Path(__file__).with_name("leitores"))
if _LEITORES not in sys.path:
    sys.path.insert(0, _LEITORES)

import extrair_caso as _ec  # noqa: E402
import montar_features as _mf  # noqa: E402
import paciente as _paciente  # noqa: E402

from app.services import ficha_clinica as _fc  # noqa: E402

logger = logging.getLogger(__name__)

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "").rstrip("/")
ML_SERVICE_TOKEN = os.getenv("ML_SERVICE_TOKEN", "")
ML_TIMEOUT = float(os.getenv("ML_TIMEOUT", "20"))
# Hoje faltam só as 6 psico_* (lidas na imagem no treino); acima disso, quebra de paridade.
# Ficha clínica com o 4o mini nas lacunas das regras (STC-1068): o caminho de produção. "false" volta a só regras.
CONDUTA_FICHA_LLM = os.getenv("CONDUTA_FICHA_LLM", "true").strip().lower() not in ("false", "0", "nao", "não", "no")
ML_MAX_FEATURES_AUSENTES = int(os.getenv("ML_MAX_FEATURES_AUSENTES", "10"))
ML_CONFIANCA_CALIBRADA = os.getenv("ML_CONFIANCA_CALIBRADA", "false").lower() == "true"
VERSAO_FEATURES = _mf.VERSAO

# Nome legível dos fatores (coluna da tabela → texto para o médico).
_NOMES = {
    "n_parametros_alterados": "Exames de laboratório alterados", "tipo_exame": "Tipo de exame", "funcao": "Função",
    "paciente_idade": "Idade", "risco_ausencia_declarada": "Ausência de risco declarada no ASO",
    "acuidade_pior_olho_faixa": "Acuidade visual (pior olho)",
    "ficha_imc": "IMC", "ficha_peso": "Peso (kg)", "ficha_altura": "Altura (cm)", "ficha_circ_abdominal": "Circunferência abdominal (cm)",
    "ficha_pa_sistolica": "PA sistólica", "ficha_pa_diastolica": "PA diastólica", "ficha_freq_cardiaca": "Frequência cardíaca",
    "ficha_tabagismo": "Tabagismo", "ficha_internacao": "Internação prévia", "ficha_queixa_atual": "Queixa atual",
    "ficha_medicamento_psicotropico": "Uso de psicotrópico", "ficha_acidente_trabalho": "Acidente de trabalho",
}
_ATIVIDADES = {"nr_35": "Trabalho em altura (NR-35)", "nr_33": "Espaço confinado (NR-33)", "nr_37": "Plataforma de petróleo (NR-37)",
               "nr_10": "Eletricidade (NR-10)", "nr_30": "Trabalho aquaviário (NR-30)", "nr_20": "Inflamáveis (NR-20)"}
_EXAMES = {
    "pa": "Pressão arterial", "imc": "IMC", "glicemia": "Glicemia", "hba1c": "Hemoglobina glicada", "colesterol": "Colesterol total",
    "ldl": "LDL", "hdl": "HDL", "triglic": "Triglicerídeos", "hemoglobina": "Hemoglobina", "leucocitos": "Leucócitos",
    "linfocitos": "Linfócitos", "plaquetas": "Plaquetas", "creatinina": "Creatinina", "urina": "Urina",
    "acuidade_visual": "Acuidade visual", "audiometria": "Audiometria", "espirometria": "Espirometria",
    "teste_ergometrico": "Teste ergométrico", "ecg": "Eletrocardiograma", "rx_coluna": "RX de coluna", "rx_torax": "RX de tórax",
    "senso_cromatico": "Senso cromático", "avaliacao_odontologica": "Avaliação odontológica", "eeg": "Eletroencefalograma",
}
_ATRIBUTOS = {"faixa": "", "status": "", "conclusao": "", "resultado": "", "fc_faixa": "frequência cardíaca",
              "oe_faixa": "olho esquerdo", "od_faixa": "olho direito", "padrao": "padrão", "urgencia": "urgência"}
_VALORES = {"sim": "sim", "nao": "não", "nao_informado": "não informado", "sem_alteracao": "sem alteração",
            "alterado": "alterado", "acima": "acima da referência", "abaixo": "abaixo da referência", "ex": "ex-fumante", "mudanca_risco": "mudança de risco", "periodico": "periódico", "retorno_ao_trabalho": "retorno ao trabalho",
            "retorno_trabalho": "retorno ao trabalho", "osteofitos": "osteófitos",
            # Achados de RX e ECG (colunas *_achado_*): o serviço manda só "sim", o nome vem daqui.
            "repolarizacao": "alteração da repolarização", "bloqueio_ramo_direito": "bloqueio de ramo direito",
            "bloqueio_ramo_esquerdo": "bloqueio de ramo esquerdo", "arritmia_outra": "outra arritmia",
            "alteracao_ossea": "alteração óssea", "bronquite_bronquiectasia": "bronquite ou bronquiectasia",
            "alteracao_curvatura": "alteração de curvatura", "anomalia_transicao": "anomalia de transição",
            "degenerativa": "alteração degenerativa", "schmorl_esclerose": "nódulo de Schmorl ou esclerose",
            # Acuidade visual em Snellen (faixas.py): 20/30–20/40, 20/50–20/100, pior que 20/100.
            "leve_20_30_40": "leve (20/30 a 20/40)", "moderada_20_50_100": "moderada (20/50 a 20/100)",
            "grave_20_100+": "grave (pior que 20/100)"}


def _texto_valor(valor: Any, col: str) -> str:
    if valor in (None, "", "nan"):
        return "não informado"
    try:
        n = float(valor)
        return f"{n:.1f}".replace(".", ",") if col == "ficha_imc" else f"{n:.0f}"
    except (TypeError, ValueError):
        pass
    v = str(valor)
    if v in _VALORES:
        return _VALORES[v]
    # Faixas que o serviço calcula (ml-exams faixas.py): "estagio2_160_179_100_109" → "estágio 2 (160–179 / 100–109)".
    v = re.sub(r"^estagio(\d)", r"estagio \1", v)
    m = re.match(r"^(.*?)_((?:\d[\d.]*k?_?)+[+-]?)$", v)
    nome, faixa = (m.group(1), m.group(2)) if m and m.group(1) else (v, "")
    nome = re.sub(r"([a-z])(\d)$", r"\1 \2", nome).replace("_", " ")
    for a, b in (("limitrofe", "limítrofe"), ("pre diabetes", "pré-diabetes"), ("estagio", "estágio"), ("muito alto", "muito alto")):
        nome = nome.replace(a, b)
    if not faixa:
        return nome
    faixa = faixa.replace("k", " mil")
    if faixa.endswith("+"):
        txt = "≥ " + faixa[:-1].replace("_", " / ≥ ")
    elif faixa.endswith("-"):
        txt = "< " + faixa[:-1]
    else:
        nums = faixa.split("_")
        pares = [f"{nums[i]}–{nums[i + 1]}" if i + 1 < len(nums) else nums[i] for i in range(0, len(nums), 2)]
        txt = " / ".join(pares)
    return f"{nome} ({txt})"


def _texto_fator(f: dict) -> str:
    col, valor = f["feature"], f.get("valor")
    pronto = f.get("valor_texto")
    if pronto not in (None, "") and "_achado_" not in col:
        # O serviço já traduz o valor (servico/textos.py do ml-exams): só falta o nome da feature.
        return f"{_nome_fator(col)}: {pronto}"
    if col in _NOMES:
        return f"{_NOMES[col]}: {_texto_valor(valor, col)}"
    if col.startswith("atividade_"):
        nome = _ATIVIDADES.get(col.removeprefix("atividade_"), col.removeprefix("atividade_").upper().replace("_", "-"))
        return f"{nome}: {_texto_valor(valor, col)}"
    if col.startswith("risco_"):
        return f"Risco {col.removeprefix('risco_').replace('_', ' ')}: {_texto_valor(valor, col)}"
    m = re.match(r"(.+?)_achado_(.+)", col)
    if m and m.group(1) in _EXAMES:
        achado = _VALORES.get(m.group(2), m.group(2).replace("_", " "))
        return f"{_EXAMES[m.group(1)]}: {achado}" if valor == "sim" else f"{_EXAMES[m.group(1)]}: sem {achado}"
    if "__" in col:
        exame, atributo = col.split("__", 1)
        nome = _EXAMES.get(exame, exame.replace("_", " ").capitalize())
        rot = _ATRIBUTOS.get(atributo, atributo.replace("_", " "))
        return f"{nome}{' (' + rot + ')' if rot else ''}: {_texto_valor(valor, col)}"
    return f"{col.replace('_', ' ').capitalize()}: {_texto_valor(valor, col)}"


def _nome_fator(col: str) -> str:
    if col in _NOMES:
        return _NOMES[col]
    if col.startswith("atividade_"):
        return _ATIVIDADES.get(col.removeprefix("atividade_"), col.removeprefix("atividade_").upper().replace("_", "-"))
    if col.startswith("risco_"):
        return f"Risco {col.removeprefix('risco_').replace('_', ' ')}"
    if "__" in col:
        exame, atributo = col.split("__", 1)
        nome = _EXAMES.get(exame, exame.replace("_", " ").capitalize())
        rot = _ATRIBUTOS.get(atributo, atributo.replace("_", " "))
        return f"{nome} ({rot})" if rot else nome
    return col.replace("_", " ").capitalize()


_LISTAS = {"rx_torax__achados": "rx_torax_achado_", "rx_coluna__achados": "rx_coluna_achado_",
           "ecg__achados": "ecg_achado_", "exame_fisico__achados": "exame_fisico_achado_"}


def _ficha_plana(entrada: str, valores_conhecidos: tuple[str, ...] = ()) -> dict[str, Any]:
    """Ficha da produção (regras + 4o mini nas lacunas, CONDUTA_FICHA_LLM) achatada nas chaves da tabela."""
    return dict(_ficha_plana_cache(entrada, tuple(v for v in valores_conhecidos if v), CONDUTA_FICHA_LLM))


@functools.lru_cache(maxsize=512)
def _ficha_plana_cache(entrada: str, valores_conhecidos: tuple[str, ...], usar_llm: bool) -> dict[str, Any]:
    # A abertura do documento remonta as features para achar a resposta guardada pelo hash: sem este cache, cada
    # abertura chamaria o 4o mini de novo (o cache em disco da ficha só existe com FICHA_CACHE_DIR).
    f = _fc.extrair_ficha(entrada, usar_llm=usar_llm, valores_conhecidos=valores_conhecidos)
    if f is None:
        return {"fonte": "sem_ficha"}
    f = f.model_dump()
    sv = f["sinais_vitais"]
    plano: dict[str, Any] = {
        "pa_sistolica": sv["pa_sistolica"], "pa_diastolica": sv["pa_diastolica"], "freq_cardiaca": sv["freq_cardiaca"],
        "peso": sv["peso_kg"], "altura": sv["altura_cm"], "imc": sv["imc"], "circ_abdominal": sv["circ_abdominal_cm"],
        "fonte": f["fonte"], "n_outros_achados": len(f["outros_achados_relevantes"]),
    }
    for k, c in f["anamnese"].items():
        plano[k] = c["valor"]
    for k, c in f["condicoes"].items():
        plano[k if k == "doenca_neurologica" else f"doenca_{k}"] = c["valor"]
    for k, c in f["exame_fisico"].items():
        plano[f"exame_{k}"] = c["valor"]
    for k, c in f["historico_familiar"].items():
        plano[f"familiar_{k}"] = c["valor"]
    for k, c in f["medicamentos"].items():
        plano[f"medicamento_{k}"] = c["valor"]
    return plano


def _travas_da_ficha(linha: dict[str, Any]) -> None:
    """As mesmas travas de coerencia_ficha.py aplicadas na tabela de treino (v23.15)."""
    fc = linha.get("ficha_freq_cardiaca")
    if fc is not None and fc > 130:
        linha["ficha_freq_cardiaca"] = None
    i = linha.get("ficha_imc")
    if i is not None and not 14 <= i <= 60:
        linha["ficha_imc"] = None
    p, a, i = linha.get("ficha_peso"), linha.get("ficha_altura"), linha.get("ficha_imc")
    if p and a and i and abs(p / (a / 100) ** 2 - i) > 1:
        linha["ficha_peso"] = linha["ficha_altura"] = linha["ficha_imc"] = None
    s, d = linha.get("ficha_pa_sistolica"), linha.get("ficha_pa_diastolica")
    if s and d and d >= s:
        linha["ficha_pa_sistolica"] = linha["ficha_pa_diastolica"] = None


def features_do_documento(markdown: str, data_documento: Optional[str], exames_ocr: Optional[list[str]] = None,
                          exames_brnet: Optional[list[str]] = None,
                          valores_conhecidos: tuple[str, ...] = ()) -> dict[str, Any]:
    """A linha da tabela de features para um documento, a partir do texto do OCR e dos exames do documento."""
    doc = {"document_id": "doc", "data": data_documento, "exams_ocr": list(exames_ocr or []),
           "exams_brnet": list(exames_brnet or [])}
    caso, _ = _ec.extrair_caso(doc, markdown)
    entrada, _ = _ec.separar_rotulo(markdown)
    caso["ficha"] = _ficha_plana(entrada, valores_conhecidos)
    linha = _mf.montar_features(caso)
    # De onde veio a ficha (regras, regras+llm, llm, sem_ficha): fica na resposta, não vai ao modelo (_NUNCA_SAI).
    linha["ficha_fonte"] = caso["ficha"].get("fonte")
    _travas_da_ficha(linha)
    # Listas viram uma coluna sim/não por valor, como no gerar_parquet; o serviço de ML completa as ausentes com "nao".
    for col, prefixo in _LISTAS.items():
        for v in str(linha.get(col) or "").split("|"):
            if v:
                linha[prefixo + v] = "sim"
    linha["paciente_idade"] = _paciente.idade(markdown, data_documento)[0]
    linha["versao_features"] = VERSAO_FEATURES
    return linha


_NUNCA_SAI = {"versao_features", "document_id", "data", "base_origem", "paciente_sexo", "paciente_sexo_fonte",
              "alertas_laboratorio", "ficha_fonte", "fonte"}


def _nunca_sai(coluna: str) -> bool:
    """Colunas que o contrato do ml-exams proíbe ou que o modelo não usa: nunca vão no POST /prever."""
    return coluna in _NUNCA_SAI or coluna.startswith("rotulo_") or coluna.endswith("_hash")


# O ngrok gratuito responde uma página de aviso a quem parece navegador; o header faz ele passar direto (contrato).
_HEADERS_TUNEL = {"ngrok-skip-browser-warning": "1"}


def _saude() -> str:
    """Estado do serviço para o log, chamado a cada falha (contrato: GET /saude)."""
    try:
        with httpx.Client(timeout=5) as cli:
            d = cli.get(f"{ML_SERVICE_URL}/saude", headers=_HEADERS_TUNEL).json()
        return f"ok={d.get('ok')} versao_modelo={d.get('versao_modelo')} versao_features={d.get('versao_features')}"
    except Exception as exc:  # noqa: BLE001
        return f"sem resposta ({type(exc).__name__})"


def _chamar_modelo(casos: list[dict], request_id: Optional[str] = None) -> dict:
    """POST /prever do contrato: {versao_features, casos: [{caso_id, features}]}."""
    if not ML_SERVICE_URL:
        raise RuntimeError("ML_SERVICE_URL não configurada")
    headers = dict(_HEADERS_TUNEL)
    if ML_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {ML_SERVICE_TOKEN}"
    if request_id:
        headers["X-Request-Id"] = request_id
    with httpx.Client(timeout=ML_TIMEOUT) as cli:
        r = cli.post(f"{ML_SERVICE_URL}/prever", json={"versao_features": VERSAO_FEATURES, "casos": casos}, headers=headers)
        r.raise_for_status()
        return r.json()


_MOTIVOS = {"imc": "IMC", "pressao_arterial": "pressão arterial", "ecg": "ECG", "hba1c": "hemoglobina glicada",
            "funcao_hepatica": "função hepática", "acuidade_visual": "acuidade visual", "rx": "RX",
            "rx_torax": "RX de tórax", "rx_coluna": "RX de coluna", "eeg": "EEG"}


def _texto_motivo(m: str) -> str:
    return _MOTIVOS.get(m, m.replace("_", " "))


def _explicacao(situacao: str, especialidades: dict[str, float], ausentes: list[str],
                motivos_por_especialidade: Optional[dict[str, list[str]]] = None) -> Optional[str]:
    if situacao == "RETIDO":
        return f"Exame previsto não encontrado no documento ({', '.join(ausentes)})."
    if situacao == "LIBERADO_COM_ENCAMINHAMENTO" and especialidades:
        esp = sorted(especialidades.items(), key=lambda x: -x[1])
        partes = []
        for k, _v in esp:
            nome = _ESPECIALIDADES.get(k, k.replace("_", " "))
            motivos = (motivos_por_especialidade or {}).get(k) or []
            partes.append(f"{nome} ({', '.join(_texto_motivo(m) for m in motivos)})" if motivos else nome)
        return "Encaminhar para " + "; ".join(partes) + "."
    return None


_ESPECIALIDADES = {"clinica_medica": "clínica médica", "otorrinolaringologia": "otorrinolaringologia",
                   "gastroenterologia": "gastroenterologia", "endocrinologia": "endocrinologia",
                   "cardiologia": "cardiologia", "oftalmologia": "oftalmologia", "odontologia": "odontologia",
                   "dermatologia": "dermatologia", "pneumologia": "pneumologia", "neurologia": "neurologia",
                   "ortopedia": "ortopedia", "urologia": "urologia", "hematologia": "hematologia",
                   "nutricao": "nutrição", "psiquiatria": "psiquiatria", "psicologia": "psicologia",
                   "fonoaudiologia": "fonoaudiologia", "ginecologia": "ginecologia", "hepatologia": "hepatologia"}


class Guardada(Protocol):
    """Trilha das chamadas ao ml-exams do documento (tabela conduta_sugestoes, só linhas novas)."""

    def ler(self, features_hash: str) -> Optional[dict]: ...
    def gravar(self, features_hash: str, features: dict, versao_modelo: Optional[str], resposta: Optional[dict],
               status_http: Optional[int], erro: Optional[str], duracao_ms: int, request_id: str) -> Optional[int]: ...


def hash_features(features: dict) -> str:
    """Mesmas features (e mesma versão delas) = mesmo hash = não chama o ml-exams de novo."""
    corpo = json.dumps({"versao_features": VERSAO_FEATURES, "features": features}, sort_keys=True, default=str)
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()


def sugerir(markdown: str, data_documento: Optional[str], exames_ausentes: list[str],
            exames_ocr: Optional[list[str]] = None, exames_brnet: Optional[list[str]] = None,
            guardada: Optional[Guardada] = None, valores_conhecidos: tuple[str, ...] = ()) -> dict[str, Any]:
    """{conduta_sugerida, motivo_sem_sugestao, versao_modelo, confianca_calibrada, prob_encaminhamento, especialidades}.

    Com `guardada`, cada chamada ao ml-exams vira uma linha da trilha (resposta inteira ou falha, com tempo, código e
    request id), e a resposta bem-sucedida é reaproveitada enquanto as features do documento não mudam: abrir o
    documento de novo não chama o POST /prever. Depois de uma falha, a próxima abertura tenta de novo.
    """
    base = {"conduta_sugerida": None, "motivo_sem_sugestao": None, "versao_modelo": None, "confianca_calibrada": False,
            "versao_features": VERSAO_FEATURES}
    if not (markdown or "").strip():
        return {**base, "motivo_sem_sugestao": "FALHA_NA_LEITURA"}
    try:
        linha = features_do_documento(markdown, data_documento, exames_ocr, exames_brnet, valores_conhecidos)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[CONDUTA] Falha ao montar as features: {type(exc).__name__}")
        return {**base, "motivo_sem_sugestao": "FALHA_NA_LEITURA"}
    features = {k: v for k, v in linha.items() if not _nunca_sai(k)}
    chave = hash_features(features)
    anterior = None
    if guardada is not None:
        try:
            anterior = guardada.ler(chave)
        except Exception as exc:  # noqa: BLE001 — sem a tabela, segue chamando o modelo
            logger.warning(f"[CONDUTA] Falha ao ler a resposta guardada: {type(exc).__name__}")
    if anterior:
        resp, guardada_em, sugestao_id = anterior["resposta"], anterior.get("criado_em"), anterior.get("id")
        caso_id = ((resp.get("resultados") or [{}])[0]).get("caso_id")
    else:
        # caso_id: o id da chamada no ml-exams (aparece na tela para achar o caso no log do serviço).
        request_id, caso_id, inicio = uuid.uuid4().hex, uuid.uuid4().hex, time.monotonic()
        try:
            resp = _chamar_modelo([{"caso_id": caso_id, "features": features}], request_id)
            status_http, erro = 200, None
        except Exception as exc:  # noqa: BLE001 — erro ou demora nunca bloqueiam: segue sem sugestão
            resp, erro = None, type(exc).__name__
            status_http = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if status_http == 409:
                logger.error(f"[CONDUTA] versao_features {VERSAO_FEATURES} diferente da do modelo: treino e produção se "
                             f"descolaram ({_saude()})")
            else:
                logger.warning(f"[CONDUTA] Serviço de ML sem resposta válida: {status_http or erro} ({_saude()})")
        duracao_ms = int((time.monotonic() - inicio) * 1000)
        guardada_em = sugestao_id = None
        if guardada is not None:
            # Falha também fica na trilha; só a resposta bem-sucedida é reaproveitada na próxima abertura.
            try:
                sugestao_id = guardada.gravar(chave, features, (resp or {}).get("versao_modelo"), resp, status_http,
                                              erro, duracao_ms, request_id)
            except Exception as exc:  # noqa: BLE001 — não guardar só faz a próxima abertura chamar de novo
                logger.warning(f"[CONDUTA] Falha ao guardar a chamada ao modelo: {type(exc).__name__}")
        if resp is None:
            return {**base, "motivo_sem_sugestao": "CONFIANCA_BAIXA", "erro_modelo": erro, "sugestao_id": sugestao_id,
                    "caso_id": caso_id, "request_id": request_id}
    out = _conduta_da_resposta(resp, exames_ausentes, base)
    out["sugestao_guardada_em"] = guardada_em.isoformat() if hasattr(guardada_em, "isoformat") else guardada_em
    out["sugestao_id"] = sugestao_id
    out["ficha_fonte"] = linha.get("ficha_fonte")
    out["caso_id"] = caso_id
    return out


def _conduta_da_resposta(resp: dict, exames_ausentes: list[str], base: dict) -> dict[str, Any]:
    """Resposta do POST /prever → objeto Conduta da API. Roda a cada abertura: exame ausente pode mudar na Checagem."""
    r = resp["resultados"][0]
    p = float(r["prob_encaminhamento"])
    # Contrato da API: confianca_calibrada fica false enquanto o modelo não for validado (ML_CONFIANCA_CALIBRADA=true depois).
    out = {**base, "versao_modelo": resp.get("versao_modelo"), "confianca_calibrada": ML_CONFIANCA_CALIBRADA,
           "prob_encaminhamento": p,
           "zona_modelo": r["zona"], "especialidades": r.get("especialidades") or {},
           "motivos": r.get("motivos") or {}, "features_ausentes": r.get("features_ausentes")}
    # Salto de features_ausentes = quebra de paridade entre o ProntuAI e o treino (contrato do ml-exams).
    if (r.get("features_ausentes") or 0) > ML_MAX_FEATURES_AUSENTES:
        logger.warning(f"[CONDUTA] {r['features_ausentes']} features ausentes no modelo {resp.get('versao_modelo')}")
    if r["zona"] == "revisao":
        return {**out, "motivo_sem_sugestao": "CONFIANCA_BAIXA"}
    situacao = "LIBERADO_COM_ENCAMINHAMENTO" if r["zona"] == "encaminhar" else "LIBERADO"
    alertas = [f"{e} previsto e não encontrado no documento" for e in exames_ausentes]
    # Exame previsto ausente nunca libera.
    if exames_ausentes and situacao in ("LIBERADO", "LIBERADO_COM_ENCAMINHAMENTO"):
        situacao = "RETIDO"
    # Achado é motivo; contexto (tipo de exame, função, idade, NR, riscos) aparece à parte (contrato v13).
    fatores = r.get("fatores") or []
    achados = [_texto_fator(f) for f in fatores if f.get("tipo", "achado") == "achado"][:5]
    contexto = [_texto_fator(f) for f in fatores if f.get("tipo") == "contexto"][:5]
    # Confiança = acerto do modelo no teste congelado quando decidiu essa zona sozinho (confianca_zona);
    # sem ela (serviço antigo), a probabilidade do lado sugerido.
    confianca = r.get("confianca_zona")
    if confianca is None:
        confianca = p if p >= 0.5 else 1 - p
    out["conduta_sugerida"] = {
        "situacao_aso": situacao,
        "confianca": round(float(confianca), 3),
        "fatores": achados,
        "contexto": contexto,
        "explicacao": _explicacao(situacao, out["especialidades"], exames_ausentes, r.get("motivos_por_especialidade")),
        "alertas": alertas,
        "regras_cliente": [],
    }
    return out
