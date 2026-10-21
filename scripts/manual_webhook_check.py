import asyncio
from uuid import UUID
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.webhook_delivery import WebhookDelivery
from app.services.webhook_worker import process_webhook_delivery


PAYMENT_ID = UUID("f1fc91ab-782c-4e88-8ad0-f2f78ce3c896")


async def main():
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.payment_id == PAYMENT_ID)
                .with_for_update()
            )
            delivery = result.scalar_one_or_none()

            if delivery is None:
                print("Webhook delivery not found")
                return

            if delivery.status.value != "pending":
                print(f"Webhook is already {delivery.status.value}")
                return

            with patch(
                "app.services.webhook_worker.send_webhook",
                new_callable=AsyncMock,
            ) as mock_send:
                await process_webhook_delivery(session, delivery)

                print(f"Mocked HTTP calls: {mock_send.await_count}")

            print(f"Delivery status: {delivery.status.value}")
            print(f"Attempts: {delivery.attempts}")
            print(f"Delivered at: {delivery.delivered_at}")


if __name__ == "__main__":
    asyncio.run(main())
