"""Application service container for handler composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApplicationServices:
    registration: Any
    grades: Any
    admin: Any
    scheduler: Any
    lifecycle: Any
    notification: Any
    scraper: Any
    session_factory: Any | None = None
