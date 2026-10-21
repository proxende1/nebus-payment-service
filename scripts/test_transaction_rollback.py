import asyncio
import uuid

from sqlalchemy import select

from app.db.session import async_session_factory, engine
from app.models.payment import Payment

async def main():
    idempotency_key = f"rollback-test-{uuid.uuid4()}"

    async with async_session_factory() as session:
        try:
            payment = Payment(
                amount="100.00",
                currency="RUB",
                description="Rollback test",
                payment_metadata={},
                webhook_url="https://example.com/webhook",
                idempotency_key=idempotency_key,
            )

            session.add(payment)
            await session.flush()

            print("Payment inserted, but not committed")

            raise RuntimeError("Simulated outbox failure")

        except RuntimeError as error:
            print("Caught error:", error)
            await session.rollback()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )

        saved_payment = result.scalar_one_or_none()

        assert saved_payment is None

        print("Payment was rolled back successfully")
        print("Rollback test PASSED")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
