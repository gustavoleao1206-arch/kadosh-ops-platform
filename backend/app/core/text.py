"""Normalização de placa e telefone (uma regra só, usada por schemas, busca e seed)."""

import re

# Placa brasileira (antiga LLLNNNN ou Mercosul LLLNLNN) e Mercosul de países vizinhos: 7 caracteres.
PLACA_MAX = 7

_NAO_ASCII = re.compile(r"[^\x00-\x7F]")


def normalize_placa(value: str | None) -> str | None:
    """Maiúsculas, só letras e números. Não impõe o formato (antiga ou Mercosul), só o tamanho."""
    if value is None:
        return None
    if _NAO_ASCII.search(value):
        raise ValueError("Placa inválida: use apenas letras sem acento e números.")
    s = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not s:
        return None
    if len(s) > PLACA_MAX:
        raise ValueError(f"Placa inválida: no máximo {PLACA_MAX} letras/números.")
    return s


def placa_fragment(q: str) -> str | None:
    """Trecho para busca parcial de placa; None se não cabe numa placa. Nunca lança."""
    s = re.sub(r"[^A-Za-z0-9]", "", q or "").upper()
    return s if 1 <= len(s) <= PLACA_MAX else None


def normalize_telefone(value: str | None) -> str | None:
    """Só dígitos, com DDI.

    - Nacional (DDD + número, 10–11 dígitos) ganha o 55 na frente; "0" de DDD/operadora é removido.
    - Internacional: começa com "+" ou "00"; guardado sem o prefixo, com o DDI.
    - 0800/0300 etc. não são telefone de cliente.
    """
    if value is None:
        return None
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    internacional = raw.startswith("+") or digits.startswith("00")
    if digits.startswith("00"):
        digits = digits[2:]
    if internacional:
        if 8 <= len(digits) <= 15 and not digits.startswith("0"):
            return digits
        raise ValueError("Telefone internacional inválido: informe +DDI e número.")

    if digits.startswith(("0800", "0300", "0500", "0900", "4004")):
        raise ValueError("Número de serviço (0800/0300/4004) não pode ser telefone de cliente.")
    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]  # 0 do DDD
    if digits.startswith("0") and len(digits) in (13, 14):
        digits = digits[3:]  # 0 + código de operadora (0XX) + DDD + número
    if digits.startswith("0"):
        raise ValueError("Telefone inválido: remova o zero inicial.")
    if len(digits) in (10, 11):
        return "55" + digits
    if 12 <= len(digits) <= 15:
        return digits
    raise ValueError("Telefone inválido: informe DDD e número (ex.: 82 99999-9999).")


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")
