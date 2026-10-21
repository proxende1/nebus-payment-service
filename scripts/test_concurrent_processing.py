
import asyncio
import time
from uuid import UUID

from app.db.session import async_session_factory
from app.services.processing import process_payment


PAYMENT_ID = UUID("a90a2ce5-63e7-4106-afc4-9ef0c1b82ba6")


async def worker(number: int):
    async with async_session_factory() as session:
        start = time.perf_counter()

        payment = await process_payment(
            session=session,
            payment_id=PAYMENT_ID,
        )

        elapsed = time.perf_counter() - start

        if payment is None:
            print(f"Worker {number}: payment not found")
        else:
            print(
                f"Worker {number}: {payment.status.value}, "
                f"time={elapsed:.2f}s"
            )


async def main():
    await asyncio.gather(
        worker(1),
        worker(2),
    )


if __name__ == "__main__":
    asyncio.run(main())
