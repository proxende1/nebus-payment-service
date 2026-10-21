
import asyncio
import uuid

from faststream.rabbit import RabbitQueue

from app.messaging.broker import broker


PAYMENTS_QUEUE = RabbitQueue(
    name="payments.new",
    durable=True,
)


async def main():
    await broker.start()

    try:
        await broker.declare_queue(PAYMENTS_QUEUE)

        payment_id = str(uuid.uuid4())

        await broker.publish(
            message={"payment_id": payment_id},
            queue=PAYMENTS_QUEUE,
            persist=True,
        )

        print("Message published successfully!")
        print("Payment ID:", payment_id)

    finally:
        await broker.stop()


if __name__ == "__main__":
    asyncio.run(main())
