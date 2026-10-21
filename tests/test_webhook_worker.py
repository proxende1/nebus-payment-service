from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.models.payment import PaymentStatus
from app.models.webhook_delivery import WebhookStatus
from app.services.webhook_worker import process_webhook_delivery


@pytest.mark.asyncio
async def test_webhook_retry_after_http_500():
    payment_id = uuid4()

    delivery = SimpleNamespace(
        id=uuid4(),
        payment_id=payment_id,
        webhook_url="https://example.com/webhook",
        status=WebhookStatus.PENDING,
        attempts=0,
        next_attempt_at=None,
        delivered_at=None,
        last_error=None,
    )

    payment = SimpleNamespace(status=PaymentStatus.SUCCEEDED)

    session = SimpleNamespace(
        get=AsyncMock(return_value=payment)
    )

    request = httpx.Request(
        "POST",
        "https://example.com/webhook",
    )
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

        before = datetime.now(timezone.utc)

        await process_webhook_delivery(session, delivery)

        after = datetime.now(timezone.utc)

        mock_send.assert_awaited_once()

    assert delivery.status == WebhookStatus.PENDING
    assert delivery.attempts == 1
    assert delivery.last_error == "Server returned HTTP 500"
    assert delivery.next_attempt_at is not None

    assert before.timestamp() + 2 <= delivery.next_attempt_at.timestamp()
    assert delivery.next_attempt_at.timestamp() <= after.timestamp() + 2


@pytest.mark.asyncio
async def test_webhook_success():
    payment_id = uuid4()

    delivery = SimpleNamespace(
        id=uuid4(),
        payment_id=payment_id,
        webhook_url="https://example.com/webhook",
        status=WebhookStatus.PENDING,
        attempts=1,
        next_attempt_at=datetime.now(timezone.utc),
        delivered_at=None,
        last_error="Previous HTTP 500 error",
    )

    payment = SimpleNamespace(status=PaymentStatus.SUCCEEDED)

    session = SimpleNamespace(
        get=AsyncMock(return_value=payment)
    )

    with patch(
        "app.services.webhook_worker.send_webhook",
        new_callable=AsyncMock,
    ) as mock_send:
        await process_webhook_delivery(session, delivery)

        mock_send.assert_awaited_once_with(
            webhook_url="https://example.com/webhook",
            payment_id=payment_id,
            status="succeeded",
        )

    assert delivery.status == WebhookStatus.DELIVERED
    assert delivery.attempts == 2
    assert delivery.delivered_at is not None
    assert delivery.next_attempt_at is None
    assert delivery.last_error is None


@pytest.mark.asyncio
async def test_webhook_fails_after_five_attempts():
    payment_id = uuid4()

    delivery = SimpleNamespace(
        id=uuid4(),
        payment_id=payment_id,
        webhook_url="https://example.com/webhook",
        status=WebhookStatus.PENDING,
        attempts=4,
        next_attempt_at=datetime.now(timezone.utc),
        delivered_at=None,
        last_error=None,
    )

    payment = SimpleNamespace(status=PaymentStatus.SUCCEEDED)
    session = SimpleNamespace(
        get=AsyncMock(return_value=payment)
    )

    request = httpx.Request(
        "POST",
        "https://example.com/webhook",
    )
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

        mock_send.assert_awaited_once()

    assert delivery.status == WebhookStatus.FAILED
    assert delivery.attempts == 5
    assert delivery.next_attempt_at is None
    assert delivery.delivered_at is None
    assert delivery.last_error == "Server returned HTTP 500"

@pytest.mark.asyncio
async def test_webhook_permanently_fails_after_third_attempt():
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    import httpx

    from app.models.payment import PaymentStatus
    from app.models.webhook_delivery import WebhookStatus
    from app.services.webhook_worker import (
        MAX_ATTEMPTS,
        process_webhook_delivery,
    )

    session = AsyncMock()

    payment = MagicMock()
    payment.status = PaymentStatus.SUCCEEDED
    session.get.return_value = payment

    delivery = MagicMock()
    delivery.id = uuid4()
    delivery.payment_id = uuid4()
    delivery.webhook_url = "https://example.com/webhook"
    delivery.attempts = 2
    delivery.status = WebhookStatus.PENDING

    with patch(
        "app.services.webhook_worker.send_webhook",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection failed"),
    ):
        await process_webhook_delivery(session, delivery)

    assert MAX_ATTEMPTS == 3
    assert delivery.attempts == 3
    assert delivery.status == WebhookStatus.FAILED
    assert delivery.next_attempt_at is None
    assert "Connection failed" in delivery.last_error

