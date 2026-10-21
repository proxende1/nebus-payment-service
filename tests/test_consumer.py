from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.messaging.consumer import handle_payment


@pytest.mark.asyncio
async def test_consumer_succeeds_on_third_attempt():
    payment_id = uuid4()

    payment = MagicMock()
    payment.status.value = "succeeded"

    with (
        patch(
            "app.messaging.consumer.process_payment",
            new_callable=AsyncMock,
        ) as mock_process,
        patch(
            "app.messaging.consumer.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep,
    ):
        mock_process.side_effect = [
            RuntimeError("Temporary DB error"),
            RuntimeError("Temporary DB error"),
            payment,
        ]

        await handle_payment({"payment_id": str(payment_id)})

        assert mock_process.await_count == 3
        assert [
            call.args[0] for call in mock_sleep.await_args_list
        ] == [2, 4]


@pytest.mark.asyncio
async def test_consumer_fails_after_three_attempts():
    payment_id = uuid4()

    with (
        patch(
            "app.messaging.consumer.process_payment",
            new_callable=AsyncMock,
        ) as mock_process,
        patch(
            "app.messaging.consumer.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep,
    ):
        mock_process.side_effect = RuntimeError("Database unavailable")

        with pytest.raises(RuntimeError, match="Database unavailable"):
            await handle_payment({"payment_id": str(payment_id)})

        assert mock_process.await_count == 3
        assert [
            call.args[0] for call in mock_sleep.await_args_list
        ] == [2, 4]
