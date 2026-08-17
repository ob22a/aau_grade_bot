"""Portal scraping service wrapper."""

from __future__ import annotations

from typing import Any


class ScraperService:
    def __init__(self, portal_client: Any) -> None:
        self.portal_client = portal_client

    async def scrape(self, university_id: str, password: str, student_id: str):
        return await self.portal_client.scrape(university_id, password, student_id)
