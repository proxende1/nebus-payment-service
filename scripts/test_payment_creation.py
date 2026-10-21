import asyncio
import uuid

from sqlalchemy import select

from app.db.session import async_session_factory, engine
from app.models.payment import Payment
from app.models.outbox import OutboxEvent
from app.schemas.payment import PaymentCreate
from app.services.payment import create_payment

async def main():
    idempotency_key = f"test-{uuid.uuid4()}"

    data = PaymentCreate(
        amount=1500.50,
        currency="RUB",
        description="Test payment",
        metadata={"source": "integration_test"},
        webhook_url="https://example.com/webhook",
    )

    async with async_session_factory() as session:
        payment = await create_payment(
            session=session,
            data=data,
            idempotency_key=idempotency_key,
        )

        payment_id = payment.id
        print("Created payment:", payment_id)

    async with async_session_factory() as session:
        saved_payment = await session.get(Payment, payment_id)

        result = await session.execute(
            select(OutboxEvent).where(
                OutboxEvent.payload["payment_id"].astext == str(payment_id)
            )
        )

        saved_event = result.scalar_one_or_none()

        assert saved_payment is not None
        assert saved_event is not None

        print("Payment status:", saved_payment.status.value)
        print("Outbox event:", saved_event.event_type)
        print("Outbox payload:", saved_event.payload)
        print("Intgration test PASSED")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
