import pytest

from app.services.webhook import validate_webhook_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8001/webhook",
        "https://127.0.0.1/webhook",
        "https://localhost/webhook",
        "https://google.com/webhook",
    ],
)
def test_rejects_unsafe_webhook_urls(url, monkeypatch):
    monkeypatch.setattr(
        "app.services.webhook.WEBHOOK_ALLOWED_HOSTS",
        {"example.com"},
    )

    with pytest.raises(ValueError):
        validate_webhook_url(url)


def test_accepts_allowed_https_hostname(monkeypatch):
    monkeypatch.setattr(
        "app.services.webhook.WEBHOOK_ALLOWED_HOSTS",
        {"example.com"},
    )

    validate_webhook_url("https://example.com/webhook")
