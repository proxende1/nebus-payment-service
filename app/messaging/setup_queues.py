import asyncio

from app.messaging.broker import broker
from app.messaging.consumer import FAILED_PAYMENTS_QUEUE


async def main():
    await broker.start()

    try:
        await broker.declare_queue(FAILED_PAYMENTS_QUEUE)
        print("Dead Letter Queue declared successfully")
    finally:
        await broker.stop()


if __name__ == "__main__":
    asyncio.run(main())
