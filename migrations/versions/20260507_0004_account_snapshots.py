"""add account equity snapshots."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260507_0004"
down_revision = "20260507_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_session_id", sa.Integer(), nullable=True),
        sa.Column("asset", sa.String(length=24), nullable=False),
        sa.Column("wallet_balance", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("margin_balance", sa.Float(), nullable=False),
        sa.Column("available_balance", sa.Float(), nullable=False),
        sa.Column("max_withdraw_amount", sa.Float(), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_session_id"], ["bot_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_snapshots_asset"), "account_snapshots", ["asset"], unique=False)
    op.create_index(
        "ix_account_snapshots_asset_event_time",
        "account_snapshots",
        ["asset", "event_time"],
        unique=False,
    )
    op.create_index(op.f("ix_account_snapshots_bot_session_id"), "account_snapshots", ["bot_session_id"], unique=False)
    op.create_index(op.f("ix_account_snapshots_created_at"), "account_snapshots", ["created_at"], unique=False)
    op.create_index(op.f("ix_account_snapshots_event_time"), "account_snapshots", ["event_time"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_account_snapshots_event_time"), table_name="account_snapshots")
    op.drop_index(op.f("ix_account_snapshots_created_at"), table_name="account_snapshots")
    op.drop_index(op.f("ix_account_snapshots_bot_session_id"), table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_asset_event_time", table_name="account_snapshots")
    op.drop_index(op.f("ix_account_snapshots_asset"), table_name="account_snapshots")
    op.drop_table("account_snapshots")
