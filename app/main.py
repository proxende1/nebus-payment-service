import os

from uuid import UUID
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.payment import (
    PaymentCreate,
    PaymentCreatedResponse,
    PaymentDetailResponse,
)
from app.services.payment import (
    create_payment,
    get_payment_by_id,
    get_payment_by_idempotency_key,
    payment_matches_request,
)

app = FastAPI(title = "Nebus Payment Service")

async def verify_api_key(
        x_api_key: str = Header(..., alias="X-API-Key"),
):
    expected_key = os.environ["API_KEY"]

    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

@app.get("/health")
async def health(
    _: None = Depends(verify_api_key)
):
    return {"status": "ok",}

@app.post(
    "/api/v1/payments",
    response_model=PaymentCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    )
async def create_payment_endpoint(
    data: PaymentCreate,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        ),
        _: None = Depends(verify_api_key),
        session: AsyncSession = Depends(get_db),
):
    existing_payment = await get_payment_by_idempotency_key(
        session=session,
        idempotency_key=idempotency_key,
    )

    if existing_payment:
        if not payment_matches_request(existing_payment, data):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already used with different payment data",
            )
        return PaymentCreatedResponse(
            payment_id=existing_payment.id,
            status=existing_payment.status.value,
            created_at=existing_payment.created_at,
        )

    try:
        payment = await create_payment(
            session=session,
            data=data,
            idempotency_key=idempotency_key,
            )
    except IntegrityError:
        await session.rollback()

        payment = await get_payment_by_idempotency_key(
            session=session,
            idempotency_key=idempotency_key,
            )

        if payment is None or not payment_matches_request(payment, data):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already used with different payment data",
            )

    return PaymentCreatedResponse(
        payment_id=payment.id,
        status=payment.status.value,
        created_at=payment.created_at,
    )


@app.get(
    "/api/v1/payments/{payment_id}",
    response_model=PaymentDetailResponse,
)
async def get_payment_endpoint(
    payment_id: UUID,
    _: None = Depends(verify_api_key),
    session: AsyncSession = Depends(get_db),
):
    payment = await get_payment_by_id(
        session=session,
        payment_id=payment_id,
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return PaymentDetailResponse(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.payment_metadata,
        status=payment.status.value,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )
