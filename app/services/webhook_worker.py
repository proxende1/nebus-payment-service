import httpx
from datetime import timedelta
import asyncio
from uuid import uuid4, UUID
from datetime import datetime, timezone

from sqlalchemy import select, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.db.session import async_session_factory
from app.models.webhook_delivery import (
    WebhookDelivery,
    WebhookStatus,
)
from app.services.webhook import send_webhook


POLL_INTERVAL = 2
MAX_ATTEMPTS = 3
LEASE_SECONDS = 60

async def claim_webhook_delivery() -> tuple[str, str] | None:
    """Reserve one webhook delivery without holding a long transaction."""
    async with async_session_factory() as session:
        async with session.begin():
            now = datetime.now(timezone.utc)

            statement = (
                select(WebhookDelivery)
                .where(WebhookDelivery.attempts < MAX_ATTEMPTS,
                    or_(
                        (
                            (WebhookDelivery.status == WebhookStatus.PENDING)
                            & (
                                WebhookDelivery.next_attempt_at.is_(None)
                                | (WebhookDelivery.next_attempt_at <= now)
                            )
                        ),
                        (
                            (WebhookDelivery.status == WebhookStatus.PROCESSING)
                            & (WebhookDelivery.lease_expires_at <= now)
                        ),
                    )
                )
                .order_by(WebhookDelivery.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )

            result = await session.execute(statement)
            delivery = result.scalar_one_or_none()

            if delivery is None:
                return None

            token = str(uuid4())

            delivery.status = WebhookStatus.PROCESSING
            delivery.lease_token = token
            delivery.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            delivery.attempts += 1

            return str(delivery.id), token



async def send_claimed_webhook(
    delivery_id: str,
    token: str,
) -> Exception | None:
    """Send a claimed webhook without holding a database transaction."""

    async with async_session_factory() as session:
        delivery = await session.get(
            WebhookDelivery,
            UUID(delivery_id),
        )

        if (
            delivery is None
            or delivery.status != WebhookStatus.PROCESSING
            or delivery.lease_token != token
        ):
            return RuntimeError("Webhook lease is no longer valid")

        payment = await session.get(Payment, delivery.payment_id)

        if payment is None:
            return ValueError("Payment not found")

        webhook_url = delivery.webhook_url
        payment_id = delivery.payment_id
        payment_status = payment.status.value

    # The database session is closed before the HTTP request.
    try:
        await send_webhook(
            webhook_url=webhook_url,
            payment_id=payment_id,
            status=payment_status,
        )
        return None
    except (httpx.HTTPError, ValueError) as exc:
        return exc


async def finalize_claimed_webhook(
    delivery_id: str,
    token: str,
    error: Exception | None,
) -> bool:
    """Save webhook result only if this worker still owns the lease."""

    async with async_session_factory() as session:
        async with session.begin():
            delivery = await session.get(
                WebhookDelivery,
                UUID(delivery_id),
                with_for_update=True,
            )

            if (
                delivery is None
                or delivery.status != WebhookStatus.PROCESSING
                or delivery.lease_token != token
            ):
                return False

            now = datetime.now(timezone.utc)

            if error is None:
                delivery.status = WebhookStatus.DELIVERED
                delivery.delivered_at = now
                delivery.next_attempt_at = None
                delivery.last_error = None

            elif isinstance(error, ValueError):
                delivery.status = WebhookStatus.FAILED
                delivery.next_attempt_at = None
                delivery.last_error = str(error)

            else:
                delivery.last_error = str(error)

                if delivery.attempts >= MAX_ATTEMPTS:
                    delivery.status = WebhookStatus.FAILED
                    delivery.next_attempt_at = None
                else:
                    delivery.status = WebhookStatus.PENDING
                    delay = 2 ** delivery.attempts
                    delivery.next_attempt_at = now + timedelta(
                        seconds=delay
                    )

            delivery.lease_token = None
            delivery.lease_expires_at = None

            return True


async def get_pending_webhooks(
    session: AsyncSession,
) -> list[WebhookDelivery]:
    now = datetime.now(timezone.utc)

    statement = (
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status == WebhookStatus.PENDING,
            or_(
                WebhookDelivery.next_attempt_at.is_(None),
                WebhookDelivery.next_attempt_at <= now,
            ),
        )
        .order_by(WebhookDelivery.created_at)
        .limit(10)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(statement)
    return list(result.scalars().all())


async def process_webhook_delivery(
    session: AsyncSession,
    delivery: WebhookDelivery,
) -> None:
    payment = await session.get(Payment, delivery.payment_id)

    if payment is None:
        raise ValueError(
            f"Payment {delivery.payment_id} not found"
        )

    delivery.attempts += 1

    try:
        await send_webhook(
            webhook_url=delivery.webhook_url,
            payment_id=delivery.payment_id,
            status=payment.status.value,
        )

        delivery.status = WebhookStatus.DELIVERED
        delivery.delivered_at = datetime.now(timezone.utc)
        delivery.next_attempt_at = None
        delivery.last_error = None

        print(f"Webhook delivered: {delivery.id}")

    except ValueError as exc:
        delivery.status = WebhookStatus.FAILED
        delivery.next_attempt_at = None
        delivery.last_error = str(exc)

        print(
            f"Webhook rejected: {delivery.id}, "
            f"reason: {exc}"
        )

    except httpx.HTTPError as exc:
        delivery.last_error = str(exc)

        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = WebhookStatus.FAILED
            delivery.next_attempt_at = None
            print(f"Webhook permanently failed: {delivery.id}")
        else:
            delay = 2 ** delivery.attempts
            delivery.next_attempt_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=delay)
            )
            print(
                f"Webhook retry scheduled: {delivery.id}, "
                f"in {delay} seconds"
            )


async def fail_exhausted_webhook_leases() -> int:
    """Fail expired webhook leases that have exhausted all attempts."""

    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        async with session.begin():
            statement = (
                update(WebhookDelivery)
                .where(
                    WebhookDelivery.status == WebhookStatus.PROCESSING,
                    WebhookDelivery.attempts >= MAX_ATTEMPTS,
                    WebhookDelivery.lease_expires_at <= now,
                )
                .values(
                    status=WebhookStatus.FAILED,
                    lease_token=None,
                    lease_expires_at=None,
                    next_attempt_at=None,
                    last_error="Webhook lease expired after maximum attempts",
                )
                .returning(WebhookDelivery.id)
            )

            result = await session.execute(statement)
            return len(result.scalars().all())


async def process_pending_webhooks() -> int:
    """Process up to 10 webhook deliveries per polling cycle."""

    await fail_exhausted_webhook_leases()


    processed = 0

    for _ in range(10):
        claimed = await claim_webhook_delivery()

        if claimed is None:
            break

        delivery_id, token = claimed

        try:
            error = await send_claimed_webhook(
                delivery_id=delivery_id,
                token=token,
            )
        except Exception as exc:
            error = exc

        finalized = await finalize_claimed_webhook(
            delivery_id=delivery_id,
            token=token,
            error=error,
        )

        if finalized:
            processed += 1

    return processed



async def main() -> None:
    print("Webhook Worker started")

    while True:
        try:
            count = await process_pending_webhooks()

            if count > 0:
                print(f"Processed {count} webhook delivery task(s)")

        except Exception as exc:
            print(f"Webhook Worker error: {exc}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Webhook Worker stopped")
