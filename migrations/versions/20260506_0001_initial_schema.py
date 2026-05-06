"""initial schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260506_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('backtest_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.String(length=36), nullable=False),
    sa.Column('strategy_name', sa.String(length=120), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('timeframe', sa.String(length=16), nullable=False),
    sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('initial_capital', sa.Float(), nullable=False),
    sa.Column('final_capital', sa.Float(), nullable=False),
    sa.Column('total_trades', sa.Integer(), nullable=False),
    sa.Column('total_return_pct', sa.Float(), nullable=False),
    sa.Column('sharpe_ratio', sa.Float(), nullable=False),
    sa.Column('sortino_ratio', sa.Float(), nullable=False),
    sa.Column('max_drawdown_pct', sa.Float(), nullable=False),
    sa.Column('win_rate', sa.Float(), nullable=False),
    sa.Column('profit_factor', sa.Float(), nullable=False),
    sa.Column('expectancy', sa.Float(), nullable=False),
    sa.Column('config_snapshot', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('backtest_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_backtest_runs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_backtest_runs_run_id'), ['run_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_backtest_runs_strategy_name'), ['strategy_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_backtest_runs_symbol'), ['symbol'], unique=False)

    op.create_table('bot_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('strategy_name', sa.String(length=120), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('timeframe', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('config_snapshot', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bot_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bot_sessions_session_id'), ['session_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_bot_sessions_started_at'), ['started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_bot_sessions_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_bot_sessions_symbol'), ['symbol'], unique=False)

    op.create_table('configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_configs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_configs_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_configs_name'), ['name'], unique=True)

    op.create_table('risk_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kill_switch_enabled', sa.Boolean(), nullable=False),
    sa.Column('manual_pause_enabled', sa.Boolean(), nullable=False),
    sa.Column('daily_loss_locked', sa.Boolean(), nullable=False),
    sa.Column('drawdown_locked', sa.Boolean(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('risk_state', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_risk_state_daily_loss_locked'), ['daily_loss_locked'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_state_drawdown_locked'), ['drawdown_locked'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_state_kill_switch_enabled'), ['kill_switch_enabled'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_state_manual_pause_enabled'), ['manual_pause_enabled'], unique=False)

    op.create_table('positions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_session_id', sa.Integer(), nullable=True),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('side', sa.String(length=12), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=False),
    sa.Column('unrealized_pnl', sa.Float(), nullable=False),
    sa.Column('leverage', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['bot_session_id'], ['bot_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('positions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_positions_bot_session_id'), ['bot_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_positions_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_positions_symbol'), ['symbol'], unique=False)
        batch_op.create_index('ix_positions_symbol_status', ['symbol', 'status'], unique=False)

    op.create_table('risk_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_session_id', sa.Integer(), nullable=True),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('severity', sa.String(length=32), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bot_session_id'], ['bot_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('risk_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_risk_events_bot_session_id'), ['bot_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_events_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_events_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_events_severity'), ['severity'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_events_symbol'), ['symbol'], unique=False)

    op.create_table('signals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_session_id', sa.Integer(), nullable=True),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('strategy_name', sa.String(length=120), nullable=False),
    sa.Column('side', sa.String(length=12), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=False),
    sa.Column('stop_price', sa.Float(), nullable=False),
    sa.Column('take_profit_price', sa.Float(), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bot_session_id'], ['bot_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('signals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_signals_bot_session_id'), ['bot_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_signals_side'), ['side'], unique=False)
        batch_op.create_index(batch_op.f('ix_signals_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_signals_symbol'), ['symbol'], unique=False)
        batch_op.create_index(batch_op.f('ix_signals_timestamp'), ['timestamp'], unique=False)

    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_session_id', sa.Integer(), nullable=True),
    sa.Column('signal_id', sa.Integer(), nullable=True),
    sa.Column('exchange_order_id', sa.String(length=120), nullable=True),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('side', sa.String(length=12), nullable=False),
    sa.Column('order_type', sa.String(length=32), nullable=False),
    sa.Column('state', sa.Enum('PENDING', 'ENTRY_PLACED', 'TP_PLACED', 'SL_PLACED', 'PROTECTED', 'FAILED_UNPROTECTED', name='orderlifecyclestate'), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=True),
    sa.Column('avg_price', sa.Float(), nullable=True),
    sa.Column('stop_order_id', sa.String(length=120), nullable=True),
    sa.Column('take_profit_order_id', sa.String(length=120), nullable=True),
    sa.Column('protected', sa.Boolean(), nullable=False),
    sa.Column('requires_manual_review', sa.Boolean(), nullable=False),
    sa.Column('emergency_close_order_id', sa.String(length=120), nullable=True),
    sa.Column('limit_price', sa.Float(), nullable=True),
    sa.Column('stop_price', sa.Float(), nullable=True),
    sa.Column('reduce_only', sa.Boolean(), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('raw_response', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bot_session_id'], ['bot_sessions.id'], ),
    sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('exchange_order_id', name='uq_orders_exchange_order_id')
    )
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_orders_bot_session_id'), ['bot_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_protected'), ['protected'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_requires_manual_review'), ['requires_manual_review'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_side'), ['side'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_signal_id'), ['signal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_symbol'), ['symbol'], unique=False)
        batch_op.create_index('ix_orders_symbol_state', ['symbol', 'state'], unique=False)

    op.create_table('trades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_session_id', sa.Integer(), nullable=True),
    sa.Column('signal_id', sa.Integer(), nullable=True),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('side', sa.String(length=12), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=False),
    sa.Column('exit_price', sa.Float(), nullable=False),
    sa.Column('pnl', sa.Float(), nullable=False),
    sa.Column('pnl_pct', sa.Float(), nullable=False),
    sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('exit_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('exit_reason', sa.String(length=64), nullable=False),
    sa.Column('fees', sa.Float(), nullable=False),
    sa.Column('slippage_usd', sa.Float(), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bot_session_id'], ['bot_sessions.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('trades', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trades_bot_session_id'), ['bot_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_trades_entry_time'), ['entry_time'], unique=False)
        batch_op.create_index(batch_op.f('ix_trades_exit_time'), ['exit_time'], unique=False)
        batch_op.create_index(batch_op.f('ix_trades_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_trades_signal_id'), ['signal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_trades_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_trades_symbol'), ['symbol'], unique=False)
        batch_op.create_index('ix_trades_symbol_exit_time', ['symbol', 'exit_time'], unique=False)

    op.create_table('ai_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_session_id', sa.Integer(), nullable=True),
    sa.Column('signal_id', sa.Integer(), nullable=True),
    sa.Column('trade_id', sa.Integer(), nullable=True),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('strategy_name', sa.String(length=120), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('prompt', sa.String(length=4000), nullable=False),
    sa.Column('report_text', sa.String(length=4000), nullable=False),
    sa.Column('input_snapshot', sa.JSON(), nullable=False),
    sa.Column('risk_state', sa.JSON(), nullable=False),
    sa.Column('market_regime', sa.JSON(), nullable=False),
    sa.Column('outcome', sa.JSON(), nullable=False),
    sa.Column('raw_response', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bot_session_id'], ['bot_sessions.id'], ),
    sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ),
    sa.ForeignKeyConstraint(['trade_id'], ['trades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_reports_bot_session_id'), ['bot_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_reports_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_reports_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_reports_signal_id'), ['signal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_reports_symbol'), ['symbol'], unique=False)
        batch_op.create_index('ix_ai_reports_symbol_created_at', ['symbol', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_reports_trade_id'), ['trade_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('ai_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_reports_trade_id'))
        batch_op.drop_index('ix_ai_reports_symbol_created_at')
        batch_op.drop_index(batch_op.f('ix_ai_reports_symbol'))
        batch_op.drop_index(batch_op.f('ix_ai_reports_signal_id'))
        batch_op.drop_index(batch_op.f('ix_ai_reports_event_type'))
        batch_op.drop_index(batch_op.f('ix_ai_reports_created_at'))
        batch_op.drop_index(batch_op.f('ix_ai_reports_bot_session_id'))

    op.drop_table('ai_reports')
    with op.batch_alter_table('trades', schema=None) as batch_op:
        batch_op.drop_index('ix_trades_symbol_exit_time')
        batch_op.drop_index(batch_op.f('ix_trades_symbol'))
        batch_op.drop_index(batch_op.f('ix_trades_source'))
        batch_op.drop_index(batch_op.f('ix_trades_signal_id'))
        batch_op.drop_index(batch_op.f('ix_trades_order_id'))
        batch_op.drop_index(batch_op.f('ix_trades_exit_time'))
        batch_op.drop_index(batch_op.f('ix_trades_entry_time'))
        batch_op.drop_index(batch_op.f('ix_trades_bot_session_id'))

    op.drop_table('trades')
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('ix_orders_symbol_state')
        batch_op.drop_index(batch_op.f('ix_orders_symbol'))
        batch_op.drop_index(batch_op.f('ix_orders_state'))
        batch_op.drop_index(batch_op.f('ix_orders_signal_id'))
        batch_op.drop_index(batch_op.f('ix_orders_side'))
        batch_op.drop_index(batch_op.f('ix_orders_requires_manual_review'))
        batch_op.drop_index(batch_op.f('ix_orders_protected'))
        batch_op.drop_index(batch_op.f('ix_orders_created_at'))
        batch_op.drop_index(batch_op.f('ix_orders_bot_session_id'))

    op.drop_table('orders')
    with op.batch_alter_table('signals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_signals_timestamp'))
        batch_op.drop_index(batch_op.f('ix_signals_symbol'))
        batch_op.drop_index(batch_op.f('ix_signals_status'))
        batch_op.drop_index(batch_op.f('ix_signals_side'))
        batch_op.drop_index(batch_op.f('ix_signals_bot_session_id'))

    op.drop_table('signals')
    with op.batch_alter_table('risk_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_risk_events_symbol'))
        batch_op.drop_index(batch_op.f('ix_risk_events_severity'))
        batch_op.drop_index(batch_op.f('ix_risk_events_event_type'))
        batch_op.drop_index(batch_op.f('ix_risk_events_created_at'))
        batch_op.drop_index(batch_op.f('ix_risk_events_bot_session_id'))

    op.drop_table('risk_events')
    with op.batch_alter_table('positions', schema=None) as batch_op:
        batch_op.drop_index('ix_positions_symbol_status')
        batch_op.drop_index(batch_op.f('ix_positions_symbol'))
        batch_op.drop_index(batch_op.f('ix_positions_status'))
        batch_op.drop_index(batch_op.f('ix_positions_bot_session_id'))

    op.drop_table('positions')
    with op.batch_alter_table('risk_state', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_risk_state_manual_pause_enabled'))
        batch_op.drop_index(batch_op.f('ix_risk_state_kill_switch_enabled'))
        batch_op.drop_index(batch_op.f('ix_risk_state_drawdown_locked'))
        batch_op.drop_index(batch_op.f('ix_risk_state_daily_loss_locked'))

    op.drop_table('risk_state')
    with op.batch_alter_table('configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_configs_name'))
        batch_op.drop_index(batch_op.f('ix_configs_is_active'))
        batch_op.drop_index(batch_op.f('ix_configs_created_at'))

    op.drop_table('configs')
    with op.batch_alter_table('bot_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bot_sessions_symbol'))
        batch_op.drop_index(batch_op.f('ix_bot_sessions_status'))
        batch_op.drop_index(batch_op.f('ix_bot_sessions_started_at'))
        batch_op.drop_index(batch_op.f('ix_bot_sessions_session_id'))

    op.drop_table('bot_sessions')
    with op.batch_alter_table('backtest_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_backtest_runs_symbol'))
        batch_op.drop_index(batch_op.f('ix_backtest_runs_strategy_name'))
        batch_op.drop_index(batch_op.f('ix_backtest_runs_run_id'))
        batch_op.drop_index(batch_op.f('ix_backtest_runs_created_at'))

    op.drop_table('backtest_runs')
