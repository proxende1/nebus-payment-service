from uuid import UUID
import asyncio

from faststream.middlewares.acknowledgement.config import AckPolicy
from faststream import FastStream
from faststream.rabbit import RabbitQueue

from app.db.session import async_session_factory
from app.messaging.broker import broker
from app.services.processing import process_payment


from faststream.rabbit import RabbitExchange, RabbitQueue

PAYMENTS_DLX = RabbitExchange(
    name="payments.dlx",
    type="direct",
    durable=True,
)

PAYMENTS_QUEUE = RabbitQueue(
    name="payments.new",
    durable=True,
)

FAILED_PAYMENTS_QUEUE = RabbitQueue(
    name="payments.failed",
    durable=True,
    routing_key="payments.failed",
)

app = FastStream(broker)


@broker.subscriber(
    PAYMENTS_QUEUE,
    ack_policy=AckPolicy.REJECT_ON_ERROR,
)
async def handle_payment(message: dict):
    payment_id = UUID(message["payment_id"])

    for attempt in range(1, 4):
        try:
            print(f"Processing payment: {payment_id}, attempt {attempt}/3")

            async with async_session_factory() as session:
                payment = await process_payment(
                    session=session,
                    payment_id=payment_id,
                )

            if payment is None:
                raise ValueError(f"Payment not found: {payment_id}")

            print(
                f"Payment {payment_id} finished "
                f"with status: {payment.status.value}"
            )
            return

        except Exception as exc:
            print(f"Attempt {attempt}/3 failed: {exc}")

            if attempt == 3:
                raise

            delay = 2 ** attempt
            await asyncio.sleep(delay)
