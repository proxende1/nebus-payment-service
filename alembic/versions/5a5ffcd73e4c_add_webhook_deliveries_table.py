"""add webhook deliveries table

Revision ID: 5a5ffcd73e4c
Revises: 0fbc84cfe175
Create Date: 2026-10-20 16:17:42.225360

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5a5ffcd73e4c'
down_revision: Union[str, Sequence[str], None] = '0fbc84cfe175'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    webhook_status = postgresql.ENUM(
        "pending",
        "delivered",
        "failed",
        name="webhook_status",
        create_type=False,
    )

    webhook_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("status", webhook_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id"),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")

    webhook_status = postgresql.ENUM(
        "pending",
        "delivered",
        "failed",
        name="webhook_status",
        create_type=False,
    )

    webhook_status.drop(op.get_bind(), checkfirst=True)
