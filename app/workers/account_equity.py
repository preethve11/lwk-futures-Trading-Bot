"""Account wallet/equity reconciliation from live exchange account state."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from app.persistence.database import SessionFactory, session_scope
from app.persistence.models import AccountSnapshotModel
from app.persistence.repositories import AccountSnapshotRepository, RiskEventRepository
from trading_bot.execution.base import AccountSnapshot, ExecutionClient
from trading_bot.utils.alerts import AlertQueue, AlertSeverity

logger = logging.getLogger("trading_bot.account_equity")


@dataclass(frozen=True)
class AccountEquitySummary:
    """Summary of one account/equity reconciliation pass."""

    asset: str
    snapshot_id: int | None = None
    previous_equity: float | None = None
    current_equity: float | None = None
    equity_delta: float | None = None
    equity_delta_pct: float | None = None
    wallet_delta: float | None = None
    drift_detected: bool = False
    drift_event_id: int | None = None
    errors: list[str] = field(default_factory=list)


class AccountEquityReconciliationWorker:
    """Poll exchange wallet state, persist equity curve points, and alert on drift."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        client: ExecutionClient,
        alert_queue: AlertQueue,
        drift_threshold_usd: float,
        drift_threshold_pct: float,
    ) -> None:
        self.session_factory = session_factory
        self.client = client
        self.alert_queue = alert_queue
        self.drift_threshold_usd = drift_threshold_usd
        self.drift_threshold_pct = drift_threshold_pct

    def reconcile_once(
        self,
        *,
        asset: str = "USDT",
        bot_session_id: int | None = None,
    ) -> AccountEquitySummary:
        requested_asset = asset.upper()
        previous = self._latest_snapshot(requested_asset)
        snapshot = self.client.get_account_snapshot(requested_asset)
        if snapshot is None:
            message = "Exchange account snapshot was unavailable"
            self._record_unavailable_event(asset=requested_asset, bot_session_id=bot_session_id, reason=message)
            return AccountEquitySummary(asset=requested_asset, errors=[message])

        persisted = self._persist_snapshot(snapshot, bot_session_id=bot_session_id)
        drift = self._detect_drift(previous, snapshot)
        drift_event_id = None
        if drift is not None:
            drift_event_id = self._record_drift_event(
                asset=requested_asset,
                bot_session_id=bot_session_id,
                snapshot_id=persisted.id,
                drift=drift,
                previous=previous,
                current=snapshot,
            )

        summary = AccountEquitySummary(
            asset=requested_asset,
            snapshot_id=persisted.id,
            previous_equity=previous.margin_balance if previous is not None else None,
            current_equity=snapshot.equity,
            equity_delta=drift.equity_delta if drift is not None else self._equity_delta(previous, snapshot),
            equity_delta_pct=drift.equity_delta_pct if drift is not None else self._equity_delta_pct(previous, snapshot),
            wallet_delta=drift.wallet_delta if drift is not None else self._wallet_delta(previous, snapshot),
            drift_detected=drift is not None,
            drift_event_id=drift_event_id,
        )
        logger.info(
            "Account equity reconciliation completed",
            extra={
                "asset": summary.asset,
                "snapshot_id": summary.snapshot_id,
                "current_equity": summary.current_equity,
                "equity_delta": summary.equity_delta,
                "equity_delta_pct": summary.equity_delta_pct,
                "drift_detected": summary.drift_detected,
            },
        )
        return summary

    def _latest_snapshot(self, asset: str) -> AccountSnapshotModel | None:
        with session_scope(self.session_factory) as session:
            return AccountSnapshotRepository(session).latest(asset=asset)

    def _persist_snapshot(
        self,
        snapshot: AccountSnapshot,
        *,
        bot_session_id: int | None,
    ) -> AccountSnapshotModel:
        with session_scope(self.session_factory) as session:
            return AccountSnapshotRepository(session).create_from_snapshot(snapshot, bot_session_id=bot_session_id)

    def _detect_drift(
        self,
        previous: AccountSnapshotModel | None,
        current: AccountSnapshot,
    ) -> AccountBalanceDrift | None:
        if previous is None:
            return None
        equity_delta = self._equity_delta(previous, current) or 0.0
        wallet_delta = self._wallet_delta(previous, current) or 0.0
        equity_delta_pct = self._equity_delta_pct(previous, current) or 0.0
        if not self._exceeds_threshold(equity_delta, equity_delta_pct, wallet_delta):
            return None
        return AccountBalanceDrift(
            equity_delta=equity_delta,
            equity_delta_pct=equity_delta_pct,
            wallet_delta=wallet_delta,
            severity=self._drift_severity(equity_delta, equity_delta_pct, wallet_delta),
        )

    def _exceeds_threshold(self, equity_delta: float, equity_delta_pct: float, wallet_delta: float) -> bool:
        usd_triggered = self.drift_threshold_usd > 0 and (
            abs(equity_delta) >= self.drift_threshold_usd or abs(wallet_delta) >= self.drift_threshold_usd
        )
        pct_triggered = self.drift_threshold_pct > 0 and abs(equity_delta_pct) >= self.drift_threshold_pct
        return usd_triggered or pct_triggered

    def _drift_severity(
        self,
        equity_delta: float,
        equity_delta_pct: float,
        wallet_delta: float,
    ) -> AlertSeverity:
        critical_usd = self.drift_threshold_usd > 0 and (
            abs(equity_delta) >= self.drift_threshold_usd * 2
            or abs(wallet_delta) >= self.drift_threshold_usd * 2
        )
        critical_pct = self.drift_threshold_pct > 0 and abs(equity_delta_pct) >= self.drift_threshold_pct * 2
        if critical_usd or critical_pct:
            return AlertSeverity.CRITICAL
        return AlertSeverity.WARNING

    def _record_drift_event(
        self,
        *,
        asset: str,
        bot_session_id: int | None,
        snapshot_id: int,
        drift: AccountBalanceDrift,
        previous: AccountSnapshotModel | None,
        current: AccountSnapshot,
    ) -> int:
        reason = "Account balance drift detected from exchange wallet state"
        payload = {
            "asset": asset,
            "snapshot_id": snapshot_id,
            "previous": self._snapshot_model_payload(previous),
            "current": self._account_snapshot_payload(current),
            "equity_delta": drift.equity_delta,
            "equity_delta_pct": drift.equity_delta_pct,
            "wallet_delta": drift.wallet_delta,
            "threshold_usd": self.drift_threshold_usd,
            "threshold_pct": self.drift_threshold_pct,
        }
        self.alert_queue.enqueue(
            drift.severity,
            reason,
            {
                "asset": asset,
                "equity_delta": round(drift.equity_delta, 8),
                "equity_delta_pct": round(drift.equity_delta_pct, 4),
                "wallet_delta": round(drift.wallet_delta, 8),
            },
        )
        with session_scope(self.session_factory) as session:
            event = RiskEventRepository(session).create(
                symbol=asset,
                event_type="account_balance_drift",
                severity=drift.severity.value,
                reason=reason,
                bot_session_id=bot_session_id,
                payload=payload,
            )
            return event.id

    def _record_unavailable_event(
        self,
        *,
        asset: str,
        bot_session_id: int | None,
        reason: str,
    ) -> None:
        self.alert_queue.enqueue(AlertSeverity.WARNING, reason, {"asset": asset})
        with session_scope(self.session_factory) as session:
            RiskEventRepository(session).create(
                symbol=asset,
                event_type="account_snapshot_unavailable",
                severity=AlertSeverity.WARNING.value,
                reason=reason,
                bot_session_id=bot_session_id,
                payload={"asset": asset},
            )

    def _equity_delta(
        self,
        previous: AccountSnapshotModel | None,
        current: AccountSnapshot,
    ) -> float | None:
        if previous is None:
            return None
        return float(current.equity) - previous.margin_balance

    def _wallet_delta(
        self,
        previous: AccountSnapshotModel | None,
        current: AccountSnapshot,
    ) -> float | None:
        if previous is None:
            return None
        return float(current.wallet_balance) - previous.wallet_balance

    def _equity_delta_pct(
        self,
        previous: AccountSnapshotModel | None,
        current: AccountSnapshot,
    ) -> float | None:
        if previous is None or previous.margin_balance == 0:
            return None
        return ((float(current.equity) - previous.margin_balance) / abs(previous.margin_balance)) * 100

    def _snapshot_model_payload(self, snapshot: AccountSnapshotModel | None) -> dict[str, object]:
        if snapshot is None:
            return {}
        return {
            "id": snapshot.id,
            "asset": snapshot.asset,
            "wallet_balance": snapshot.wallet_balance,
            "unrealized_pnl": snapshot.unrealized_pnl,
            "margin_balance": snapshot.margin_balance,
            "available_balance": snapshot.available_balance,
            "event_time": snapshot.event_time.isoformat(),
        }

    def _account_snapshot_payload(self, snapshot: AccountSnapshot) -> dict[str, object]:
        return {
            "asset": snapshot.asset,
            "wallet_balance": snapshot.wallet_balance,
            "unrealized_pnl": snapshot.unrealized_pnl,
            "margin_balance": snapshot.margin_balance,
            "available_balance": snapshot.available_balance,
            "event_time": snapshot.event_time.isoformat() if snapshot.event_time is not None else None,
        }


@dataclass(frozen=True)
class AccountBalanceDrift:
    """Detected account balance drift details."""

    equity_delta: float
    equity_delta_pct: float
    wallet_delta: float
    severity: AlertSeverity
