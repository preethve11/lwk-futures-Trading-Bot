"""Timeframe string to minutes conversion."""

def timeframe_minutes(tf: str) -> int:
    """Convert Binance-style timeframe (e.g. '5m', '1h', '1d') to minutes."""
    tf = tf.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("d"):
        return int(tf[:-1]) * 60 * 24
    raise ValueError(f"Unsupported timeframe: {tf}")
