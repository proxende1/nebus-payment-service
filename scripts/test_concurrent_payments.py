import asyncio
import uuid

import httpx


API_URL ="http://127.0.0.1:8000/api/v1/payments"

PAYLOAD = {
    "amount": "1500.50",
    "currency": "RUB",
    "description": "Concurrent payment test",
    "metadata": {"source": "concurrency-test"},
    "webhook_url": "https://example.com/webhook",
}

async def main():
    idempotency_key = f"concurrent-{uuid.uuid4()}"

    headers = {
        "X-API-Key": "nebus_local_dev_key_2026",
        "Idempotency-Key": idempotency_key,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def send_payment(number: int):
            response = await client.post(
                API_URL,
                json=PAYLOAD,
                headers=headers,
            )

            print(f"Request {number}: HTTP {response.status_code}")

            return response

        responses = await asyncio.gather(
            *(send_payment(i) for i in range(1, 11))
        )

    payment_ids = []

    for response in responses:
        if response.status_code != 202:
            print("Error", response.text)
            continue

        payment_ids.append(response.json()["payment_id"])

    print("\nUnique payment IDs:", len(set(payment_ids)))

    assert len(payment_ids) == 10, "Some requests failed"
    assert len(set(payment_ids)) == 1, "Duplicate payments detected"

    print ("Concurrent idempotency test PASSED")

if __name__ == "__main__":
    asyncio.run(main())
