import asyncio
import httpx
import ipaddress
import os
from urllib.parse import urlsplit
from uuid import UUID

WEBHOOK_ALLOWED_HOSTS = {
    host.strip().lower().rstrip(".")
    for host in os.getenv("WEBHOOK_ALLOWED_HOSTS", "").split(",")
    if host.strip()
}

def validate_webhook_url(webhook_url: str) -> None:
    parsed = urlsplit(webhook_url)

    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use HTTPS")

    if not parsed.hostname:
        raise ValueError("Webhook URL must have a hostname")

    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not contain credentials")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname not in WEBHOOK_ALLOWED_HOSTS:
        raise ValueError("Webhook hostname is not in the allowlist")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Localhost webhook URLs are not allowed")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return

    if not address.is_global:
        raise ValueError("Non-public IP addresses are not allowed")


async def send_webhook(
    webhook_url: str,
    payment_id: UUID,
    status: str,
) -> None:

    validate_webhook_url(webhook_url)

    payload = {
        "payment_id": str(payment_id),
        "status": status,
    }

    async with httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = await client.post(
            url=webhook_url,
            json=payload,
        )

        response.raise_for_status()


async def send_webhook_with_retry(
    webhook_url: str,
    payment_id: UUID,
    status: str,
    max_attempts: int = 3,
) -> None:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for attempt in range(1, max_attempts + 1):
        try:
            print(f"Webhook attempt {attempt}/{max_attempts}")

            await send_webhook(
                webhook_url=webhook_url,
                payment_id=payment_id,
                status=status,
            )

            print("Webhook delivered successfully")
            return

        except (httpx.HTTPError,) as exc:
            print(f"Webhook attempt {attempt} failed: {exc}")

            if attempt == max_attempts:
                raise

            delay = 2 ** attempt
            print(f"Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
