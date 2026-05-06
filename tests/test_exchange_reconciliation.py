from __future__ import annotations

from sqlalchemy import select

from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.models import ExchangeFillModel, TradeModel
from app.workers.exchange_reconciliation import ExchangeReconciliationWorker


def _session_factory() -> SessionFactory:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    return factory


def _entry_fill() -> dict[str, object]:
    return {
        "symbol": "ZECUSDT",
        "id": 1001,
        "orderId": 501,
        "side": "BUY",
        "price": "100.00",
        "qty": "0.5",
        "quoteQty": "50.00",
        "realizedPnl": "0",
        "commission": "0.01",
        "commissionAsset": "USDT",
        "buyer": True,
        "maker": False,
        "time": 1767225600000,
    }


def _closing_fill() -> dict[str, object]:
    return {
        "symbol": "ZECUSDT",
        "id": 1002,
        "orderId": 502,
        "side": "SELL",
        "price": "102.00",
        "qty": "0.5",
        "quoteQty": "51.00",
        "realizedPnl": "1.0",
        "commission": "0.01",
        "commissionAsset": "USDT",
        "buyer": False,
        "maker": False,
        "time": 1767225900000,
    }


def test_exchange_reconciliation_persists_fills_and_closed_trade_idempotently() -> None:
    factory = _session_factory()
    worker = ExchangeReconciliationWorker(factory)

    first = worker.reconcile_raw_fills(symbol="ZECUSDT", raw_fills=[_entry_fill(), _closing_fill()])
    second = worker.reconcile_raw_fills(symbol="ZECUSDT", raw_fills=[_entry_fill(), _closing_fill()])

    assert first.fetched == 2
    assert first.fills_created == 2
    assert first.closed_trades_created == 1
    assert second.fills_created == 0
    assert second.fills_seen == 2
    assert second.closed_trades_created == 0
    assert second.closed_trades_seen == 1

    with session_scope(factory) as session:
        fills = session.scalars(select(ExchangeFillModel).order_by(ExchangeFillModel.exchange_trade_id)).all()
        trades = session.scalars(select(TradeModel)).all()

    assert len(fills) == 2
    assert len(trades) == 1
    assert fills[1].trade_id == trades[0].id
    assert trades[0].exchange_trade_id == "1002"
    assert trades[0].exchange_order_id == "502"
    assert trades[0].side == "BUY"
    assert trades[0].entry_price == 100.0
    assert trades[0].exit_price == 102.0
    assert trades[0].pnl == 1.0
    assert trades[0].pnl_pct == 2.0


def test_exchange_reconciliation_skips_invalid_fill_side() -> None:
    factory = _session_factory()
    worker = ExchangeReconciliationWorker(factory)
    invalid_fill = dict(_entry_fill())
    invalid_fill["id"] = 1003
    invalid_fill["side"] = "UNKNOWN"

    summary = worker.reconcile_raw_fills(symbol="ZECUSDT", raw_fills=[invalid_fill])

    assert summary.fetched == 1
    assert summary.fills_created == 0
    assert len(summary.parse_errors) == 1
    with session_scope(factory) as session:
        assert session.scalar(select(ExchangeFillModel)) is None
