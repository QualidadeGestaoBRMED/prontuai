"""
Normalização canônica de nomes de exame para o catálogo.

Único lugar que decide como um nome de exame vira chave de comparação. As
tabelas `exam_parents` e `exam_variations` guardam o resultado de
`normalizar_termo` na coluna `name_normalized`, e é por essa coluna que a
unicidade (árvore estrita: uma variação, um pai) é garantida.

ATENÇÃO — duplicação conhecida: `_normalizar_busca` em
`app/services/workflow_service.py` e em `app/services/validacao_service.py`
faz exatamente este mesmo cálculo, em duas cópias. Enquanto o motor não
passar a ler do catálogo, as três implementações precisam permanecer
idênticas: mudar uma sem as outras faz o painel gravar uma chave que o motor
nunca encontra. Ao migrar o motor, apague as duas e importe daqui.
"""
import re
import unicodedata

# Espelha MAX_SIMILARITY_TERM_LENGTH do workflow_service.
MAX_TERM_LENGTH = 180

# Reescritas de sigla aplicadas depois de remover acento e pontuação. Mesma
# ordem do motor — GGT precisa colapsar antes da desduplicação final.
_REESCRITAS = (
    (r"\bGAMA\s*GLUTAMIL\s*TRANSPEPTIDASE\b", "GGT"),
    (r"\bGAMA\s*GLUTAMIL\s*TRANSFERASE\b", "GGT"),
    (r"\bGAMA\s*GLUTAMILTRANSFERASE\b", "GGT"),
    (r"\bGAMA\s*GT\b", "GGT"),
    (r"\bGGT\s+GGT\b", "GGT"),
)

_MARCADOR_EXTERNO = re.compile(r"\(\s*externo\s*\)|\bexterno\b", re.IGNORECASE)


def limpar_texto(texto: str) -> str:
    """Remove controles, colapsa espaço e corta no limite do catálogo."""
    if not texto:
        return ""
    limpo = re.sub(r"[\x00-\x1f\x7f]", " ", texto)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo[:MAX_TERM_LENGTH]


def normalizar_termo(texto: str) -> str:
    """Nome de exame → chave de comparação (maiúsculas, sem acento nem pontuação)."""
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", texto)
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
    normalizado = re.sub(r"\s+", " ", normalizado).strip().upper()
    normalizado = re.sub(r"[^A-Z0-9 ]+", " ", normalizado)
    normalizado = re.sub(r"\s+", " ", normalizado).strip()
    for padrao, substituto in _REESCRITAS:
        normalizado = re.sub(padrao, substituto, normalizado)
    return normalizado


def separar_marcador_externo(texto: str) -> tuple[str, bool]:
    """
    Separa o sufixo "(externo)" do nome do exame.

    O BRNET usa "externo" em 1 de 134 nomes, mas o CSV de origem gastava 61 de
    371 linhas criando pais espelhados só para marcar isso. Por decisão de
    modelagem, "externo" é flag do pai, não pai separado.

    Retorna (nome_sem_marcador, tinha_marcador).
    """
    if not texto:
        return "", False
    sem_marcador = _MARCADOR_EXTERNO.sub(" ", texto)
    sem_marcador = re.sub(r"\s+", " ", sem_marcador).strip(" -–—")
    tinha = normalizar_termo(sem_marcador) != normalizar_termo(texto)
    return (sem_marcador or texto), tinha
