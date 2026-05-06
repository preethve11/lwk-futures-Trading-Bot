-- Add advisory-only AI trade journal reports.
-- Existing local/dev startup still uses SQLAlchemy Base.metadata.create_all.

CREATE TABLE IF NOT EXISTS ai_reports (
    id SERIAL PRIMARY KEY,
    bot_session_id INTEGER NULL REFERENCES bot_sessions(id),
    signal_id INTEGER NULL REFERENCES signals(id),
    trade_id INTEGER NULL REFERENCES trades(id),
    symbol VARCHAR(32) NOT NULL,
    strategy_name VARCHAR(120) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    model VARCHAR(120) NOT NULL,
    prompt VARCHAR(4000) NOT NULL DEFAULT '',
    report_text VARCHAR(4000) NOT NULL DEFAULT '',
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    market_regime JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ai_reports_bot_session_id ON ai_reports(bot_session_id);
CREATE INDEX IF NOT EXISTS ix_ai_reports_signal_id ON ai_reports(signal_id);
CREATE INDEX IF NOT EXISTS ix_ai_reports_trade_id ON ai_reports(trade_id);
CREATE INDEX IF NOT EXISTS ix_ai_reports_symbol ON ai_reports(symbol);
CREATE INDEX IF NOT EXISTS ix_ai_reports_event_type ON ai_reports(event_type);
CREATE INDEX IF NOT EXISTS ix_ai_reports_created_at ON ai_reports(created_at);
CREATE INDEX IF NOT EXISTS ix_ai_reports_symbol_created_at ON ai_reports(symbol, created_at);
