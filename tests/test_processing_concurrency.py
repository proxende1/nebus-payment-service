import asyncio
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.db.session import async_session_factory
from app.models.payment import Payment, PaymentStatus
from app.models.webhook_delivery import WebhookDelivery
from app.services.processing import process_payment


@pytest.mark.asyncio
async def test_concurrent_processing_creates_one_webhook():
    payment_id = uuid4()

    # Создаём отдельный тестовый платёж.
    async with async_session_factory() as session:
        session.add(
            Payment(
                id=payment_id,
                amount=Decimal("100.00"),
                currency="RUB",
                description="Concurrent processing test",
                payment_metadata={},
                status=PaymentStatus.PENDING,
                idempotency_key=f"concurrency-test-{payment_id}",
                webhook_url="https://example.com/webhook",
            )
        )
        await session.commit()

    async def worker():
        async with async_session_factory() as session:
            return await process_payment(session, payment_id)

    try:
        # Убираем искусственную задержку, но сохраняем
        # реальную работу с PostgreSQL и блокировками.
        with (
            patch(
                "app.services.processing.random.uniform",
                return_value=0,
            ),
            patch(
                "app.services.processing.random.random",
                return_value=0.1,
            ),
        ):
            results = await asyncio.gather(worker(), worker())

        assert all(result is not None for result in results)
        assert all(
            result.status == PaymentStatus.SUCCEEDED
            for result in results
        )

        async with async_session_factory() as session:
            payment = await session.get(Payment, payment_id)

            webhook_count = await session.scalar(
                select(func.count())
                .select_from(WebhookDelivery)
                .where(WebhookDelivery.payment_id == payment_id)
            )

            assert payment.status == PaymentStatus.SUCCEEDED
            assert payment.processed_at is not None
            assert webhook_count == 1

    finally:
        # Удаляем тестовые данные даже при неудачной проверке.
        async with async_session_factory() as session:
            async with session.begin():
                deliveries = (
                    await session.scalars(
                        select(WebhookDelivery).where(
                            WebhookDelivery.payment_id == payment_id
                        )
                    )
                ).all()

                for delivery in deliveries:
                    await session.delete(delivery)

                payment = await session.get(Payment, payment_id)

                if payment is not None:
                    await session.delete(payment)