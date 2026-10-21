import asyncio
import uuid
from decimal import Decimal

from app.db.session import async_session_factory
from app.models.payment import Payment
from app.services.processing import process_payment
from app.services.webhook import send_webhook


async def main():
    async with async_session_factory() as session:
        payment = Payment(
            amount=Decimal("1500.00"),
            currency="RUB",
            description="Processing and webhook integration test",
            payment_metadata={"test": "webhook"},
            webhook_url="http://127.0.0.1:8001/webhook",
            idempotency_key=f"webhook-test-{uuid.uuid4()}",
        )

        session.add(payment)
        await session.commit()

        payment_id = payment.id
        print(f"Created payment: {payment_id}")

    async with async_session_factory() as session:
        processed = await process_payment(session, payment_id)

        if processed is None:
            raise RuntimeError("Payment not found")

        print(f"Payment status: {processed.status.value}")

        await send_webhook(
            webhook_url=processed.webhook_url,
            payment_id=processed.id,
            status=processed.status.value,
        )

        print("Webhook delivered successfully!")


if __name__ == "__main__":
    asyncio.run(main())
