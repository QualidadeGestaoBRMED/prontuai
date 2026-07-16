import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Pattern


@dataclass(frozen=True)
class _NamePattern:
    regex: Pattern[str]
    weight: int
    display_priority: int


_MARKDOWN_PREFIX = r"[ \t]*(?:#{1,6}[ \t]*)?"
_NAME_PATTERNS = (
    # Cabeçalho de ficha clínica. É especialmente confiável porque delimita o
    # nome entre dois campos conhecidos, mesmo quando o OCR omite os dois-pontos.
    _NamePattern(
        re.compile(
            rf"(?im)^{_MARKDOWN_PREFIX}nome\s+"
            r"(?!(?:[/:\-]|do\s+paciente\b))(?P<value>.+?)\s+"
            r"(?:empresa|company)\s*:?[ \t]"
        ),
        6,
        3,
    ),
    _NamePattern(
        re.compile(
            rf"(?im)^{_MARKDOWN_PREFIX}nome\s+do\s+paciente\s*:\s*(?P<value>[^\n\r]+)"
        ),
        5,
        4,
    ),
    _NamePattern(
        re.compile(
            rf"(?im)^{_MARKDOWN_PREFIX}nome\s*/\s*name\s*:\s*(?P<value>[^\n\r]+)"
        ),
        4,
        5,
    ),
    _NamePattern(
        re.compile(
            rf"(?im)^{_MARKDOWN_PREFIX}paciente\s*:\s*(?P<value>[^\n\r]+)"
        ),
        4,
        4,
    ),
    _NamePattern(
        re.compile(rf"(?im)^{_MARKDOWN_PREFIX}nome\s*:\s*(?P<value>[^\n\r]+)"),
        2,
        2,
    ),
)

_TRAILING_FIELD = re.compile(
    r"(?i)\s+(?:"
    r"(?:empresa|company|matr[ií]cula|register|cpf|fun[cç][aã]o|function|"
    r"setor|section|idade|age|identidade|id\s+number|nacionalidade|"
    r"nationality|g[eê]nero|genre|n[º°o]\s*controle)\s*:?[ \t]*.*"
    r"|(?:nascimento(?:\s*/\s*birth)?|birth(?:\s*/\s*nascimento)?)"
    r"(?:\s*:[ \t]*|[ \t]+(?=\d)).*"
    r")$"
)
_INVALID_VALUES = {
    "NOME",
    "NAME",
    "PACIENTE",
    "NA",
    "N A",
    "NAO IDENTIFICADO",
    "NAO ENCONTRADO",
}


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized.upper())
    return re.sub(r"\s+", " ", normalized).strip()


def _name_key(value: str) -> str:
    # Espaços são particularmente instáveis no OCR (ex.: SILVA JUNIOR pode
    # aparecer como SILVAJUNIOR). Eles não devem separar evidências iguais.
    return _normalize_name(value).replace(" ", "")


def _clean_candidate(value: str) -> Optional[str]:
    candidate = re.sub(r"\s+", " ", value or "").strip()
    candidate = _TRAILING_FIELD.sub("", candidate)
    candidate = candidate.strip(" #-*_|/:;,.\t")

    normalized = _normalize_name(candidate)
    if not normalized or normalized in _INVALID_VALUES:
        return None

    words = normalized.split()
    if len(words) > 12:
        return None
    if len(candidate) < 4 or len(candidate) > 120:
        return None
    if any(character.isdigit() for character in candidate):
        return None
    return candidate


def extract_patient_name_from_markdown(markdown: str) -> Optional[str]:
    """Extrai o nome do paciente avaliando todas as evidências do OCR.

    O Textract pode ler uma ocorrência incorretamente e acertar o mesmo nome em
    outras páginas. Por isso, candidatos equivalentes são agrupados e recebem
    bônus por recorrência, em vez de a primeira linha compatível ser aceita sem
    validação.
    """
    if not markdown:
        return None

    candidates: dict[str, dict[str, object]] = {}
    seen_occurrences: set[tuple[int, int, str]] = set()

    for name_pattern in _NAME_PATTERNS:
        for match in name_pattern.regex.finditer(markdown):
            candidate = _clean_candidate(match.group("value"))
            if not candidate:
                continue

            key = _name_key(candidate)
            occurrence = (match.start(), match.end(), key)
            if occurrence in seen_occurrences:
                continue
            seen_occurrences.add(occurrence)

            evidence = candidates.setdefault(
                key,
                {
                    "display": candidate,
                    "display_priority": name_pattern.display_priority,
                    "display_position": match.start(),
                    "score": 0,
                    "count": 0,
                    "first_position": match.start(),
                },
            )
            evidence["score"] = int(evidence["score"]) + name_pattern.weight
            evidence["count"] = int(evidence["count"]) + 1
            evidence["first_position"] = min(
                int(evidence["first_position"]), match.start()
            )
            if (
                name_pattern.display_priority > int(evidence["display_priority"])
                or (
                    name_pattern.display_priority
                    == int(evidence["display_priority"])
                    and match.start() < int(evidence["display_position"])
                )
            ):
                evidence["display"] = candidate
                evidence["display_priority"] = name_pattern.display_priority
                evidence["display_position"] = match.start()

    if not candidates:
        return None

    def ranking(evidence: dict[str, object]) -> tuple[int, int, int]:
        count = int(evidence["count"])
        recurrence_bonus = max(0, count - 1) * 3
        return (
            int(evidence["score"]) + recurrence_bonus,
            count,
            -int(evidence["first_position"]),
        )

    best = max(candidates.values(), key=ranking)
    return str(best["display"])
