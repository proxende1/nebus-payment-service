from faststream.rabbit import RabbitQueue
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.outbox import OutboxEvent
from app.messaging.broker import broker

POLL_INTERVAL = 2
BATCH_SIZE = 10
PAYMENTS_QUEUE = RabbitQueue(
    name="payments.new",
    durable=True,
)


async def get_pending_events(session):
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(statement)

    return result.scalars().all()


async def publish_pending_events():
    async with async_session_factory() as session:
        async with session.begin():
            events = await get_pending_events(session)

            for event in events:
                await broker.publish(
                    message=event.payload,
                    queue=PAYMENTS_QUEUE,
                    persist=True,
                )

                event.published_at = datetime.now(timezone.utc)

            return len(events)


async def main():
    await broker.start()

    try:
        while True:
            count = await publish_pending_events()

            if count > 0:
                print(f"Published {count} outbox event(s)")

            await asyncio.sleep(POLL_INTERVAL)

    finally:
        await broker.stop()



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Outbox Publisher stopped.")