@pytest.mark.asyncio
async def test_webhook_delivered_successfully():
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from app.models.payment import PaymentStatus
    from app.models.webhook_delivery import WebhookStatus
    from app.services.webhook_worker import process_webhook_delivery

    session = AsyncMock()

    payment = MagicMock()
    payment.status = PaymentStatus.SUCCEEDED
    session.get.return_value = payment

    delivery = MagicMock()
    delivery.id = uuid4()
    delivery.payment_id = uuid4()
    delivery.webhook_url = "https://example.com/webhook"
    delivery.attempts = 0
    delivery.status = WebhookStatus.PENDING

    with patch(
        "app.services.webhook_worker.send_webhook",
        new_callable=AsyncMock,
    ) as mock_send:
        await process_webhook_delivery(session, delivery)

    mock_send.assert_awaited_once_with(
        webhook_url=delivery.webhook_url,
        payment_id=delivery.payment_id,
        status="succeeded",
    )

    assert delivery.attempts == 1
    assert delivery.status == WebhookStatus.DELIVERED
    assert delivery.delivered_at is not None
    assert delivery.next_attempt_at is None
    assert delivery.last_error is None



from unittest.mock import AsyncMock, patch

import pytest

from app.services.webhook_worker import finalize_claimed_webhook


@pytest.mark.asyncio
async def test_stale_worker_cannot_finalize_webhook():
    """An outdated worker must not overwrite another worker's result."""

    fake_session = AsyncMock()
    fake_session.get.return_value = None

    from unittest.mock import MagicMock

    fake_factory = MagicMock()
    fake_factory.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.__aexit__ = AsyncMock(return_value=None)

    fake_transaction = MagicMock()
    fake_transaction.__aenter__ = AsyncMock(return_value=None)
    fake_transaction.__aexit__ = AsyncMock(return_value=None)

    fake_session.begin = MagicMock(return_value=fake_transaction)

    with patch(
        "app.services.webhook_worker.async_session_factory",
        return_value=fake_factory,
    ):
        result = await finalize_claimed_webhook(
            delivery_id="00000000-0000-0000-0000-000000000001",
            token="outdated-token",
            error=None,
        )

    assert result is False


@pytest.mark.asyncio
async def test_outdated_lease_token_cannot_finalize_webhook():
    """A worker with an outdated token cannot modify the delivery."""

    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.models.webhook_delivery import WebhookStatus

    delivery = SimpleNamespace(
        status=WebhookStatus.PROCESSING,
        lease_token="new-worker-token",
    )

    fake_session = AsyncMock()
    fake_session.get.return_value = delivery

    fake_transaction = MagicMock()
    fake_transaction.__aenter__ = AsyncMock(return_value=None)
    fake_transaction.__aexit__ = AsyncMock(return_value=None)

    fake_session.begin = MagicMock(return_value=fake_transaction)

    fake_factory = MagicMock()
    fake_factory.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.webhook_worker.async_session_factory",
        return_value=fake_factory,
    ):
        result = await finalize_claimed_webhook(
            delivery_id="00000000-0000-0000-0000-000000000001",
            token="old-worker-token",
            error=None,
        )

    assert result is False
    assert delivery.status == WebhookStatus.PROCESSING
    assert delivery.lease_token == "new-worker-token"


@pytest.mark.asyncio
async def test_expired_webhook_lease_after_max_attempts():
    """Expired leases with exhausted attempts are marked as failed."""

    from unittest.mock import MagicMock

    from app.services.webhook_worker import (
        fail_exhausted_webhook_leases,
    )

    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [
        "webhook-id-1",
        "webhook-id-2",
    ]

    fake_session = AsyncMock()
    fake_session.execute.return_value = fake_result

    fake_transaction = MagicMock()
    fake_transaction.__aenter__ = AsyncMock(return_value=None)
    fake_transaction.__aexit__ = AsyncMock(return_value=None)

    fake_session.begin = MagicMock(return_value=fake_transaction)

    fake_factory = MagicMock()
    fake_factory.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.webhook_worker.async_session_factory",
        return_value=fake_factory,
    ):
        count = await fail_exhausted_webhook_leases()

    assert count == 2
    fake_session.execute.assert_awaited_once()
