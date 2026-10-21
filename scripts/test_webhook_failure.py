import asyncio
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.webhook_delivery import WebhookDelivery, WebhookStatus
from app.services.webhook_worker import process_webhook_delivery


async def main():
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.status == WebhookStatus.PENDING)
                .order_by(WebhookDelivery.created_at)
                .limit(1)
                .with_for_update()
            )

            delivery = result.scalar_one_or_none()

            if delivery is None:
                print("No pending webhook deliveries")
                return

            request = httpx.Request("POST", "https://example.com/webhook")
            response = httpx.Response(500, request=request)
            error = httpx.HTTPStatusError(
                "Server returned HTTP 500",
                request=request,
                response=response,
            )

            with patch(
                "app.services.webhook_worker.send_webhook",
                new_callable=AsyncMock,
            ) as mock_send:
                mock_send.side_effect = error

                await process_webhook_delivery(session, delivery)

                print(f"Mocked HTTP calls: {mock_send.await_count}")

            print(f"Payment ID: {delivery.payment_id}")
            print(f"Status: {delivery.status.value}")
            print(f"Attempts: {delivery.attempts}")
            print(f"Next attempt: {delivery.next_attempt_at}")
            print(f"Last error: {delivery.last_error}")


if __name__ == "__main__":
    asyncio.run(main())
