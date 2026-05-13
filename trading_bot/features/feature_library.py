"""Vectorized feature generation with lookahead-safe defaults."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.analytics.regime import calculate_adx


DEFAULT_FEATURE_VERSION = "v1"


def build_feature_frame(candles: pd.DataFrame, *, shift_features: bool = True) -> pd.DataFrame:
    """Return OHLCV candles with quant research features.

    When ``shift_features`` is true, derived feature columns are shifted one bar
    so a signal generated at candle ``t`` only sees information available after
    candle ``t - 1`` closed.
    """
    _require_columns(candles, ["time", "open", "high", "low", "close", "volume"])
    df = candles.copy().sort_values("time").reset_index(drop=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = df[column].astype(float)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    df["return_1"] = close.pct_change()
    times = pd.to_datetime(df["time"], utc=True)
    df["day_of_week"] = times.dt.dayofweek
    df["hour_of_day"] = times.dt.hour
    df["log_return_1"] = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan)
    df["rolling_volatility_20"] = df["log_return_1"].rolling(20, min_periods=5).std()
    df["atr_14"] = _atr(df, window=14)
    df["rsi_14"] = _rsi(close, window=14)
    df["ema_12"] = close.ewm(span=12, adjust=False).mean()
    df["ema_26"] = close.ewm(span=26, adjust=False).mean()
    df["ema_50"] = close.ewm(span=50, adjust=False).mean()
    df["ema_200"] = close.ewm(span=200, adjust=False).mean()
    df["sma_20"] = close.rolling(20, min_periods=5).mean()
    df["sma_50"] = close.rolling(50, min_periods=10).mean()
    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    bb_mid = df["sma_20"]
    bb_std = close.rolling(20, min_periods=5).std()
    df["bb_mid"] = bb_mid
    df["bb_upper"] = bb_mid + (2.0 * bb_std)
    df["bb_lower"] = bb_mid - (2.0 * bb_std)
    df["bb_width_pct"] = ((df["bb_upper"] - df["bb_lower"]) / bb_mid.replace(0, np.nan)) * 100.0
    df["vwap"] = _vwap(df)
    volume_ma = volume.rolling(20, min_periods=5).mean()
    df["volume_ratio_20"] = volume / volume_ma.replace(0, np.nan)
    df["momentum_10"] = close.pct_change(10)
    df["price_zscore_20"] = (close - bb_mid) / bb_std.replace(0, np.nan)
    df["high_low_range_pct"] = ((high - low) / close.replace(0, np.nan)) * 100.0
    df["adx_14"] = calculate_adx(df, window=14)
    df["trend_strength"] = (df["ema_50"] - df["ema_200"]) / close.replace(0, np.nan)
    df["volatility_percentile_100"] = _rolling_percentile(df["rolling_volatility_20"], window=100)
    df["spread_proxy_bps"] = ((high - low) / close.replace(0, np.nan)) * 10_000.0
    df["donchian_high_20"] = high.rolling(20, min_periods=20).max()
    df["donchian_low_20"] = low.rolling(20, min_periods=20).min()

    feature_columns = [
        column
        for column in df.columns
        if column not in candles.columns and column not in {"day_of_week", "hour_of_day"}
    ]
    if shift_features:
        df.loc[:, feature_columns] = df.loc[:, feature_columns].shift(1)
    return df


def feature_payload(row: pd.Series) -> dict[str, object]:
    """Return JSON-safe features from a DataFrame row."""
    payload: dict[str, object] = {}
    for key, value in row.items():
        if key in {"time", "open", "high", "low", "close", "volume"}:
            continue
        if pd.isna(value):
            continue
        if isinstance(value, (np.integer, int)):
            payload[str(key)] = int(value)
        elif isinstance(value, (np.floating, float)):
            payload[str(key)] = float(value)
        else:
            payload[str(key)] = str(value)
    return payload


def _require_columns(candles: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in candles.columns]
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")


def _atr(candles: pd.DataFrame, *, window: int) -> pd.Series:
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=window).mean()


def _rsi(close: pd.Series, *, window: int) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.rolling(window, min_periods=window).mean()
    avg_loss = losses.rolling(window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _vwap(candles: pd.DataFrame) -> pd.Series:
    typical = (candles["high"] + candles["low"] + candles["close"]) / 3.0
    cumulative_volume = candles["volume"].cumsum().replace(0, np.nan)
    return (typical * candles["volume"]).cumsum() / cumulative_volume


def _rolling_percentile(series: pd.Series, *, window: int) -> pd.Series:
    def percentile(values: pd.Series) -> float:
        latest = values.iloc[-1]
        if pd.isna(latest):
            return float("nan")
        return float((values <= latest).mean())

    return series.rolling(window, min_periods=max(10, window // 5)).apply(percentile, raw=False)
