import asyncio
import time
from uuid import UUID

import httpx

from app.services.webhook import send_webhook_with_retry


async def main():
    payment_id = UUID(
        "a90a2ce5-63e7-4106-afc4-9ef0c1b82ba6"
    )

    start = time.perf_counter()

    try:
        await send_webhook_with_retry(
            webhook_url="http://127.0.0.1:8001/webhook",
            payment_id=payment_id,
            status="succeeded",
            max_attempts=3,
        )

    except httpx.HTTPError:
        elapsed = time.perf_counter() - start

        print("All webhook attempts failed")
        print(f"Total time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
