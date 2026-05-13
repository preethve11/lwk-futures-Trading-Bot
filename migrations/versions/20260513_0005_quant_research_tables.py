"""add quant research persistence tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0005"
down_revision = "20260507_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("quote_volume", sa.Float(), nullable=False),
        sa.Column("trades_count", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "timeframe", "open_time", name="uq_market_data_symbol_timeframe_open_time"),
    )
    op.create_index("ix_market_data_symbol_timeframe_open_time", "market_data", ["symbol", "timeframe", "open_time"])
    op.create_index(op.f("ix_market_data_symbol"), "market_data", ["symbol"])
    op.create_index(op.f("ix_market_data_timeframe"), "market_data", ["timeframe"])
    op.create_index(op.f("ix_market_data_open_time"), "market_data", ["open_time"])
    op.create_index(op.f("ix_market_data_source"), "market_data", ["source"])
    op.create_index(op.f("ix_market_data_is_closed"), "market_data", ["is_closed"])
    op.create_index(op.f("ix_market_data_created_at"), "market_data", ["created_at"])

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_set_version", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "timeframe",
            "event_time",
            "feature_set_version",
            name="uq_features_symbol_timeframe_event_time_version",
        ),
    )
    op.create_index("ix_features_symbol_timeframe_event_time", "features", ["symbol", "timeframe", "event_time"])
    op.create_index(op.f("ix_features_symbol"), "features", ["symbol"])
    op.create_index(op.f("ix_features_timeframe"), "features", ["timeframe"])
    op.create_index(op.f("ix_features_event_time"), "features", ["event_time"])
    op.create_index(op.f("ix_features_feature_set_version"), "features", ["feature_set_version"])
    op.create_index(op.f("ix_features_created_at"), "features", ["created_at"])

    op.create_table(
        "regimes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detector_version", sa.String(length=64), nullable=False),
        sa.Column("trend_state", sa.String(length=32), nullable=False),
        sa.Column("volatility_state", sa.String(length=32), nullable=False),
        sa.Column("liquidity_state", sa.String(length=32), nullable=False),
        sa.Column("regime_id", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "timeframe",
            "event_time",
            "detector_version",
            name="uq_regimes_symbol_timeframe_event_time_version",
        ),
    )
    op.create_index("ix_regimes_symbol_timeframe_event_time", "regimes", ["symbol", "timeframe", "event_time"])
    op.create_index(op.f("ix_regimes_symbol"), "regimes", ["symbol"])
    op.create_index(op.f("ix_regimes_timeframe"), "regimes", ["timeframe"])
    op.create_index(op.f("ix_regimes_event_time"), "regimes", ["event_time"])
    op.create_index(op.f("ix_regimes_detector_version"), "regimes", ["detector_version"])
    op.create_index(op.f("ix_regimes_trend_state"), "regimes", ["trend_state"])
    op.create_index(op.f("ix_regimes_volatility_state"), "regimes", ["volatility_state"])
    op.create_index(op.f("ix_regimes_liquidity_state"), "regimes", ["liquidity_state"])
    op.create_index(op.f("ix_regimes_regime_id"), "regimes", ["regime_id"])
    op.create_index(op.f("ix_regimes_created_at"), "regimes", ["created_at"])

    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("family", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("allowed_regimes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id"),
    )
    op.create_index(op.f("ix_strategies_strategy_id"), "strategies", ["strategy_id"])
    op.create_index(op.f("ix_strategies_name"), "strategies", ["name"])
    op.create_index(op.f("ix_strategies_family"), "strategies", ["family"])
    op.create_index(op.f("ix_strategies_status"), "strategies", ["status"])
    op.create_index(op.f("ix_strategies_created_at"), "strategies", ["created_at"])

    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.String(length=160), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("regime_metrics", sa.JSON(), nullable=False),
        sa.Column("fee_bps", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("passed_validation", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_results_strategy_symbol_timeframe", "backtest_results", ["strategy_id", "symbol", "timeframe"])
    op.create_index(op.f("ix_backtest_results_run_id"), "backtest_results", ["run_id"])
    op.create_index(op.f("ix_backtest_results_strategy_id"), "backtest_results", ["strategy_id"])
    op.create_index(op.f("ix_backtest_results_symbol"), "backtest_results", ["symbol"])
    op.create_index(op.f("ix_backtest_results_timeframe"), "backtest_results", ["timeframe"])
    op.create_index(op.f("ix_backtest_results_passed_validation"), "backtest_results", ["passed_validation"])
    op.create_index(op.f("ix_backtest_results_created_at"), "backtest_results", ["created_at"])

    op.create_table(
        "executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("exchange_execution_id", sa.String(length=120), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("strategy_id", sa.String(length=160), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("side", sa.String(length=12), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("expected_price", sa.Float(), nullable=True),
        sa.Column("actual_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("fee_asset", sa.String(length=24), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_execution_id", name="uq_executions_exchange_execution_id"),
    )
    op.create_index("ix_executions_symbol_event_time", "executions", ["symbol", "event_time"])
    op.create_index(op.f("ix_executions_order_id"), "executions", ["order_id"])
    op.create_index(op.f("ix_executions_symbol"), "executions", ["symbol"])
    op.create_index(op.f("ix_executions_strategy_id"), "executions", ["strategy_id"])
    op.create_index(op.f("ix_executions_mode"), "executions", ["mode"])
    op.create_index(op.f("ix_executions_side"), "executions", ["side"])
    op.create_index(op.f("ix_executions_status"), "executions", ["status"])
    op.create_index(op.f("ix_executions_event_time"), "executions", ["event_time"])
    op.create_index(op.f("ix_executions_created_at"), "executions", ["created_at"])

    op.create_table(
        "portfolio_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.String(length=160), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("allocated_capital", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("max_weight", sa.Float(), nullable=False),
        sa.Column("regime_id", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolio_allocations_strategy_created_at", "portfolio_allocations", ["strategy_id", "created_at"])
    op.create_index(op.f("ix_portfolio_allocations_strategy_id"), "portfolio_allocations", ["strategy_id"])
    op.create_index(op.f("ix_portfolio_allocations_symbol"), "portfolio_allocations", ["symbol"])
    op.create_index(op.f("ix_portfolio_allocations_regime_id"), "portfolio_allocations", ["regime_id"])
    op.create_index(op.f("ix_portfolio_allocations_active"), "portfolio_allocations", ["active"])
    op.create_index(op.f("ix_portfolio_allocations_created_at"), "portfolio_allocations", ["created_at"])

    op.create_table(
        "performance_health",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.String(length=160), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expectancy", sa.Float(), nullable=False),
        sa.Column("profit_factor", sa.Float(), nullable=False),
        sa.Column("sharpe_ratio", sa.Float(), nullable=False),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("degradation_pct", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_performance_health_strategy_checked_at", "performance_health", ["strategy_id", "checked_at"])
    op.create_index(op.f("ix_performance_health_strategy_id"), "performance_health", ["strategy_id"])
    op.create_index(op.f("ix_performance_health_symbol"), "performance_health", ["symbol"])
    op.create_index(op.f("ix_performance_health_timeframe"), "performance_health", ["timeframe"])
    op.create_index(op.f("ix_performance_health_status"), "performance_health", ["status"])
    op.create_index(op.f("ix_performance_health_checked_at"), "performance_health", ["checked_at"])

    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=24), nullable=False),
        sa.Column("logger", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_logs_level_created_at", "system_logs", ["level", "created_at"])
    op.create_index(op.f("ix_system_logs_level"), "system_logs", ["level"])
    op.create_index(op.f("ix_system_logs_logger"), "system_logs", ["logger"])
    op.create_index(op.f("ix_system_logs_event_type"), "system_logs", ["event_type"])
    op.create_index(op.f("ix_system_logs_created_at"), "system_logs", ["created_at"])


def downgrade() -> None:
    for index_name in [
        "ix_system_logs_created_at",
        "ix_system_logs_event_type",
        "ix_system_logs_logger",
        "ix_system_logs_level",
        "ix_system_logs_level_created_at",
    ]:
        op.drop_index(index_name, table_name="system_logs")
    op.drop_table("system_logs")

    for index_name in [
        "ix_performance_health_checked_at",
        "ix_performance_health_status",
        "ix_performance_health_timeframe",
        "ix_performance_health_symbol",
        "ix_performance_health_strategy_id",
        "ix_performance_health_strategy_checked_at",
    ]:
        op.drop_index(index_name, table_name="performance_health")
    op.drop_table("performance_health")

    for index_name in [
        "ix_portfolio_allocations_created_at",
        "ix_portfolio_allocations_active",
        "ix_portfolio_allocations_regime_id",
        "ix_portfolio_allocations_symbol",
        "ix_portfolio_allocations_strategy_id",
        "ix_portfolio_allocations_strategy_created_at",
    ]:
        op.drop_index(index_name, table_name="portfolio_allocations")
    op.drop_table("portfolio_allocations")

    for index_name in [
        "ix_executions_created_at",
        "ix_executions_event_time",
        "ix_executions_status",
        "ix_executions_side",
        "ix_executions_mode",
        "ix_executions_strategy_id",
        "ix_executions_symbol",
        "ix_executions_order_id",
        "ix_executions_symbol_event_time",
    ]:
        op.drop_index(index_name, table_name="executions")
    op.drop_table("executions")

    for index_name in [
        "ix_backtest_results_created_at",
        "ix_backtest_results_passed_validation",
        "ix_backtest_results_timeframe",
        "ix_backtest_results_symbol",
        "ix_backtest_results_strategy_id",
        "ix_backtest_results_run_id",
        "ix_backtest_results_strategy_symbol_timeframe",
    ]:
        op.drop_index(index_name, table_name="backtest_results")
    op.drop_table("backtest_results")

    for index_name in [
        "ix_strategies_created_at",
        "ix_strategies_status",
        "ix_strategies_family",
        "ix_strategies_name",
        "ix_strategies_strategy_id",
    ]:
        op.drop_index(index_name, table_name="strategies")
    op.drop_table("strategies")

    for index_name in [
        "ix_regimes_created_at",
        "ix_regimes_regime_id",
        "ix_regimes_liquidity_state",
        "ix_regimes_volatility_state",
        "ix_regimes_trend_state",
        "ix_regimes_detector_version",
        "ix_regimes_event_time",
        "ix_regimes_timeframe",
        "ix_regimes_symbol",
        "ix_regimes_symbol_timeframe_event_time",
    ]:
        op.drop_index(index_name, table_name="regimes")
    op.drop_table("regimes")

    for index_name in [
        "ix_features_created_at",
        "ix_features_feature_set_version",
        "ix_features_event_time",
        "ix_features_timeframe",
        "ix_features_symbol",
        "ix_features_symbol_timeframe_event_time",
    ]:
        op.drop_index(index_name, table_name="features")
    op.drop_table("features")

    for index_name in [
        "ix_market_data_created_at",
        "ix_market_data_is_closed",
        "ix_market_data_source",
        "ix_market_data_open_time",
        "ix_market_data_timeframe",
        "ix_market_data_symbol",
        "ix_market_data_symbol_timeframe_open_time",
    ]:
        op.drop_index(index_name, table_name="market_data")
    op.drop_table("market_data")
