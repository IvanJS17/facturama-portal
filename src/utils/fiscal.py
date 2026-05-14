"""Fiscal normalization and validation helpers."""

from __future__ import annotations

import re


RFC_PATTERN = re.compile(r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$")


def normalize_rfc(value: str) -> str:
    """Normalize and validate Mexican RFC."""
    normalized = (value or "").strip().upper()
    if not RFC_PATTERN.fullmatch(normalized):
        raise ValueError("RFC is invalid")
    return normalized


def normalize_postal_code(value: str) -> str:
    """Normalize and validate Mexican postal code."""
    normalized = (value or "").strip()
    if not re.fullmatch(r"\d{5}", normalized):
        raise ValueError("postal code is invalid")
    return normalized


def normalize_legal_name(value: str) -> str:
    """Normalize legal names using uppercase and compact spacing."""
    normalized = " ".join((value or "").strip().split()).upper()
    if not normalized:
        raise ValueError("name is required")
    return normalized

