"""
Regras de identificação de exame — a parte do Catálogo de Exames que diz COMO o
laudo de cada exame é (STC-1052).

O catálogo já guardava o nome: exame pai (como o BRNET pede) e variações (como o
documento escreve). Faltava o resto, que vivia espalhado pelo código em listas
fixas: o título do laudo do clínico é "Ficha Médica", a audiometria prova-se por
limiares em Hz e dB, o toxicológico por quatro drogas com resultado, a glicemia
de jejum sai no laudo como "Glicose … mg/dL". Isto agora são linhas das tabelas
`exam_report_profiles` / `exam_report_rules` (migração 019), editáveis pelo
painel, e os módulos que usavam as listas leem daqui.

Ficam separadas das variações de propósito: variação muda o que conta como exame
ENCONTRADO na comparação; uma regra daqui só diz como reconhecer o laudo.

Cada regra tem um PAPEL, que diz quem a usa:

  titulo_laudo         `layout_ocr` — título de laudo para onde o clique no exame leva
  titulo_identidade    `identidade_laudo` — título extra que liga a outra pessoa ao exame
  marcador_ocr         comparação — nome lido pelo OCR que vale como o exame do BRNET
  marcador_texto       comparação — exame do BRNET dado como encontrado pela marca no texto
  marca_laudo          `laudo_evidencia` — tipo do exame e a marca que o laudo tem de ter
  sorologia_analito    `laudo_evidencia` — analito da sorologia julgado por proximidade
  prova_conteudo       `laudo_evidencia` — conteúdo que prova o exame dado como faltante
  regua_monitoramento  `monitoramento_checagem` — conteúdo do laudo na página do clique
  laboratorio          `evidencia_laboratorio` — quem é exame de laboratório
  termos_extras        `evidencia_laboratorio` — outros nomes do analito no laudo

`padrao_nome` é uma regex procurada no nome NORMALIZADO do exame (cada módulo usa
o normalizador que já usava). `condicao` é uma árvore pequena, em JSON:

  {"regex": "..."}                      a regex aparece no texto
  {"todos": [c, ...]}                   todas as condições valem
  {"algum": [c, ...]}                   alguma vale
  {"nao": c}                            a condição não vale
  {"contar": [c, ...], "minimo": k}     pelo menos k das condições valem
                                        (o total vai para {contagem} no motivo)
  {"distintos": "regex", "minimo": k}   a regex casa k textos diferentes

ORDEM: dentro de cada papel as regras são lidas por `ordem`. Para `marca_laudo`,
`regua_monitoramento` e `prova_conteudo` vale a PRIMEIRA que casa o nome — a
radiografia OIT tem de vir antes da radiografia comum.

FONTE: o banco. A carga inicial (`migrations/019_regras_identificacao_exames.json`)
reproduz exatamente as listas que estavam no código — o teste de regressão
compara com a saída antiga — e só é lida em dois casos: para semear a tabela
vazia na migração e, como último recurso, quando o banco não responde (com
log de erro). Banco que responde vence sempre, mesmo que um papel fique vazio:
desligar uma regra no painel é decisão de curadoria.

O cache é por processo e o painel o invalida a cada escrita (`invalidar()`),
como em `exam_catalog_source` (WORKERS=1).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional

logger = logging.getLogger(__name__)

TITULO_LAUDO = "titulo_laudo"
TITULO_IDENTIDADE = "titulo_identidade"
MARCADOR_OCR = "marcador_ocr"
MARCADOR_TEXTO = "marcador_texto"
MARCA_LAUDO = "marca_laudo"
SOROLOGIA_ANALITO = "sorologia_analito"
PROVA_CONTEUDO = "prova_conteudo"
REGUA_MONITORAMENTO = "regua_monitoramento"
LABORATORIO = "laboratorio"
TERMOS_EXTRAS = "termos_extras"

PAPEIS = (
    TITULO_LAUDO, TITULO_IDENTIDADE, MARCADOR_OCR, MARCADOR_TEXTO, MARCA_LAUDO,
    SOROLOGIA_ANALITO, PROVA_CONTEUDO, REGUA_MONITORAMENTO, LABORATORIO, TERMOS_EXTRAS,
)

ESTRATEGIAS_MARCA = ("marca", "nome_fora_das_listas", "laboratorio", "sorologia")

CAMINHO_SEMENTE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "migrations",
    "019_regras_identificacao_exames.json",
)

# Teto de tamanho de regex vinda do painel: as maiores da carga inicial têm ~250.
MAX_REGEX = 600
MAX_PROFUNDIDADE = 6


class RegraInvalida(ValueError):
    """Regra que não pode valer: o motivo vai no texto da exceção."""


# ---------------------------------------------------------------------------
# Condição
# ---------------------------------------------------------------------------

Avaliador = Callable[[str, dict], bool]


def _compilar_regex(padrao: Any, onde: str) -> re.Pattern:
    if not isinstance(padrao, str) or not padrao:
        raise RegraInvalida(f"{onde}: regex vazia")
    if len(padrao) > MAX_REGEX:
        raise RegraInvalida(f"{onde}: regex com {len(padrao)} caracteres (máximo {MAX_REGEX})")
    try:
        return re.compile(padrao)
    except re.error as e:
        raise RegraInvalida(f"{onde}: regex inválida ({e})") from e


def _minimo(no: Mapping, onde: str) -> int:
    k = no.get("minimo")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise RegraInvalida(f"{onde}: 'minimo' tem de ser inteiro ≥ 1")
    return k


def compilar_condicao(no: Any, onde: str = "condicao", _nivel: int = 0) -> Avaliador:
    """A condição em JSON vira uma função (texto, contexto) → bool.

    Levanta `RegraInvalida` com o caminho do nó defeituoso."""
    if _nivel > MAX_PROFUNDIDADE:
        raise RegraInvalida(f"{onde}: condição aninhada demais (máximo {MAX_PROFUNDIDADE} níveis)")
    if not isinstance(no, Mapping):
        raise RegraInvalida(f"{onde}: esperado objeto, veio {type(no).__name__}")
    chaves = set(no) - {"minimo"}
    if len(chaves) != 1:
        raise RegraInvalida(f"{onde}: o nó precisa de exatamente um operador, veio {sorted(no)}")
    operador = chaves.pop()
    if "minimo" in no and operador not in ("contar", "distintos"):
        raise RegraInvalida(f"{onde}: 'minimo' só vale com 'contar' ou 'distintos'")

    if operador == "regex":
        padrao = _compilar_regex(no["regex"], onde)
        return lambda texto, _ctx: padrao.search(texto) is not None

    if operador in ("todos", "algum", "contar"):
        filhos_json = no[operador]
        if not isinstance(filhos_json, list) or not filhos_json:
            raise RegraInvalida(f"{onde}.{operador}: lista vazia")
        filhos = [
            compilar_condicao(f, f"{onde}.{operador}[{i}]", _nivel + 1) for i, f in enumerate(filhos_json)
        ]
        if operador == "todos":
            return lambda texto, ctx: all(f(texto, ctx) for f in filhos)
        if operador == "algum":
            return lambda texto, ctx: any(f(texto, ctx) for f in filhos)
        k = _minimo(no, onde)
        if k > len(filhos):
            raise RegraInvalida(f"{onde}: 'minimo' {k} maior que as {len(filhos)} condições")

        def contar(texto: str, ctx: dict) -> bool:
            n = sum(1 for f in filhos if f(texto, ctx))
            ctx["contagem"] = n
            return n >= k

        return contar

    if operador == "nao":
        filho = compilar_condicao(no["nao"], f"{onde}.nao", _nivel + 1)
        return lambda texto, ctx: not filho(texto, ctx)

    if operador == "distintos":
        padrao = _compilar_regex(no["distintos"], f"{onde}.distintos")
        if padrao.groups:
            # findall com grupo devolve o grupo, não o trecho: a contagem mudaria.
            raise RegraInvalida(f"{onde}.distintos: use grupo sem captura (?:...)")
        k = _minimo(no, onde)
        return lambda texto, _ctx: len(set(padrao.findall(texto))) >= k

    raise RegraInvalida(f"{onde}: operador desconhecido '{operador}'")


# ---------------------------------------------------------------------------
# Regra
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Regra:
    chave: str
    perfil: str
    papel: str
    ordem: int
    nome: re.Pattern
    parametros: Mapping[str, Any] = field(default_factory=dict)
    motivo: Optional[str] = None
    # A condição em JSON (para o painel e para os exemplos) e compilada.
    condicao_json: Optional[Mapping] = None
    _avaliar: Optional[Avaliador] = None
    # A regex da condição quando ela é uma regex só (títulos, marcas, analitos).
    regex: Optional[re.Pattern] = None

    def casa_nome(self, nome_normalizado: str) -> bool:
        return self.nome.search(nome_normalizado or "") is not None

    def avaliar(self, texto: str) -> tuple[bool, dict]:
        """(vale, contexto). Sem condição, não vale."""
        ctx: dict = {}
        if self._avaliar is None:
            return False, ctx
        return bool(self._avaliar(texto or "", ctx)), ctx

    def vale(self, texto: str) -> bool:
        return self.avaliar(texto)[0]

    def motivo_formatado(self, ctx: Mapping) -> str:
        motivo = self.motivo or ""
        try:
            return motivo.format(**ctx)
        except (KeyError, IndexError, ValueError):
            return motivo


def _validar_por_papel(papel: str, condicao: Any, parametros: Mapping, motivo: Any, onde: str) -> None:
    def exige_regex_simples() -> None:
        if not (isinstance(condicao, Mapping) and set(condicao) == {"regex"}):
            raise RegraInvalida(f"{onde}: o papel {papel} pede condição {{'regex': ...}}")

    def exige_termos() -> None:
        termos = parametros.get("termos")
        if not isinstance(termos, list) or not termos or not all(isinstance(t, str) and t.strip() for t in termos):
            raise RegraInvalida(f"{onde}: o papel {papel} pede parametros.termos (lista de textos)")

    if papel in (TITULO_LAUDO, SOROLOGIA_ANALITO):
        exige_regex_simples()
    elif papel in (MARCADOR_OCR, MARCADOR_TEXTO, REGUA_MONITORAMENTO):
        if condicao is None:
            raise RegraInvalida(f"{onde}: o papel {papel} pede condição")
        if papel == REGUA_MONITORAMENTO and not str(parametros.get("grupo") or "").strip():
            raise RegraInvalida(f"{onde}: a régua pede parametros.grupo")
    elif papel == PROVA_CONTEUDO:
        if condicao is None:
            raise RegraInvalida(f"{onde}: a prova pelo conteúdo pede condição")
        if not isinstance(motivo, str) or not motivo.strip():
            raise RegraInvalida(f"{onde}: a prova pelo conteúdo pede o motivo mostrado ao revisor")
    elif papel == MARCA_LAUDO:
        if not str(parametros.get("tipo") or "").strip():
            raise RegraInvalida(f"{onde}: marca_laudo pede parametros.tipo")
        estrategia = parametros.get("estrategia", "marca")
        if estrategia not in ESTRATEGIAS_MARCA:
            raise RegraInvalida(f"{onde}: estratégia '{estrategia}' desconhecida ({', '.join(ESTRATEGIAS_MARCA)})")
        if condicao is not None:
            exige_regex_simples()
        if estrategia == "nome_fora_das_listas" and condicao is None:
            raise RegraInvalida(f"{onde}: a estratégia nome_fora_das_listas pede a regex do nome no laudo")
        if estrategia == "sorologia":
            _compilar_regex(parametros.get("marca_proximidade"), f"{onde}.parametros.marca_proximidade")
            janela = parametros.get("janela")
            if not isinstance(janela, int) or isinstance(janela, bool) or not 1 <= janela <= 5000:
                raise RegraInvalida(f"{onde}: parametros.janela tem de ser inteiro entre 1 e 5000")
    elif papel in (TITULO_IDENTIDADE, TERMOS_EXTRAS):
        if condicao is not None:
            raise RegraInvalida(f"{onde}: o papel {papel} não usa condição, só parametros.termos")
        exige_termos()
    elif papel == LABORATORIO:
        if condicao is not None:
            raise RegraInvalida(f"{onde}: o papel laboratorio só classifica pelo nome")


def compilar_regra(registro: Mapping[str, Any]) -> Regra:
    """Valida e compila uma linha (do banco ou da carga inicial).

    Levanta `RegraInvalida`. É a mesma validação que o painel aplica antes de
    gravar, então regra que entrou no banco por ele sempre compila."""
    chave = str(registro.get("chave") or "").strip()
    onde = f"regra '{chave or '?'}'"
    if not chave:
        raise RegraInvalida("regra sem chave")
    papel = registro.get("papel")
    if papel not in PAPEIS:
        raise RegraInvalida(f"{onde}: papel '{papel}' desconhecido")
    perfil = str(registro.get("perfil") or "").strip()
    if not perfil:
        raise RegraInvalida(f"{onde}: sem perfil")
    ordem = registro.get("ordem")
    if not isinstance(ordem, int) or isinstance(ordem, bool):
        raise RegraInvalida(f"{onde}: ordem tem de ser inteiro")
    nome = _compilar_regex(registro.get("padrao_nome"), f"{onde}.padrao_nome")
    if nome.search(""):
        # Regex que casa o vazio casa qualquer exame — quase sempre engano.
        raise RegraInvalida(f"{onde}: padrao_nome casa qualquer nome")
    parametros = registro.get("parametros")
    if parametros is None:
        parametros = {}
    if not isinstance(parametros, Mapping):
        raise RegraInvalida(f"{onde}: parametros tem de ser objeto")
    condicao = registro.get("condicao")
    motivo = registro.get("motivo")
    _validar_por_papel(papel, condicao, parametros, motivo, onde)
    avaliar = compilar_condicao(condicao, f"{onde}.condicao") if condicao is not None else None
    return Regra(
        chave=chave,
        perfil=perfil,
        papel=papel,
        ordem=ordem,
        nome=nome,
        parametros=dict(parametros),
        motivo=motivo,
        condicao_json=condicao,
        _avaliar=avaliar,
        regex=(
            re.compile(condicao["regex"])
            if isinstance(condicao, Mapping) and set(condicao) == {"regex"}
            else None
        ),
    )


def conferir_exemplos(registro: Mapping[str, Any], regra: Optional[Regra] = None) -> list[str]:
    """Os exemplos da regra que não batem com ela. Vazio = todos batem.

    `exemplos` = {"nome_sim", "nome_nao", "texto_sim", "texto_nao"}, listas de
    textos já normalizados como o módulo do papel normaliza."""
    regra = regra or compilar_regra(registro)
    exemplos = registro.get("exemplos") or {}
    if not isinstance(exemplos, Mapping):
        return [f"{regra.chave}: exemplos tem de ser objeto"]
    desconhecidas = set(exemplos) - {"nome_sim", "nome_nao", "texto_sim", "texto_nao"}
    if desconhecidas:
        return [f"{regra.chave}: chave de exemplo desconhecida {sorted(desconhecidas)}"]
    vale = (lambda t: marcador(regra, t)) if regra.papel in (MARCADOR_OCR, MARCADOR_TEXTO) else regra.vale
    erros = []
    for nome in exemplos.get("nome_sim", []):
        if not regra.casa_nome(nome):
            erros.append(f"{regra.chave}: o nome '{nome}' deveria casar")
    for nome in exemplos.get("nome_nao", []):
        if regra.casa_nome(nome):
            erros.append(f"{regra.chave}: o nome '{nome}' não deveria casar")
    for texto in exemplos.get("texto_sim", []):
        if not vale(texto):
            erros.append(f"{regra.chave}: o texto '{texto[:60]}' deveria valer")
    for texto in exemplos.get("texto_nao", []):
        if vale(texto):
            erros.append(f"{regra.chave}: o texto '{texto[:60]}' não deveria valer")
    return erros


# ---------------------------------------------------------------------------
# Conjunto de regras e cache
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Conjunto:
    por_papel: Mapping[str, tuple[Regra, ...]]
    origem: str  # "banco" | "semente" | "teste"
    invalidas: tuple[str, ...] = ()

    def do_papel(self, papel: str) -> tuple[Regra, ...]:
        return self.por_papel.get(papel, ())


def montar(registros: Iterable[Mapping[str, Any]], origem: str) -> Conjunto:
    """Compila as linhas ativas. Linha inválida fica de fora, com log — uma regra
    errada não pode derrubar as outras nem o processamento do documento."""
    por_papel: dict[str, list[Regra]] = {p: [] for p in PAPEIS}
    invalidas: list[str] = []
    chaves: set[str] = set()
    for registro in registros:
        if registro.get("ativo") is False:
            continue
        try:
            regra = compilar_regra(registro)
        except RegraInvalida as e:
            invalidas.append(str(e))
            logger.error("[REGRAS_EXAME] Regra ignorada (%s): %s", origem, e)
            continue
        if regra.chave in chaves:
            invalidas.append(f"chave repetida '{regra.chave}'")
            logger.error("[REGRAS_EXAME] Chave repetida ignorada (%s): %s", origem, regra.chave)
            continue
        chaves.add(regra.chave)
        por_papel[regra.papel].append(regra)
    return Conjunto(
        por_papel={p: tuple(sorted(rs, key=lambda r: (r.ordem, r.chave))) for p, rs in por_papel.items()},
        origem=origem,
        invalidas=tuple(invalidas),
    )


def ler_semente(caminho: str = CAMINHO_SEMENTE) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


SQL_REGRAS = (
    "SELECT r.key, p.key, r.role, r.position, r.name_pattern, r.condition, r.params, "
    "r.reason, r.examples, r.is_active AND p.is_active "
    "FROM exam_report_rules r JOIN exam_report_profiles p ON p.id = r.profile_id"
)


def _ler_banco() -> list[dict]:
    from sqlalchemy import text  # import tardio, como em exam_catalog_source

    from app.core.database import user_db

    with user_db.engine.connect() as conexao:
        return registros_do_banco(conexao.execute(text(SQL_REGRAS)).all())


def registros_do_banco(linhas: Iterable[tuple]) -> list[dict]:
    """As linhas de `SQL_REGRAS` no formato da carga inicial."""
    return [
        {
            "chave": chave, "perfil": perfil, "papel": papel, "ordem": ordem, "padrao_nome": nome,
            "condicao": condicao, "parametros": parametros or {}, "motivo": motivo,
            "exemplos": exemplos or {}, "ativo": bool(ativo),
        }
        for chave, perfil, papel, ordem, nome, condicao, parametros, motivo, exemplos, ativo in linhas
    ]


_lock = threading.Lock()
_conjunto: Optional[Conjunto] = None
_fixado_para_teste = False


def _carregar() -> Conjunto:
    try:
        registros = _ler_banco()
        if not registros:
            # Tabela criada e ainda não semeada (a semeadura roda no startup).
            raise LookupError("tabela de regras vazia")
        conjunto = montar(registros, "banco")
        logger.info(
            "[REGRAS_EXAME] %d regras carregadas do catálogo (%d inválidas)",
            sum(len(v) for v in conjunto.por_papel.values()),
            len(conjunto.invalidas),
        )
        return conjunto
    except Exception as e:  # noqa: BLE001 — qualquer falha cai na carga inicial
        logger.error(
            "[REGRAS_EXAME] Catálogo de regras indisponível, usando a carga inicial da migração 019: %s: %s",
            type(e).__name__,
            e,
        )
        return montar(ler_semente()["regras"], "semente")


def conjunto() -> Conjunto:
    global _conjunto
    if _conjunto is None:
        with _lock:
            if _conjunto is None:
                _conjunto = _carregar()
    return _conjunto


def regras(papel: str) -> tuple[Regra, ...]:
    """As regras ativas do papel, na ordem."""
    if papel not in PAPEIS:
        raise ValueError(f"papel desconhecido: {papel}")
    return conjunto().do_papel(papel)


def invalidar() -> None:
    """Descarta o cache. Chamado pelo painel depois de cada escrita."""
    global _conjunto
    if _fixado_para_teste:
        return
    with _lock:
        _conjunto = None
    logger.info("[REGRAS_EXAME] Cache de regras invalidado")


def fixar(registros: Optional[Iterable[Mapping[str, Any]]] = None) -> Conjunto:
    """Para testes: usa estas linhas (ou a carga inicial) sem tocar no banco."""
    global _conjunto, _fixado_para_teste
    with _lock:
        _conjunto = montar(registros if registros is not None else ler_semente()["regras"], "teste")
        _fixado_para_teste = True
    return _conjunto


def soltar() -> None:
    """Desfaz `fixar`."""
    global _conjunto, _fixado_para_teste
    with _lock:
        _conjunto = None
        _fixado_para_teste = False


# ---------------------------------------------------------------------------
# Atalhos usados pelos módulos
# ---------------------------------------------------------------------------

def marcador(regra: Regra, texto: str) -> bool:
    """Marcador (papéis marcador_*) avaliado sobre o texto com espaço nas pontas,
    para o padrão " OD " casar palavra inteira também no começo e no fim."""
    if not texto:
        return False
    return regra.vale(f" {texto} ")


def primeira_do_nome(papel: str, nome_normalizado: str) -> Optional[Regra]:
    """A primeira regra do papel cujo padrão casa o nome (a ordem decide)."""
    return next((r for r in regras(papel) if r.casa_nome(nome_normalizado)), None)


def do_nome(papel: str, nome_normalizado: str) -> list[Regra]:
    """Todas as regras do papel cujo padrão casa o nome, na ordem."""
    return [r for r in regras(papel) if r.casa_nome(nome_normalizado)]


# ---------------------------------------------------------------------------
# Semeadura (chamada por app.core.migrations depois da 019)
# ---------------------------------------------------------------------------

def semear_se_vazio(conexao, semente: Optional[dict] = None, autor: str = "migracao_019") -> int:
    """Grava a carga inicial quando a tabela de regras está vazia. Devolve
    quantas regras gravou (0 quando já havia regras).

    `conexao` é uma conexão psycopg2 (a das migrações). Regra desativada no
    painel continua na tabela, então ela só fica vazia na primeira vez."""
    import uuid

    cursor = conexao.cursor()
    cursor.execute("SELECT count(*) FROM exam_report_rules")
    if cursor.fetchone()[0]:
        cursor.close()
        return 0
    semente = semente or ler_semente()
    # Nada entra se alguma regra da carga inicial não compilar.
    for registro in semente["regras"]:
        compilar_regra(registro)
    ids: dict[str, str] = {}
    for p in semente["perfis"]:
        cursor.execute("SELECT id FROM exam_report_profiles WHERE key = %s", (p["chave"],))
        existente = cursor.fetchone()
        if existente:
            ids[p["chave"]] = existente[0]
            continue
        ids[p["chave"]] = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO exam_report_profiles (id, key, name, description, created_by, updated_by) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (ids[p["chave"]], p["chave"], p["nome"], p.get("descricao") or None, autor, autor),
        )
    for r in semente["regras"]:
        cursor.execute(
            "INSERT INTO exam_report_rules (id, key, profile_id, role, position, name_pattern, condition, "
            "params, reason, examples, notes, created_by, updated_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                str(uuid.uuid4()), r["chave"], ids[r["perfil"]], r["papel"], r["ordem"], r["padrao_nome"],
                json.dumps(r["condicao"]) if r.get("condicao") is not None else None,
                json.dumps(r.get("parametros") or {}),
                r.get("motivo"),
                json.dumps(r.get("exemplos") or {}),
                r.get("notas"),
                autor, autor,
            ),
        )
    conexao.commit()
    cursor.close()
    logger.info("[REGRAS_EXAME] Carga inicial gravada: %d regras", len(semente["regras"]))
    return len(semente["regras"])
