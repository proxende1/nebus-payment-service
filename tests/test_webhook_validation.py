import pytest
from pydantic import ValidationError
from unittest.mock import patch
from app.schemas.payment import PaymentCreate


def make_payment(webhook_url):
    return PaymentCreate(
        amount="100.00",
        currency="RUB",
        description="Test payment",
        metadata={},
        webhook_url=webhook_url,
    )


def test_webhook_url_is_optional():
    payment = make_payment(None)
    assert payment.webhook_url is None


def test_http_webhook_is_rejected():
    with pytest.raises(ValidationError):
        make_payment("http://webhook.example.com/callback")


def test_localhost_webhook_is_rejected():
    with pytest.raises(ValidationError):
        make_payment("https://localhost/callback")


def test_unapproved_host_is_rejected():
    with pytest.raises(ValidationError):
        make_payment("https://unapproved.example.com/callback")


def test_approved_https_webhook_is_accepted():
    with patch(
        "app.services.webhook.WEBHOOK_ALLOWED_HOSTS",
        {"webhook.example.com"},
    ):
        payment = make_payment("https://webhook.example.com/callback")

    assert str(payment.webhook_url) == "https://webhook.example.com/callback"