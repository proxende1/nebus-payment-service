
import asyncio

from app.messaging.broker import broker


async def main():
    await broker.start()

    try:
        print("RabbitMQ connection successful!")
    finally:
        await broker.stop()


if __name__ == "__main__":
    asyncio.run(main())
