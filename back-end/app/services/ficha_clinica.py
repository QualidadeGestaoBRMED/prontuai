"""
Extração da ficha clínica (STC-1068): regras primeiro, 4o mini só para completar.

`ler_ficha_regras` (`app/services/ficha_clinica_regras.py`) lê a Ficha Médica da BR MED sem LLM.
O que ela decide fica: o modelo só preenche campo que ficou `nao_informado` e sinal vital que
ficou nulo. Ficha de outro modelo (clínica credenciada, prontuário próprio) chega das regras
quase toda `nao_informado`, e aí o LLM faz a maior parte.

Travas do caminho da OpenAI (ver CLAUDE.md, "Nenhum dado cadastral vai para a OpenAI"):
- o texto sai por `redigir_para_llm` e passa por `verificar_payload`; se a conferência acusar
  cadastro, não há chamada e fica só o resultado das regras;
- cliente síncrono aberto e fechado por chamada (`with OpenAI(...)`), nunca global — ver o
  histórico de vazamento em `app/core/clients.py`;
- Structured Outputs com schema estrito, gerado do Pydantic pelo próprio SDK;
- todo `trecho` devolvido pelo modelo precisa existir no texto redigido (regra da STC-1070).
  Trecho que não está no texto é campo inventado e volta a `nao_informado`.

STC-1070: só a região da ficha vai ao modelo (`regiao_da_ficha`), e a resposta fica num cache pelo
hash do texto enviado + modelo + versão do prompt (`FICHA_CACHE_DIR`; sem a variável, não há cache).
Mudou o prompt, suba `PROMPT_VERSAO`: o cache antigo deixa de valer sozinho.

Nada aqui levanta exceção para quem chama: falha de rede, recusa ou saída inválida viram
"resultado das regras" (ou `None` se as regras também não acharam nada — caso sem sugestão).
Log só com contagens e nome de exceção, nunca com texto da ficha.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.core.pii_redaction import (
    VazamentoDeDadoCadastral,
    contem_marcador,
    redigir_para_llm,
    verificar_payload,
)
from app.models.ficha_clinica import (
    Anamnese,
    Condicoes,
    ExameFisico,
    FichaClinica,
    HistoricoFamiliar,
    Medicamentos,
    SinaisVitais,
    ficha_vazia,
)

logger = logging.getLogger(__name__)

NAO_INFORMADO = "nao_informado"

# Blocos de campos com valor/trecho, na ordem do modelo comum.
_BLOCOS_DE_CAMPOS = ("anamnese", "condicoes", "exame_fisico", "historico_familiar", "medicamentos")


class RespostaFichaLLM(BaseModel):
    """O que o 4o mini devolve: a `FichaClinica` sem `fonte`.

    `fonte` é decidida aqui, não pelo modelo — pedir isso ao LLM só abriria espaço para ele
    se declarar "regras". Os sub-modelos são os mesmos do modelo comum.
    """
    model_config = ConfigDict(extra="forbid")

    sinais_vitais: SinaisVitais
    anamnese: Anamnese
    condicoes: Condicoes
    exame_fisico: ExameFisico
    historico_familiar: HistoricoFamiliar
    medicamentos: Medicamentos
    outros_achados_relevantes: list[str]


# Suba a cada mudança no prompt ou no schema: invalida o cache.
PROMPT_VERSAO = "2026-11-18.1"  # prompt igual; a fusão mudou (cache continua valendo)

_PROMPT_SISTEMA = """Você lê fichas clínicas de exame ocupacional e preenche o formulário pedido.

