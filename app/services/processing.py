import asyncio
import random

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentStatus
from app.models.webhook_delivery import WebhookDelivery


async def process_payment(
    session: AsyncSession,
    payment_id: UUID,
) -> Payment | None:

    statement = (
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
    )

    result = await session.execute(statement)
    payment = result.scalar_one_or_none()

    if payment is None:
        return None

    if payment.status != PaymentStatus.PENDING:
        return payment

    delay = random.uniform(2, 5)
    await asyncio.sleep(delay)

    is_successful = random.random() < 0.9

    payment.status = (
        PaymentStatus.SUCCEEDED
        if is_successful
        else PaymentStatus.FAILED
    )

    payment.processed_at = datetime.now(timezone.utc)

    if payment.webhook_url:
        webhook_delivery = WebhookDelivery(
            payment_id=payment.id,
            webhook_url=payment.webhook_url,
        )
        session.add(webhook_delivery)

    await session.commit()
    await session.refresh(payment)

    return payment
