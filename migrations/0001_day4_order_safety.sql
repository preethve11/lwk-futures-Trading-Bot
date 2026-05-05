-- Day 4 execution-safety schema changes for existing SQLite/Postgres databases.
-- New installations still use SQLAlchemy Base.metadata.create_all.

ALTER TABLE orders ADD COLUMN stop_order_id VARCHAR(120);
ALTER TABLE orders ADD COLUMN take_profit_order_id VARCHAR(120);
ALTER TABLE orders ADD COLUMN protected BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN requires_manual_review BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN emergency_close_order_id VARCHAR(120);

CREATE INDEX IF NOT EXISTS ix_orders_protected ON orders (protected);
CREATE INDEX IF NOT EXISTS ix_orders_requires_manual_review ON orders (requires_manual_review);