Regras:
- Extraia só o que está escrito no texto. Não deduza, não complete por conhecimento clínico.
- Quando o texto não diz nada sobre um campo, use "nao_informado" e trecho null. "nao" só quando o texto nega de forma explícita (ex.: "( X ) Não", "nega", "sem").
- "trecho" é cópia literal e curta do texto que justifica o valor, sem reescrever nem corrigir. O trecho tem que conter a resposta, não só a pergunta: "Cirurgia?" ou "Sim" sozinhos não justificam nada.
- Formulário de caixinhas (Não / Sim): só marque o valor se a marca (X) estiver visível junto da opção no texto. Se as opções aparecem sem marca, use "nao_informado".
- Ignore a conclusão do ASO (apto, inapto, aptidão para NR) e o resultado de outros exames: não são ficha clínica.
- Sinais vitais: só números escritos no texto; null quando ausentes. Altura em centímetros, peso em kg.
- Medicamentos: marque a classe pelo princípio ativo ou nome comercial. Exemplos:
  anti-hipertensivo: losartana, enalapril, captopril, anlodipino, atenolol, propranolol, hidroclorotiazida, Aradois, Renitec;
  antidiabético oral: metformina (Glifage), glibenclamida, gliclazida (Diamicron), Januvia, Jardiance, Forxiga;
  insulina: NPH, regular, glargina (Lantus), asparte (NovoRapid), lispro (Humalog);
  hipolipemiante: sinvastatina, atorvastatina (Lipitor), rosuvastatina (Crestor), ciprofibrato;
  antiagregante: AAS, clopidogrel (Plavix);
  anticoagulante: varfarina (Marevan), rivaroxabana (Xarelto), apixabana (Eliquis), dabigatrana (Pradaxa);
  psicotrópico: fluoxetina, sertralina, escitalopram (Lexapro), venlafaxina, bupropiona, amitriptilina, quetiapina (Seroquel), risperidona, lítio;
  sedativo/benzodiazepínico: clonazepam (Rivotril), alprazolam (Frontal), diazepam (Valium), bromazepam (Lexotan), zolpidem (Stilnox);
  anticonvulsivante: carbamazepina (Tegretol), valproato (Depakote), fenitoína (Hidantal), fenobarbital (Gardenal), lamotrigina, topiramato;
  opioide: tramadol (Tramal), codeína (Tylex), morfina, oxicodona;
  imunossupressor/quimioterápico: metotrexato, azatioprina, ciclosporina, tacrolimo, tamoxifeno;
  levotiroxina: Puran T4, Synthroid, Euthyrox.
- outros_achados_relevantes: só achados escritos na ficha que mudam a conduta ocupacional e não cabem nos campos (ex.: "visão monocular", "uso de insulina", "amputação de dedo"), em frases curtas. Lista vazia se não houver."""


# ---------------------------------------------------------------------------
# Conferência do trecho (STC-1070)
# ---------------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    """Sem acento, sem caixa e sem espaço: tolera quebra de linha e espaçamento do OCR."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", "", sem_acento.casefold())


# Trecho que não prova nada: a própria pergunta do formulário ("Cirurgia?"), a opção solta ("Sim",
# "Não", "X") ou rótulo sem valor. No questionário de caixinhas o OCR imprime as duas opções e perde a
# marca; o modelo chutava "sim" citando a pergunta, e a conferência deixava passar porque "Sim" existe
# no texto (teste real de 18/11, 2 de 10 fichas).
_TRECHO_VAZIO = re.compile(r"^[\W_]*(?:sim|nao|não|x|ok|n/?a|\(\s*x?\s*\))?[\W_]*$", re.IGNORECASE)


def trecho_existe(trecho: Optional[str], texto_normalizado: str) -> bool:
    """True se o trecho prova algo e aparece no texto já normalizado por `_normalizar`."""
    if not trecho:
        return False
    limpo = trecho.strip()
    if _TRECHO_VAZIO.match(limpo) or limpo.endswith("?") or limpo.endswith(":"):
        return False
    alvo = _normalizar(limpo)
    return len(alvo) >= 4 and alvo in texto_normalizado


# ---------------------------------------------------------------------------
# Chamada ao modelo
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Região da ficha e cache (STC-1070)
# ---------------------------------------------------------------------------

# Onde a ficha clínica está no prontuário: o modelo só precisa disso. O documento inteiro (laudos,
# ASO, guias) levava 16–50 s por ficha no teste real de 18/11.
_MARCAS_DA_FICHA = re.compile(
    r"ANAMNESE|FICHA M[EÉ]DICA|FICHA CL[IÍ]NICA|HIST[OÓ]RI[AC]O? (?:OCUPACIONAL|FAMILIAR|PATOL)|H[AÁ]BITOS DE VIDA"
    r"|SINAIS VITAIS|PRESS[AÃ]O (?:ARTERIAL|SIST[OÓ]LICA)|EXAME F[IÍ]SICO|OBSERVA[CÇ][OÕ]ES DA FICHA|QUESTION[AÁ]RIO"
    r"|ANTECEDENTES|MEDICA[CÇ][OÕ]ES|MEDICAMENTOS? EM USO|QUEIXA",
    re.IGNORECASE,
)
_ANTES, _DEPOIS = 5, 80


