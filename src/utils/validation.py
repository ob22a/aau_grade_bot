"""Framework-free validation policies."""

from __future__ import annotations

import re


_AAU_UNDERGRADUATE_ID_PATTERN = re.compile(r"^UGR/\d{4}/\d{2}$")


def normalize_aau_undergraduate_id(value: str) -> str:
    """Return canonical AAU undergraduate ID or raise ``ValueError``.

    The validator deliberately checks shape only. Authentication remains the portal's responsibility, so a syntactically valid ID is never assumed to represent a real student.
    """
    normalized = value.strip().upper()
    if not _AAU_UNDERGRADUATE_ID_PATTERN.fullmatch(normalized):
        raise ValueError("AAU ID must use the format UGR/NNNN/YY")
    return normalized
