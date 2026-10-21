from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.models.payment import Payment
from app.models.outbox import OutboxEvent
from app.schemas.payment import PaymentCreate

async def create_payment(
        session: AsyncSession,
        data: PaymentCreate,
        idempotency_key: str,
) -> Payment:
    payment = Payment(
        amount=data.amount,
        currency=data.currency.value,
        description=data.description,
        payment_metadata=data.metadata,
        webhook_url=str(data.webhook_url) if data.webhook_url is not None else None,
        idempotency_key=idempotency_key,
    )

    session.add(payment)

    await session.flush()

    event = OutboxEvent(
        event_type="payment_created",
        payload={
            "payment_id": str(payment.id),
        },
    )

    session.add(event)

    await session.commit()

    await session.refresh(payment)

    return payment

async def get_payment_by_idempotency_key(
        session: AsyncSession,
        idempotency_key: str,
) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )

    return result.scalar_one_or_none()

def payment_matches_request(
        payment: Payment,
        data: PaymentCreate,
) -> bool:
    return (
        payment.amount == data.amount and
        payment.currency == data.currency.value and
        payment.description == data.description and
        payment.payment_metadata == data.metadata and
        str(payment.webhook_url) == str(data.webhook_url)
    )

async def get_payment_by_id(
    session: AsyncSession,
    payment_id: UUID,
) -> Payment | None:
    return await session.get(Payment, payment_id)