def regiao_da_ficha(texto: str) -> str:
    """As linhas em volta das marcas de ficha clínica, na ordem do documento. Sem marca nenhuma,
    o texto inteiro (prontuário em texto corrido sem título)."""
    linhas = texto.splitlines()
    manter = [False] * len(linhas)
    for i, linha in enumerate(linhas):
        if _MARCAS_DA_FICHA.search(linha):
            for j in range(max(0, i - _ANTES), min(len(linhas), i + _DEPOIS)):
                manter[j] = True
    if not any(manter):
        return texto
    return "\n".join(l for l, m in zip(linhas, manter) if m)


def _chave_cache(texto_enviado: str) -> str:
    base = f"{PROMPT_VERSAO}\n{settings.MODELO_GPT}\n{texto_enviado}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _ler_cache(chave: str) -> Optional[RespostaFichaLLM]:
    pasta = os.getenv("FICHA_CACHE_DIR")
    if not pasta:
        return None
    arquivo = Path(pasta) / f"{chave}.json"
    try:
        return RespostaFichaLLM.model_validate_json(arquivo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # cache corrompido ou de schema antigo: ignora e chama de novo
        logger.warning("ficha_clinica: cache ilegível (%s)", type(exc).__name__)
        return None


def _gravar_cache(chave: str, resposta: RespostaFichaLLM) -> None:
    """A resposta tem trechos da ficha (dado de saúde): a pasta tem de ser privada (0700)."""
    pasta = os.getenv("FICHA_CACHE_DIR")
    if not pasta:
        return
    try:
        Path(pasta).mkdir(mode=0o700, parents=True, exist_ok=True)
        arquivo = Path(pasta) / f"{chave}.json"
        arquivo.write_text(resposta.model_dump_json(), encoding="utf-8")
        os.chmod(arquivo, 0o600)
    except Exception as exc:
        logger.warning("ficha_clinica: não gravou cache (%s)", type(exc).__name__)


def _chamar_llm_com_cache(texto_redigido: str) -> Optional[RespostaFichaLLM]:
    chave = _chave_cache(texto_redigido)
    em_cache = _ler_cache(chave)
    if em_cache is not None:
        return em_cache
    resposta = _chamar_llm(texto_redigido)
    if resposta is not None:
        _gravar_cache(chave, resposta)
    return resposta


def _chamar_llm(texto_redigido: str) -> Optional[RespostaFichaLLM]:
    """Uma chamada ao 4o mini com Structured Outputs estrito. None em recusa ou saída vazia."""
    with OpenAI(api_key=settings.OPENAI_API_KEY) as cliente:
        resposta = cliente.chat.completions.parse(
            model=settings.MODELO_GPT,
            temperature=0,
            messages=[
                {"role": "system", "content": _PROMPT_SISTEMA},
                {"role": "user", "content": texto_redigido},
            ],
            response_format=RespostaFichaLLM,
        )
    mensagem = resposta.choices[0].message
    if getattr(mensagem, "refusal", None):
        logger.warning("ficha_clinica: modelo recusou a extração")
        return None
    parsed = mensagem.parsed
    if parsed is None:
        return None
    # Garante o tipo mesmo se o SDK devolver dict (mock, versão futura): saída inválida
    # levanta ValidationError aqui e cai no tratamento do chamador.
    return RespostaFichaLLM.model_validate(parsed)


# ---------------------------------------------------------------------------
# Fusão regras + LLM
# ---------------------------------------------------------------------------

def questionario_sem_marca(texto: str) -> bool:
    """O documento tem questionário de caixinhas "Não / Sim" com as opções impressas e sem a marca
    visível no OCR (5+ pares). Nesse caso nem regra nem modelo sabem o que foi marcado: os campos
    sim/não ficam como as regras deixaram (o modelo só completa sinais vitais e achados)."""
    linhas = [l.strip().strip("#").strip().lower() for l in texto.splitlines() if l.strip()]
    pares = sum(
        1 for a, b in zip(linhas, linhas[1:])
        if a in ("não", "nao") and b == "sim"
    )
    return pares >= 5


def _ficha_brmed(ficha: FichaClinica) -> bool:
    """As regras leram a anamnese da Ficha Médica da BR MED (algum campo da anamnese decidido)."""
    return any(getattr(ficha.anamnese, c).valor != NAO_INFORMADO for c in type(ficha.anamnese).model_fields)


def _tem_lacuna(ficha: FichaClinica) -> bool:
    if any(v is None for v in ficha.sinais_vitais.model_dump().values()):
        return True
    for nome_bloco in _BLOCOS_DE_CAMPOS:
        bloco = getattr(ficha, nome_bloco)
        if any(getattr(bloco, campo).valor == NAO_INFORMADO for campo in type(bloco).model_fields):
            return True
    return False


def _tem_conteudo(ficha: FichaClinica) -> bool:
    if ficha.outros_achados_relevantes:
        return True
    if any(v is not None for v in ficha.sinais_vitais.model_dump().values()):
        return True
    for nome_bloco in _BLOCOS_DE_CAMPOS:
        bloco = getattr(ficha, nome_bloco)
        if any(getattr(bloco, campo).valor != NAO_INFORMADO for campo in type(bloco).model_fields):
            return True
    return False


# Conclusão do ASO é o rótulo da conduta: nunca entra como achado da ficha.
_APTIDAO = re.compile(r"\b(?:in)?apt[oa]s?\b|aptid[aã]o|liberad[oa] para|restri[cç][aã]o para", re.IGNORECASE)


# O que é possível para cada sinal vital (as mesmas faixas da leitura por regras). Fora disso o
# número veio de outro campo ou foi inventado.
_FAIXA_PLAUSIVEL = {
    "pa_sistolica": (70, 260), "pa_diastolica": (35, 160), "freq_cardiaca": (30, 200),
    "peso_kg": (30, 250), "altura_cm": (120, 220), "imc": (12, 70), "circ_abdominal_cm": (45, 200),
}


def _completar(
    base: FichaClinica, resposta: RespostaFichaLLM, texto_redigido: str, *, campos_sim_nao: bool = True,
    aceitar_nao: bool = True,
) -> tuple[FichaClinica, int, int]:
    """Preenche as lacunas de `base` com a resposta do LLM.

    Devolve (ficha, campos aproveitados, trechos descartados por não existirem no texto).
    Campo que as regras decidiram não é tocado; sinal vital só entra onde as regras deram null.
    """
    dados = base.model_dump()
    llm = resposta.model_dump()
    texto_normalizado = _normalizar(texto_redigido)
    aproveitados = 0
    descartados = 0

    for nome, valor in llm["sinais_vitais"].items():
        if dados["sinais_vitais"][nome] is None and valor is not None:
            lo, hi = _FAIXA_PLAUSIVEL[nome]
            if not lo <= valor <= hi:
                descartados += 1  # número fora do possível: leitura errada, não sinal vital
                continue
            dados["sinais_vitais"][nome] = valor
            aproveitados += 1

    for nome_bloco in (_BLOCOS_DE_CAMPOS if campos_sim_nao else ()):
        for campo, atual in dados[nome_bloco].items():
            if atual["valor"] != NAO_INFORMADO:
                continue  # regra decidiu
            sugerido = llm[nome_bloco][campo]
            if sugerido["valor"] == NAO_INFORMADO:
                continue
            if sugerido["valor"] == "nao" and not aceitar_nao:
                continue  # ficha da BR MED: o "nao" do modelo vinha de negação genérica
            if not trecho_existe(sugerido["trecho"], texto_normalizado):
                descartados += 1
                continue
            dados[nome_bloco][campo] = {"valor": sugerido["valor"], "trecho": sugerido["trecho"]}
            aproveitados += 1

    vistos = {_normalizar(a) for a in dados["outros_achados_relevantes"]}
    for achado in llm["outros_achados_relevantes"]:
        achado = (achado or "").strip()
        chave = _normalizar(achado)
        if not achado or chave in vistos or contem_marcador(achado) or _APTIDAO.search(achado):
            continue
        vistos.add(chave)
        dados["outros_achados_relevantes"].append(achado)
        aproveitados += 1

    return FichaClinica.model_validate(dados), aproveitados, descartados


# ---------------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------------

def extrair_ficha(
    texto: str,
    *,
    usar_llm: bool = True,
    valores_conhecidos: Iterable[Optional[str]] = (),
) -> FichaClinica | None:
    """Lê a ficha clínica do texto: regras, e o 4o mini só para o que ficou `nao_informado`.

    `texto` precisa vir SEM a carta/página de encaminhamento e sem a conclusão do ASO (use o
    texto de entrada de `separar_rotulo`). Senão o modelo lê a conduta ("encaminho por HAS") e
    marca a condição a partir do rótulo — vazamento que faz o classificador parecer ótimo no
    teste e falhar em produção.

    `valores_conhecidos` recebe o que o pipeline local já extraiu do documento (nome, CPF,
    CNPJ) para reforçar a redação e a conferência antes do envio — mesmo contrato de
    `redigir_para_llm`/`verificar_payload`.

    Devolve `None` quando nem regras nem LLM acharam nada (caso sem sugestão). Nunca levanta.
    """
    if not texto or not texto.strip():
        return None

    valores_conhecidos = tuple(v for v in valores_conhecidos if v)

    regras: Optional[FichaClinica]
    try:
        from app.services.ficha_clinica_regras import ler_ficha_regras

        regras = ler_ficha_regras(texto)
    except Exception as exc:  # regra quebrada não pode derrubar a extração
        logger.warning("ficha_clinica: leitura por regras falhou (%s)", type(exc).__name__)
        regras = None

    regras_tem_conteudo = regras is not None and _tem_conteudo(regras)
    resultado_regras = regras.model_copy(update={"fonte": "regras"}) if regras_tem_conteudo else None

    base = regras if regras is not None else ficha_vazia()
    if not usar_llm or not _tem_lacuna(base):
        return resultado_regras

    try:
        texto_redigido = redigir_para_llm(
            regiao_da_ficha(texto), valores_conhecidos=valores_conhecidos, preservar_datas=True
        )
        verificar_payload(texto_redigido, valores_conhecidos=valores_conhecidos)
    except VazamentoDeDadoCadastral as exc:
        # A mensagem da exceção nomeia só o tipo de dado, nunca o valor.
        logger.warning("ficha_clinica: envio ao LLM bloqueado — %s", exc)
        return resultado_regras
    except Exception as exc:
        logger.warning("ficha_clinica: redação falhou (%s); sem LLM", type(exc).__name__)
        return resultado_regras

    try:
        resposta = _chamar_llm_com_cache(texto_redigido)
    except Exception as exc:
        # Só o nome da exceção: ValidationError carrega a saída do modelo, que tem trechos da ficha.
        logger.warning("ficha_clinica: chamada ao LLM falhou (%s)", type(exc).__name__)
        return resultado_regras
    if resposta is None:
        return resultado_regras

    try:
        completa, aproveitados, descartados = _completar(
            base, resposta, texto_redigido, campos_sim_nao=not questionario_sem_marca(texto),
            # Medição da STC-1070: na Ficha Médica da BR MED o "nao" do modelo acertou 28 de 74 (lia
            # "nega doenças crônicas" como "não" para gestação, fobia, substância...). Fora dela, 12 de 13.
            aceitar_nao=not _ficha_brmed(base),
        )
    except Exception as exc:
        logger.warning("ficha_clinica: fusão regras+LLM falhou (%s)", type(exc).__name__)
        return resultado_regras

    logger.info(
        "ficha_clinica: LLM completou %d campo(s), %d descartado(s) por trecho inexistente",
        aproveitados,
        descartados,
    )

    if aproveitados == 0:
        return resultado_regras
    fonte = "regras+llm" if regras_tem_conteudo else "llm"
    return completa.model_copy(update={"fonte": fonte})
