
"""Add webhook processing lease.

Revision ID: beb1fa8b123b
Revises: afe6e762eb1d
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "beb1fa8b123b"
down_revision: Union[str, Sequence[str], None] = "afe6e762eb1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE webhook_status ADD VALUE IF NOT EXISTS 'processing'"
    )

    op.add_column(
        "webhook_deliveries",
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Downgrade must not leave active processing leases.
    connection = op.get_bind()

    active = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM webhook_deliveries "
            "WHERE status = 'processing'"
        )
    ).scalar_one()

    if active:
        raise RuntimeError(
            "Cannot downgrade while webhook deliveries are processing"
        )

    op.drop_column("webhook_deliveries", "lease_expires_at")

    # PostgreSQL cannot directly remove an ENUM value.
    # Recreate the type without 'processing'.
    op.execute(
        "ALTER TYPE webhook_status RENAME TO webhook_status_old"
    )

    op.execute(
        "CREATE TYPE webhook_status AS ENUM "
        "('pending', 'delivered', 'failed')"
    )

    op.execute(
        "ALTER TABLE webhook_deliveries "
        "ALTER COLUMN status TYPE webhook_status "
        "USING status::text::webhook_status"
    )

    op.execute("DROP TYPE webhook_status_old")
