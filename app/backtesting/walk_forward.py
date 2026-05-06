"""Walk-forward strategy parameter optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal, Mapping, cast

import optuna
import pandas as pd

from app.backtesting.multi_symbol import metrics_to_dict
from app.core.config import Settings
from app.strategies.registry import create_default_strategy_registry
from trading_bot.analytics.metrics import PerformanceMetrics, compute_metrics
from trading_bot.backtesting.engine import BacktestEngine, BacktestResult
from trading_bot.core.types import Trade
from trading_bot.risk.manager import RiskManager

ObjectiveName = Literal["sharpe", "sortino", "total_return", "profit_factor", "win_rate"]


@dataclass(frozen=True)
class StrategyParameterSet:
    """Optimizable parameters for the EMA/RSI/VWAP strategy."""

    ema_fast: int
    ema_slow: int
    rsi_len: int
    atr_len: int
    atr_stop_mult: float
    atr_tp_mult: float
    vol_mult: float
    vol_ma_len: int
    vwap_window: int
    rsi_long_min: float
    rsi_short_max: float
    cooldown_candles: int

    def to_settings_update(self) -> dict[str, int | float]:
        return {
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "rsi_len": self.rsi_len,
            "atr_len": self.atr_len,
            "atr_stop_mult": self.atr_stop_mult,
            "atr_tp_mult": self.atr_tp_mult,
            "vol_mult": self.vol_mult,
            "vol_ma_len": self.vol_ma_len,
            "vwap_window": self.vwap_window,
            "rsi_long_min": self.rsi_long_min,
            "rsi_short_max": self.rsi_short_max,
            "cooldown_candles": self.cooldown_candles,
        }

    def to_dict(self) -> dict[str, int | float]:
        return self.to_settings_update()


@dataclass(frozen=True)
class WalkForwardWindow:
    """One train/validation split."""

    index: int
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    train_rows: int
    validation_rows: int

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "validation_start": self.validation_start.isoformat(),
            "validation_end": self.validation_end.isoformat(),
            "train_rows": self.train_rows,
            "validation_rows": self.validation_rows,
        }


@dataclass(frozen=True)
class WalkForwardWindowResult:
    """Optimization and out-of-sample validation result for one split."""

    window: WalkForwardWindow
    best_params: StrategyParameterSet
    train_score: float
    validation_score: float
    overfit_score: float
    validation_metrics: PerformanceMetrics
    validation_total_pnl: float
    validation_trades: int

    def to_dict(self) -> dict[str, object]:
        return {
            "window": self.window.to_dict(),
            "best_params": self.best_params.to_dict(),
            "train_score": _json_number(self.train_score),
            "validation_score": _json_number(self.validation_score),
            "overfit_score": _json_number(self.overfit_score),
            "validation_total_pnl": _json_number(self.validation_total_pnl),
            "validation_trades": self.validation_trades,
            "validation_metrics": metrics_to_dict(self.validation_metrics),
        }


@dataclass(frozen=True)
class WalkForwardAggregate:
    """Aggregate out-of-sample performance across all validation windows."""

    initial_capital: float
    final_capital: float
    total_pnl: float
    total_trades: int
    metrics: PerformanceMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_pnl": _json_number(self.total_pnl),
            "total_trades": self.total_trades,
            "metrics": metrics_to_dict(self.metrics),
        }


@dataclass(frozen=True)
class WalkForwardOptimizationReport:
    """Serializable walk-forward optimization report."""

    strategy_name: str
    symbol: str
    timeframe: str
    objective: ObjectiveName
    n_trials: int
    aggregate: WalkForwardAggregate
    windows: list[WalkForwardWindowResult]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "objective": self.objective,
            "n_trials": self.n_trials,
            "aggregate": self.aggregate.to_dict(),
            "windows": [window.to_dict() for window in self.windows],
        }


class WalkForwardOptimizer:
    """Optimize strategy parameters on rolling train windows and validate out of sample."""

    def __init__(
        self,
        settings: Settings,
        *,
        train_size: int,
        validation_size: int,
        step_size: int,
        n_trials: int,
        objective: ObjectiveName = "sharpe",
        random_seed: int = 42,
    ) -> None:
        if train_size <= 0:
            raise ValueError("train_size must be greater than zero")
        if validation_size <= 0:
            raise ValueError("validation_size must be greater than zero")
        if step_size <= 0:
            raise ValueError("step_size must be greater than zero")
        if n_trials <= 0:
            raise ValueError("n_trials must be greater than zero")
        self.settings = settings
        self.train_size = train_size
        self.validation_size = validation_size
        self.step_size = step_size
        self.n_trials = n_trials
        self.objective = objective
        self.random_seed = random_seed

    def run(
        self,
        candles: pd.DataFrame,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> WalkForwardOptimizationReport:
        """Run all train/validation windows and return a portable report."""
        normalized = _normalize_candles(candles)
        splits = self._build_splits(normalized)
        if not splits:
            required = self.train_size + self.validation_size
            raise ValueError(f"Walk-forward optimization requires at least {required} candles")

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        resolved_symbol = (symbol or self.settings.symbol).strip().upper()
        resolved_timeframe = timeframe or self.settings.timeframe
        window_results: list[WalkForwardWindowResult] = []
        validation_trades: list[Trade] = []

        for index, train, validation in splits:
            window = _window_from_split(index, train, validation)
            params, train_score = self._optimize_train_window(train, resolved_symbol)
            validation_result = self._run_backtest(validation, params, resolved_symbol)
            validation_metrics = _require_metrics(validation_result)
            validation_score = _score_metrics(validation_metrics, self.objective)
            validation_total_pnl = sum(trade.pnl for trade in validation_result.trades)
            validation_trades.extend(validation_result.trades)
            window_results.append(
                WalkForwardWindowResult(
                    window=window,
                    best_params=params,
                    train_score=train_score,
                    validation_score=validation_score,
                    overfit_score=_overfit_score(train_score, validation_score),
                    validation_metrics=validation_metrics,
                    validation_total_pnl=validation_total_pnl,
                    validation_trades=len(validation_result.trades),
                )
            )

        aggregate = _aggregate_validation(self.settings.backtest_initial_capital, validation_trades)
        return WalkForwardOptimizationReport(
            strategy_name=self.settings.strategy_name,
            symbol=resolved_symbol,
            timeframe=resolved_timeframe,
            objective=self.objective,
            n_trials=self.n_trials,
            aggregate=aggregate,
            windows=window_results,
        )

    def _build_splits(self, candles: pd.DataFrame) -> list[tuple[int, pd.DataFrame, pd.DataFrame]]:
        splits: list[tuple[int, pd.DataFrame, pd.DataFrame]] = []
        start = 0
        index = 1
        while start + self.train_size + self.validation_size <= len(candles):
            train_end = start + self.train_size
            validation_end = train_end + self.validation_size
            splits.append(
                (
                    index,
                    candles.iloc[start:train_end].reset_index(drop=True),
                    candles.iloc[train_end:validation_end].reset_index(drop=True),
                )
            )
            start += self.step_size
            index += 1
        return splits

    def _optimize_train_window(self, train: pd.DataFrame, symbol: str) -> tuple[StrategyParameterSet, float]:
        sampler = optuna.samplers.TPESampler(seed=self.random_seed)
        study = optuna.create_study(direction="maximize", sampler=sampler)

        def objective_fn(trial: optuna.Trial) -> float:
            params = _suggest_params(trial)
            result = self._run_backtest(train, params, symbol)
            return _score_metrics(_require_metrics(result), self.objective)

        study.optimize(objective_fn, n_trials=self.n_trials, show_progress_bar=False)
        return _params_from_mapping(study.best_params), float(study.best_value)

    def _run_backtest(self, candles: pd.DataFrame, params: StrategyParameterSet, symbol: str) -> BacktestResult:
        trial_settings = self.settings.model_copy(update=params.to_settings_update())
        strategy = create_default_strategy_registry().create(trial_settings.strategy_name, trial_settings)
        engine = BacktestEngine(
            strategy=strategy,
            risk_manager=_create_risk_manager(trial_settings),
            initial_capital=trial_settings.backtest_initial_capital,
            slippage_bps=trial_settings.slippage_bps,
            fee_bps=trial_settings.fee_bps,
        )
        return engine.run(candles.copy(), symbol=symbol)


class WalkForwardReportExporter:
    """Write walk-forward optimization reports to JSON."""

    @staticmethod
    def write_json(report: WalkForwardOptimizationReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2, allow_nan=False)
            handle.write("\n")
        return path


def _suggest_params(trial: optuna.Trial) -> StrategyParameterSet:
    ema_fast = trial.suggest_int("ema_fast", 5, 20)
    return StrategyParameterSet(
        ema_fast=ema_fast,
        ema_slow=trial.suggest_int("ema_slow", ema_fast + 5, 80),
        rsi_len=trial.suggest_int("rsi_len", 5, 21),
        atr_len=trial.suggest_int("atr_len", 7, 28),
        atr_stop_mult=trial.suggest_float("atr_stop_mult", 0.5, 2.0, step=0.1),
        atr_tp_mult=trial.suggest_float("atr_tp_mult", 1.0, 4.0, step=0.1),
        vol_mult=trial.suggest_float("vol_mult", 1.0, 3.0, step=0.1),
        vol_ma_len=trial.suggest_int("vol_ma_len", 10, 40),
        vwap_window=trial.suggest_int("vwap_window", 0, 100, step=5),
        rsi_long_min=trial.suggest_float("rsi_long_min", 45.0, 65.0, step=1.0),
        rsi_short_max=trial.suggest_float("rsi_short_max", 35.0, 55.0, step=1.0),
        cooldown_candles=trial.suggest_int("cooldown_candles", 0, 5),
    )


def _params_from_mapping(params: Mapping[str, int | float]) -> StrategyParameterSet:
    return StrategyParameterSet(
        ema_fast=int(params["ema_fast"]),
        ema_slow=int(params["ema_slow"]),
        rsi_len=int(params["rsi_len"]),
        atr_len=int(params["atr_len"]),
        atr_stop_mult=float(params["atr_stop_mult"]),
        atr_tp_mult=float(params["atr_tp_mult"]),
        vol_mult=float(params["vol_mult"]),
        vol_ma_len=int(params["vol_ma_len"]),
        vwap_window=int(params["vwap_window"]),
        rsi_long_min=float(params["rsi_long_min"]),
        rsi_short_max=float(params["rsi_short_max"]),
        cooldown_candles=int(params["cooldown_candles"]),
    )


def _score_metrics(metrics: PerformanceMetrics, objective: ObjectiveName) -> float:
    if metrics.total_trades == 0:
        return -1_000_000.0
    if objective == "sharpe":
        return _finite(metrics.sharpe_ratio)
    if objective == "sortino":
        return _finite(metrics.sortino_ratio)
    if objective == "total_return":
        return _finite(metrics.total_return_pct)
    if objective == "profit_factor":
        return min(_finite(metrics.profit_factor), 100.0)
    if objective == "win_rate":
        return _finite(metrics.win_rate)
    raise ValueError(f"Unsupported objective: {objective}")


def _aggregate_validation(initial_capital: float, trades: list[Trade]) -> WalkForwardAggregate:
    ordered_trades = sorted(trades, key=lambda trade: trade.exit_time)
    equity_curve = [initial_capital]
    for trade in ordered_trades:
        equity_curve.append(equity_curve[-1] + trade.pnl)
    pnls = [trade.pnl for trade in ordered_trades]
    metrics = compute_metrics(pnls, cumulative_returns=[value / initial_capital for value in equity_curve])
    return WalkForwardAggregate(
        initial_capital=initial_capital,
        final_capital=equity_curve[-1],
        total_pnl=equity_curve[-1] - initial_capital,
        total_trades=len(ordered_trades),
        metrics=metrics,
    )


def _normalize_candles(candles: pd.DataFrame) -> pd.DataFrame:
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Candles are missing required columns: {', '.join(sorted(missing))}")
    normalized = candles.copy()
    normalized["time"] = pd.to_datetime(normalized["time"], utc=True)
    normalized = normalized.sort_values("time").reset_index(drop=True)
    for column in ["open", "high", "low", "close", "volume"]:
        normalized[column] = normalized[column].astype(float)
    return normalized


def _window_from_split(index: int, train: pd.DataFrame, validation: pd.DataFrame) -> WalkForwardWindow:
    return WalkForwardWindow(
        index=index,
        train_start=_to_datetime(train.iloc[0]["time"]),
        train_end=_to_datetime(train.iloc[-1]["time"]),
        validation_start=_to_datetime(validation.iloc[0]["time"]),
        validation_end=_to_datetime(validation.iloc[-1]["time"]),
        train_rows=len(train),
        validation_rows=len(validation),
    )


def _create_risk_manager(settings: Settings) -> RiskManager:
    return RiskManager(
        risk_per_trade_usd=settings.risk_per_trade_usd,
        max_daily_loss_usd=settings.max_daily_loss_usd,
        max_drawdown_pct=settings.max_drawdown_pct,
        min_notional=settings.min_notional,
        max_position_pct_capital=settings.max_position_pct_capital,
        min_risk_reward=settings.min_risk_reward,
        use_atr_position_cap=settings.use_atr_position_cap,
        trailing_stop_atr_mult=settings.trailing_stop_atr_mult,
        symbol_info=None,
    )


def _require_metrics(result: BacktestResult) -> PerformanceMetrics:
    if result.metrics is None:
        raise ValueError("Backtest metrics were not produced")
    return result.metrics


def _overfit_score(train_score: float, validation_score: float) -> float:
    if train_score <= -999_999.0 and validation_score <= -999_999.0:
        return 0.0
    return max(0.0, _finite(train_score) - _finite(validation_score))


def _finite(value: float) -> float:
    if value != value:
        return 0.0
    if value == float("inf"):
        return 100.0
    if value == float("-inf"):
        return -100.0
    return value


def _json_number(value: float) -> float | None:
    if value != value or value in {float("inf"), float("-inf")}:
        return None
    return value


def _to_datetime(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return cast(datetime, timestamp.to_pydatetime())
