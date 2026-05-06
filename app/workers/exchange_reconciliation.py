"""Exchange-led fill reconciliation into the local persistence ledger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import logging

from app.exchange.fills import ExchangeFill, parse_exchange_fill
from app.persistence.database import SessionFactory, session_scope
from app.persistence.repositories import ExchangeFillRepository, TradeRepository
from trading_bot.execution.base import ExecutionClient

logger = logging.getLogger("trading_bot.exchange_reconciliation")


@dataclass(frozen=True)
class ExchangeReconciliationSummary:
    """Summary of one exchange account-trade reconciliation pass."""

    symbol: str
    fetched: int = 0
    fills_created: int = 0
    fills_seen: int = 0
    closed_trades_created: int = 0
    closed_trades_seen: int = 0
    parse_errors: list[str] = field(default_factory=list)


class ExchangeReconciliationWorker:
    """Persist raw Binance fills and idempotent closed-PnL trade events."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def reconcile_recent_trades(
        self,
        client: ExecutionClient,
        *,
        symbol: str,
        bot_session_id: int | None = None,
        limit: int = 500,
    ) -> ExchangeReconciliationSummary:
        raw_fills = client.fetch_recent_trades(symbol, limit=limit)
        return self.reconcile_raw_fills(symbol=symbol, raw_fills=raw_fills, bot_session_id=bot_session_id)

    def reconcile_raw_fills(
        self,
        *,
        symbol: str,
        raw_fills: Sequence[Mapping[str, object]],
        bot_session_id: int | None = None,
    ) -> ExchangeReconciliationSummary:
        parsed_fills, parse_errors = self._parse_fills(symbol, raw_fills)
        fills_created = 0
        fills_seen = 0
        closed_trades_created = 0
        closed_trades_seen = 0

        with session_scope(self.session_factory) as session:
            fill_repository = ExchangeFillRepository(session)
            trade_repository = TradeRepository(session)

            for fill in parsed_fills:
                fill_model, fill_was_created = fill_repository.create_from_fill(
                    fill,
                    bot_session_id=bot_session_id,
                )
                if fill_was_created:
                    fills_created += 1
                else:
                    fills_seen += 1

                trade_model, trade_was_created = trade_repository.create_from_exchange_fill(
                    fill,
                    bot_session_id=bot_session_id,
                )
                if trade_model is not None and fill_model.trade_id is None:
                    fill_model.trade_id = trade_model.id
                if trade_was_created:
                    closed_trades_created += 1
                elif trade_model is not None:
                    closed_trades_seen += 1

        summary = ExchangeReconciliationSummary(
            symbol=symbol,
            fetched=len(raw_fills),
            fills_created=fills_created,
            fills_seen=fills_seen,
            closed_trades_created=closed_trades_created,
            closed_trades_seen=closed_trades_seen,
            parse_errors=parse_errors,
        )
        logger.info(
            "Exchange fill reconciliation completed",
            extra={
                "symbol": symbol,
                "fetched": summary.fetched,
                "fills_created": summary.fills_created,
                "fills_seen": summary.fills_seen,
                "closed_trades_created": summary.closed_trades_created,
                "closed_trades_seen": summary.closed_trades_seen,
                "parse_error_count": len(summary.parse_errors),
            },
        )
        return summary

    def _parse_fills(
        self,
        symbol: str,
        raw_fills: Sequence[Mapping[str, object]],
    ) -> tuple[list[ExchangeFill], list[str]]:
        parsed: list[ExchangeFill] = []
        errors: list[str] = []
        for raw_fill in raw_fills:
            try:
                parsed.append(parse_exchange_fill(raw_fill, fallback_symbol=symbol))
            except ValueError as exc:
                message = str(exc)
                errors.append(message)
                logger.warning("Skipping unparseable exchange fill", extra={"symbol": symbol, "error": message})
        return parsed, errors
