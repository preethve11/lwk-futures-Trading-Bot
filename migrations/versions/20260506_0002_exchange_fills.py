"""add exchange fill reconciliation ledger."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260506_0002"
down_revision = "20260506_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exchange_trade_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("exchange_order_id", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_trades_exchange_order_id", ["exchange_order_id"], unique=False)
        batch_op.create_unique_constraint("uq_trades_exchange_trade_id", ["exchange_trade_id"])

    op.create_table(
        "exchange_fills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_session_id", sa.Integer(), nullable=True),
        sa.Column("trade_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("exchange_trade_id", sa.String(length=120), nullable=False),
        sa.Column("exchange_order_id", sa.String(length=120), nullable=False),
        sa.Column("side", sa.String(length=12), nullable=False),
        sa.Column("position_side", sa.String(length=16), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("quote_quantity", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=False),
        sa.Column("commission", sa.Float(), nullable=False),
        sa.Column("commission_asset", sa.String(length=24), nullable=False),
        sa.Column("buyer", sa.Boolean(), nullable=False),
        sa.Column("maker", sa.Boolean(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_session_id"], ["bot_sessions.id"]),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_trade_id", name="uq_exchange_fills_exchange_trade_id"),
    )
    with op.batch_alter_table("exchange_fills", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_exchange_fills_bot_session_id"), ["bot_session_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_exchange_fills_created_at"), ["created_at"], unique=False)
        batch_op.create_index("ix_exchange_fills_exchange_order_id", ["exchange_order_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_exchange_fills_event_time"), ["event_time"], unique=False)
        batch_op.create_index(batch_op.f("ix_exchange_fills_side"), ["side"], unique=False)
        batch_op.create_index(batch_op.f("ix_exchange_fills_symbol"), ["symbol"], unique=False)
        batch_op.create_index("ix_exchange_fills_symbol_event_time", ["symbol", "event_time"], unique=False)
        batch_op.create_index(batch_op.f("ix_exchange_fills_trade_id"), ["trade_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("exchange_fills", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exchange_fills_trade_id"))
        batch_op.drop_index("ix_exchange_fills_symbol_event_time")
        batch_op.drop_index(batch_op.f("ix_exchange_fills_symbol"))
        batch_op.drop_index(batch_op.f("ix_exchange_fills_side"))
        batch_op.drop_index(batch_op.f("ix_exchange_fills_event_time"))
        batch_op.drop_index("ix_exchange_fills_exchange_order_id")
        batch_op.drop_index(batch_op.f("ix_exchange_fills_created_at"))
        batch_op.drop_index(batch_op.f("ix_exchange_fills_bot_session_id"))

    op.drop_table("exchange_fills")

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_constraint("uq_trades_exchange_trade_id", type_="unique")
        batch_op.drop_index("ix_trades_exchange_order_id")
        batch_op.drop_column("exchange_order_id")
        batch_op.drop_column("exchange_trade_id")
