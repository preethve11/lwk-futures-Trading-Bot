-- Day 5 API schema additions for config snapshots and operator risk controls.

CREATE TABLE IF NOT EXISTS configs (
    id INTEGER PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    payload JSON NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_configs_name ON configs (name);
CREATE INDEX IF NOT EXISTS ix_configs_is_active ON configs (is_active);
CREATE INDEX IF NOT EXISTS ix_configs_created_at ON configs (created_at);

CREATE TABLE IF NOT EXISTS risk_state (
    id INTEGER PRIMARY KEY,
    kill_switch_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    manual_pause_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    daily_loss_locked BOOLEAN NOT NULL DEFAULT FALSE,
    drawdown_locked BOOLEAN NOT NULL DEFAULT FALSE,
    reason VARCHAR(500) NOT NULL DEFAULT '',
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_risk_state_kill_switch_enabled ON risk_state (kill_switch_enabled);
CREATE INDEX IF NOT EXISTS ix_risk_state_manual_pause_enabled ON risk_state (manual_pause_enabled);
CREATE INDEX IF NOT EXISTS ix_risk_state_daily_loss_locked ON risk_state (daily_loss_locked);
CREATE INDEX IF NOT EXISTS ix_risk_state_drawdown_locked ON risk_state (drawdown_locked);
