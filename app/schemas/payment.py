from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl
from pydantic import field_validator
from app.services.webhook import validate_webhook_url

from app.models.payment import Payment

class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    RUB = "RUB"

class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt = 0, max_digits = 18, decimal_places = 2)
    currency: Currency
    description: str = Field(min_length = 1, max_length = 500)
    metadata: dict[str, Any] = Field(default_factory = dict)
    webhook_url: HttpUrl | None = None

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None:
            validate_webhook_url(str(value))
        return value

from datetime import datetime
from uuid import UUID

class PaymentCreatedResponse(BaseModel):
    payment_id: UUID
    status: str
    created_at: datetime

def payment_matches_request(
        payment: Payment,
        data: PaymentCreate,
) -> bool:
    return (
        payment.amount == data.amount and
        payment.currency == data.currency.value and
        payment.description == data.description and
        payment.payment_metadata == data.metadata and
        payment.webhook_url == str(data.webhook_url)
    )


class PaymentDetailResponse(BaseModel):
    payment_id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: str
    webhook_url: HttpUrl | None = None
    created_at: datetime
    processed_at: datetime | None
