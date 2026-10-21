import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_without_api_key():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_health_with_invalid_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret-key")

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"X-API-Key": "wrong-key"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_with_valid_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret-key")

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"X-API-Key": "test-secret-key"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from unittest.mock import AsyncMock

import app.main as main_module


@pytest.mark.asyncio
async def test_create_payment_returns_existing_payment(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret-key")

    existing_payment = SimpleNamespace(
        id=uuid4(),
        status=SimpleNamespace(value="pending"),
        created_at=datetime.now(timezone.utc),
        amount=Decimal("150.00"),
        currency="USD",
        description="Test payment",
        payment_metadata={},
        webhook_url=None,
    )

    find_payment = AsyncMock(return_value=existing_payment)
    create_new_payment = AsyncMock()

    monkeypatch.setattr(
        main_module,
        "get_payment_by_idempotency_key",
        find_payment,
    )
    monkeypatch.setattr(
        main_module,
        "create_payment",
        create_new_payment,
    )

    async def fake_get_db():
        yield object()

    app.dependency_overrides[main_module.get_db] = fake_get_db

    try:
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/payments",
                headers={
                    "X-API-Key": "test-secret-key",
                    "Idempotency-Key": "existing-key",
                },
                json={
                    "amount": "150.00",
                    "currency": "USD",
                    "description": "Test payment",
                    "metadata": {},
                },
            )

        assert response.status_code == 202
        assert response.json()["payment_id"] == str(existing_payment.id)
        create_new_payment.assert_not_awaited()
        find_payment.assert_awaited_once()

    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_create_payment_conflict(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret-key")

    existing_payment = SimpleNamespace(
        id=uuid4(),
        status=SimpleNamespace(value="pending"),
        created_at=datetime.now(timezone.utc),
        amount=Decimal("150.00"),
        currency="USD",
        description="Test payment",
        payment_metadata={},
        webhook_url=None,
    )

    find_payment = AsyncMock(return_value=existing_payment)
    create_new_payment = AsyncMock()

    monkeypatch.setattr(
        main_module,
        "get_payment_by_idempotency_key",
        find_payment,
    )
    monkeypatch.setattr(
        main_module,
        "create_payment",
        create_new_payment,
    )

    async def fake_get_db():
        yield object()

    app.dependency_overrides[main_module.get_db] = fake_get_db

    try:
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/payments",
                headers={
                    "X-API-Key": "test-secret-key",
                    "Idempotency-Key": "existing-key",
                },
                json={
                    "amount": "999.00",
                    "currency": "USD",
                    "description": "Test payment",
                    "metadata": {},
                },
            )

        assert response.status_code == 409
        assert "Idempotency key already used" in response.json()["detail"]

        create_new_payment.assert_not_awaited()

    finally:
        app.dependency_overrides.clear()

from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_concurrent_idempotency_conflict(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret-key")

    existing_payment = SimpleNamespace(
        id=uuid4(),
        status=SimpleNamespace(value="pending"),
        created_at=datetime.now(timezone.utc),
        amount=Decimal("150.00"),
        currency="USD",
        description="Test payment",
        payment_metadata={},
        webhook_url=None,
    )

    find_payment = AsyncMock(
        side_effect=[None, existing_payment]
    )

    create_new_payment = AsyncMock(
        side_effect=IntegrityError(
            statement="INSERT INTO payments",
            params={},
            orig=Exception("duplicate key"),
        )
    )

    fake_session = SimpleNamespace(
        rollback=AsyncMock()
    )

    monkeypatch.setattr(
        main_module,
        "get_payment_by_idempotency_key",
        find_payment,
    )
    monkeypatch.setattr(
        main_module,
        "create_payment",
        create_new_payment,
    )

    async def fake_get_db():
        yield fake_session

    app.dependency_overrides[main_module.get_db] = fake_get_db

    try:
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/payments",
                headers={
                    "X-API-Key": "test-secret-key",
                    "Idempotency-Key": "concurrent-key",
                },
                json={
                    "amount": "999.00",
                    "currency": "USD",
                    "description": "Test payment",
                    "metadata": {},
                },
            )

        assert response.status_code == 409
        assert "Idempotency key already used" in response.json()["detail"]

        assert find_payment.await_count == 2
        create_new_payment.assert_awaited_once()
        fake_session.rollback.assert_awaited_once()

    finally:
        app.dependency_overrides.clear()
