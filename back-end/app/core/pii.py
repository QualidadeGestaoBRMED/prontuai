import re
from typing import Optional


def mask_cpf(value: Optional[str]) -> Optional[str]:
    """Mascara um CPF mantendo apenas os últimos 2 dígitos: ***.***.***-72"""
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        return "***"
    return f"***.***.***-{digits[-2:]}"


def mask_identifier(value: Optional[str]) -> Optional[str]:
    """Mascara um identificador genérico (CPF, passaporte, CNPJ), preservando só os últimos 2 caracteres."""
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11:
        return mask_cpf(value)
    if len(digits) >= 4:
        return f"{'*' * (len(value) - 2)}{value[-2:]}"
    return "***"


def mask_name(value: Optional[str]) -> Optional[str]:
    """Mascara um nome mantendo apenas a primeira letra de cada palavra."""
    if not value:
        return value
    parts = value.split()
    return " ".join(f"{p[0]}{'*' * (len(p) - 1)}" if p else p for p in parts)
