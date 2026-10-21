import asyncio
from uuid import UUID

from app.services.webhook import send_webhook


async def main():
    payment_id = UUID(
        "a90a2ce5-63e7-4106-afc4-9ef0c1b82ba6"
    )

    await send_webhook(
        webhook_url="http://127.0.0.1:8001/webhook",
        payment_id=payment_id,
        status="succeeded",
    )

    print("Webhook sent successfully!")


if __name__ == "__main__":
    asyncio.run(main())
