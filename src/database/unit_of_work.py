from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession


SessionFactory = Callable[[], AsyncSession]


class SqlAlchemyUnitOfWork:
    """Own one session, rollback failures, and require explicit commits.

    A new instance must be created for each request or concurrent worker.
    Repositories receive ``session`` after entering the context but do not own its lifecycle.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        return self

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("Unit of Work must be entered before committing. Try using 'async with' to enter the context.")
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        if self.session is not None:
            await self.session.rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        try:
            if exc_type is not None or not self._committed:
                await self.session.rollback()
        finally:
            await self.session.close()
            self.session = None
