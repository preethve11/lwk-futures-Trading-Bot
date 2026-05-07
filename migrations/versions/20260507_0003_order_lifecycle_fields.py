"""add order lifecycle reconciliation fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260507_0003"
down_revision = "20260506_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exchange_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("filled_quantity", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("remaining_quantity", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f("ix_orders_exchange_status"), ["exchange_status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_orders_exchange_status"))
        batch_op.drop_column("last_reconciled_at")
        batch_op.drop_column("remaining_quantity")
        batch_op.drop_column("filled_quantity")
        batch_op.drop_column("exchange_status")
