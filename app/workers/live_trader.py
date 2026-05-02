"""Live trading worker orchestration."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.core.config import Settings
from app.core.security import assert_live_trading_allowed
from app.strategies.registry import StrategyRegistry, create_default_strategy_registry
from trading_bot.core.types import Signal
from trading_bot.execution.binance_futures import BinanceFuturesClient
from trading_bot.risk.manager import RiskManager
from trading_bot.utils.telegram import send_telegram
from trading_bot.utils.timeframes import timeframe_minutes


class LiveTrader:
    """Coordinates strategy, risk, execution, and live-loop state."""

    def __init__(
        self,
        settings: Settings,
        *,
        strategy_registry: StrategyRegistry | None = None,
        client: BinanceFuturesClient | None = None,
    ) -> None:
        self.settings = settings
        self.strategy_registry = strategy_registry or create_default_strategy_registry()
        self.client = client
        self.logger = logging.getLogger("trading_bot.live_trader")

    def run_forever(self) -> int:
        """Run the live trading loop until interrupted."""
        assert_live_trading_allowed(self.settings)
        client = self.client or self._create_client()
        client.set_leverage(self.settings.symbol, self.settings.leverage)

        symbol_info = client.get_symbol_info(self.settings.symbol)
        risk_manager = self._create_risk_manager(symbol_info)
        strategy = self.strategy_registry.create(self.settings.strategy_name, self.settings)
        cooldown_s = timeframe_minutes(self.settings.timeframe) * 60
        last_signal_ts = 0.0
        last_hourly = datetime.now(timezone.utc)

        send_telegram(
            (
                f"Trading bot starting | {self.settings.symbol} | "
                f"testnet={self.settings.use_testnet} | leverage={self.settings.leverage}x"
            ),
            self.settings.telegram_bot_token,
            self.settings.telegram_chat_id,
        )

        while True:
            try:
                daily_loss = self._sync_daily_loss(client, risk_manager)
                if not risk_manager.check_daily_loss():
                    self.logger.warning("Daily loss cap reached", extra={"symbol": self.settings.symbol})
                    time.sleep(60)
                    continue

                position = client.get_open_position(self.settings.symbol)
                if position and position.quantity > 0:
                    self.logger.info("Position open, waiting", extra={"symbol": self.settings.symbol})
                    time.sleep(5)
                    if (datetime.now(timezone.utc) - last_hourly) >= timedelta(minutes=55):
                        send_telegram(
                            (
                                f"Hourly | {self.settings.symbol} | Open pos: {position.quantity} "
                                f"@ {position.entry_price} | Daily loss: ${daily_loss:.2f}"
                            ),
                            self.settings.telegram_bot_token,
                            self.settings.telegram_chat_id,
                        )
                        last_hourly = datetime.now(timezone.utc)
                    continue

                if time.time() - last_signal_ts < cooldown_s:
                    time.sleep(1)
                    continue

                df = client.get_klines(self.settings.symbol, self.settings.timeframe, limit=300)
                df = strategy.compute_indicators(df)
                raw = strategy.get_signal(df)
                if raw is None:
                    time.sleep(1)
                    continue

                prev = df.iloc[-2]
                atr = float(prev["atr"]) if not pd.isna(prev.get("atr")) else 0.0
                result = risk_manager.validate_signal(
                    raw.entry_price,
                    raw.stop_price,
                    raw.take_profit_price,
                    raw.side,
                    atr,
                    None,
                )
                if not result.allowed or result.quantity <= 0:
                    self.logger.info(
                        "Signal rejected by risk manager",
                        extra={"symbol": self.settings.symbol, "reason": result.reason},
                    )
                    time.sleep(1)
                    continue

                signal = Signal(
                    side=raw.side,
                    entry_price=raw.entry_price,
                    stop_price=raw.stop_price,
                    take_profit_price=raw.take_profit_price,
                    quantity=result.quantity,
                    timestamp=raw.timestamp,
                    metadata=raw.metadata,
                )
                order_result = client.place_market_and_sl_tp(self.settings.symbol, signal)
                if order_result.success:
                    last_signal_ts = time.time()
                    send_telegram(
                        (
                            f"Entry {raw.side.value} {self.settings.symbol} qty={result.quantity} "
                            f"entry={order_result.avg_price or raw.entry_price:.3f} "
                            f"SL={raw.stop_price:.3f} TP={raw.take_profit_price:.3f}"
                        ),
                        self.settings.telegram_bot_token,
                        self.settings.telegram_chat_id,
                    )
                time.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("Shutdown by user")
                send_telegram(
                    "Trading bot stopped (user request).",
                    self.settings.telegram_bot_token,
                    self.settings.telegram_chat_id,
                )
                break
            except Exception as exc:
                self.logger.exception("Live loop error", extra={"error": str(exc)})
                time.sleep(5)
        return 0

    def _create_client(self) -> BinanceFuturesClient:
        if not self.settings.active_binance_api_key or not self.settings.active_binance_api_secret:
            raise RuntimeError("Missing active Binance API key or secret")
        return BinanceFuturesClient(
            self.settings.active_binance_api_key,
            self.settings.active_binance_api_secret,
            testnet=self.settings.use_testnet,
        )

    def _create_risk_manager(self, symbol_info: dict[str, object] | None) -> RiskManager:
        return RiskManager(
            risk_per_trade_usd=self.settings.risk_per_trade_usd,
            max_daily_loss_usd=self.settings.max_daily_loss_usd,
            max_drawdown_pct=self.settings.max_drawdown_pct,
            min_notional=self.settings.min_notional,
            max_position_pct_capital=self.settings.max_position_pct_capital,
            min_risk_reward=self.settings.min_risk_reward,
            use_atr_position_cap=self.settings.use_atr_position_cap,
            trailing_stop_atr_mult=self.settings.trailing_stop_atr_mult,
            symbol_info=symbol_info,
        )

    def _sync_daily_loss(self, client: BinanceFuturesClient, risk_manager: RiskManager) -> float:
        trades = client.fetch_recent_trades(self.settings.symbol, limit=500)
        now_date = datetime.now(timezone.utc).date()
        day_start_ts = int(datetime.combine(now_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
        realized = sum(
            float(trade.get("realizedPnl", 0))
            for trade in trades
            if int(trade.get("time", 0)) >= day_start_ts
        )
        daily_loss = max(0.0, -realized)
        risk_manager.set_daily_loss(daily_loss, now_date)
        return daily_loss
