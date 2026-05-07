from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.models import AccountSnapshotModel, RiskEventModel
from app.workers.account_equity import AccountEquityReconciliationWorker
from trading_bot.execution.base import AccountSnapshot
from trading_bot.execution.binance_futures import BinanceFuturesClient
from trading_bot.utils.alerts import AlertQueue


class FakeAccountClient:
    def __init__(self, snapshots: list[AccountSnapshot | None]) -> None:
        self.snapshots = snapshots

    def get_account_snapshot(self, asset: str = "USDT") -> AccountSnapshot | None:
        return self.snapshots.pop(0)


class FakeBinanceApi:
    def futures_account(self) -> dict[str, object]:
        return {
            "totalWalletBalance": "1000.50",
            "totalUnrealizedProfit": "5.25",
            "totalMarginBalance": "1005.75",
            "availableBalance": "900.00",
            "maxWithdrawAmount": "850.00",
            "updateTime": 1767225600000,
            "assets": [
                {
                    "asset": "USDT",
                    "walletBalance": "999.00",
                    "unrealizedProfit": "1.00",
                    "marginBalance": "1000.00",
                    "availableBalance": "800.00",
                }
            ],
        }


def _session_factory() -> SessionFactory:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    return factory


def _alert_queue(sent: list[str]) -> AlertQueue:
    def sender(text: str, bot_token: str, chat_id: str) -> bool:
        sent.append(text)
        return True

    return AlertQueue(sender=sender, autostart=True)


def _snapshot(wallet: float, equity: float) -> AccountSnapshot:
    return AccountSnapshot(
        asset="USDT",
        wallet_balance=wallet,
        unrealized_pnl=equity - wallet,
        margin_balance=equity,
        available_balance=wallet - 100,
        event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        raw_response={"wallet": wallet, "equity": equity},
    )


def test_account_equity_reconciliation_persists_live_snapshot_without_initial_drift() -> None:
    factory = _session_factory()
    sent: list[str] = []
    queue = _alert_queue(sent)
    worker = AccountEquityReconciliationWorker(
        session_factory=factory,
        client=FakeAccountClient([_snapshot(1000.0, 1002.0)]),
        alert_queue=queue,
        drift_threshold_usd=25.0,
        drift_threshold_pct=5.0,
    )

    summary = worker.reconcile_once(asset="USDT")

    queue.stop(drain=True)
    with session_scope(factory) as session:
        snapshot = session.scalar(select(AccountSnapshotModel))
        events = session.scalars(select(RiskEventModel)).all()

    assert summary.snapshot_id is not None
    assert summary.drift_detected is False
    assert snapshot is not None
    assert snapshot.margin_balance == 1002.0
    assert events == []
    assert sent == []


def test_account_equity_reconciliation_alerts_and_audits_balance_drift() -> None:
    factory = _session_factory()
    sent: list[str] = []
    queue = _alert_queue(sent)
    worker = AccountEquityReconciliationWorker(
        session_factory=factory,
        client=FakeAccountClient([_snapshot(1000.0, 1000.0), _snapshot(1030.0, 1030.0)]),
        alert_queue=queue,
        drift_threshold_usd=25.0,
        drift_threshold_pct=5.0,
    )

    first = worker.reconcile_once(asset="USDT")
    second = worker.reconcile_once(asset="USDT")

    queue.stop(drain=True)
    with session_scope(factory) as session:
        snapshots = session.scalars(select(AccountSnapshotModel).order_by(AccountSnapshotModel.id.asc())).all()
        event = session.scalar(select(RiskEventModel))

    assert first.drift_detected is False
    assert second.drift_detected is True
    assert second.equity_delta == 30.0
    assert len(snapshots) == 2
    assert event is not None
    assert event.event_type == "account_balance_drift"
    assert event.severity == "WARNING"
    assert event.payload["equity_delta"] == 30.0
    assert any("[WARNING] Account balance drift detected" in message for message in sent)


def test_account_equity_reconciliation_records_unavailable_snapshot() -> None:
    factory = _session_factory()
    sent: list[str] = []
    queue = _alert_queue(sent)
    worker = AccountEquityReconciliationWorker(
        session_factory=factory,
        client=FakeAccountClient([None]),
        alert_queue=queue,
        drift_threshold_usd=25.0,
        drift_threshold_pct=5.0,
    )

    summary = worker.reconcile_once(asset="USDT")

    queue.stop(drain=True)
    with session_scope(factory) as session:
        snapshots = session.scalars(select(AccountSnapshotModel)).all()
        event = session.scalar(select(RiskEventModel))

    assert summary.errors == ["Exchange account snapshot was unavailable"]
    assert snapshots == []
    assert event is not None
    assert event.event_type == "account_snapshot_unavailable"
    assert any("[WARNING] Exchange account snapshot was unavailable" in message for message in sent)


def test_binance_client_normalizes_futures_account_snapshot() -> None:
    client = BinanceFuturesClient.__new__(BinanceFuturesClient)
    client._client = FakeBinanceApi()
    client._symbol_info_cache = {}

    snapshot = client.get_account_snapshot("USDT")

    assert snapshot is not None
    assert snapshot.asset == "USDT"
    assert snapshot.wallet_balance == 1000.50
    assert snapshot.unrealized_pnl == 5.25
    assert snapshot.margin_balance == 1005.75
    assert snapshot.available_balance == 900.00
    assert snapshot.max_withdraw_amount == 850.00
    assert snapshot.event_time == datetime(2026, 1, 1, tzinfo=timezone.utc)
