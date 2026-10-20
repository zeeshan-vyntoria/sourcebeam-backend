from collections.abc import AsyncIterator
import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = (
    "7N3yqL9vB2mK8xR4pT6wC1zF5hJ0sD_aG-UeIoiQXcM"
)

from app.db.base import Base
from app.db.session import get_db
from app.core.rate_limit import limiter
from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    limiter.clear()
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.clear()
    await test_engine.dispose()


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient) -> AsyncClient:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "learner@example.com",
            "display_name": "Learner",
            "password": "strong-test-password",
        },
    )
    assert response.status_code == 201
    return client
