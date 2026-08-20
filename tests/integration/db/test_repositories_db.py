import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database.models import Base, User, Campus
from repositories.sqlalchemy.user_repository import SqlAlchemyUserRepository
from repositories.sqlalchemy.campus_repository import SqlAlchemyCampusRepository

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
async def sqlite_session(sqlite_engine):
    async_session = async_sessionmaker(sqlite_engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

@pytest.mark.asyncio
async def test_campus_repository_creates_and_retrieves(sqlite_session):
    repo = SqlAlchemyCampusRepository(sqlite_session)
    sqlite_session.add(Campus(campus_id="C1", full_name="Campus One"))
    await sqlite_session.commit()
    
    campuses = await repo.get_all()
    assert len(campuses) == 1
    assert campuses[0].full_name == "Campus One"

@pytest.mark.asyncio
async def test_user_repository_creates_and_fetches_with_relations(sqlite_session):
    campus_repo = SqlAlchemyCampusRepository(sqlite_session)
    sqlite_session.add(Campus(campus_id="C1", full_name="Campus One"))
    await sqlite_session.commit()
    
    user_repo = SqlAlchemyUserRepository(sqlite_session)
    user = User(
        telegram_id=123,
        university_id="UGR/123/12",
        department_id=None,
        section="1",
        section_source=None,
        is_credential_valid=True
    )
    await user_repo.add(user)
    await sqlite_session.commit()
    
    fetched = await user_repo.get_by_telegram_id(123)
    assert fetched is not None
    assert fetched.university_id == "UGR/123/12"
    assert fetched.department_id is None
