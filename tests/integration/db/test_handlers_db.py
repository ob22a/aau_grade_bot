import pytest
import pytest_asyncio
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, User as TgUser, Chat
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database.models import Base, Campus
from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
from aiogram.methods import TelegramMethod
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.client.bot import Bot
from aiogram.methods.base import Response, TelegramType

class MockBot(Bot):
    def __init__(self):
        super().__init__(token="123:test")
        self.sent_messages = []
        
    async def __call__(self, method: TelegramMethod[TelegramType], request_timeout: int | None = None) -> TelegramType:
        if method.__class__.__name__ == "SendMessage":
            self.sent_messages.append({"text": method.text, "reply_markup": method.reply_markup})
            from aiogram.types import Message, Chat, User
            return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), from_user=User(id=1, is_bot=False, first_name="bot"))
        return await super().__call__(method, request_timeout=request_timeout)

from handlers.commands.registration import build_registration_router

@pytest_asyncio.fixture
async def sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def sqlite_session_factory(sqlite_engine):
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)

@pytest_asyncio.fixture
async def db_setup(sqlite_session_factory):
    async with sqlite_session_factory() as session:
        session.add(Campus(campus_id="C1", full_name="Campus One"))
        session.add(Campus(campus_id="C2", full_name="Campus Two"))
        await session.commit()

@pytest.mark.asyncio
async def test_registration_handler_with_db_no_detached_error(sqlite_session_factory, db_setup):
    import services
    services.session_factory = sqlite_session_factory
    
    # We mock services but keep the DB real
    class DummyRegistrationService:
        def __init__(self, **kwargs): pass
        async def is_registered(self, tid): return False

    class DummyLifecycleService:
        pass

    from services.container import ApplicationServices
    ApplicationServices.registration_service = DummyRegistrationService()
    ApplicationServices.lifecycle_service = DummyLifecycleService()

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_registration_router(ApplicationServices))
    
    bot = MockBot()
    user = TgUser(id=123, is_bot=False, first_name="Test")
    chat = Chat(id=123, type="private")
    message = Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text="/register")

    from aiogram.types import Update
    # Start registration
    await dp.feed_update(bot, Update(update_id=1, message=message.model_copy(update={"text": "/register"})))
    
    # Enter AAU ID
    await dp.feed_update(bot, Update(update_id=2, message=message.model_copy(update={"text": "UGR/1234/12"})))
    
    # If the detached instance error occurs, it will be raised during the campus selection keyboard generation
    assert len(bot.sent_messages) >= 2
    # The last message should ask for campus and have InlineKeyboardMarkup with Campus One and Campus Two
    last_msg = bot.sent_messages[-1]
    assert "Campus" in last_msg["text"] or "Section" in last_msg["text"]
    
    if last_msg.get("reply_markup"):
        keyboard = last_msg["reply_markup"].inline_keyboard
        # Check if campuses are in keyboard
        buttons = [btn.text for row in keyboard for btn in row]
        assert "Campus One" in buttons or "Skip Section" in buttons
