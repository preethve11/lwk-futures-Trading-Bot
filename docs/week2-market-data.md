# Week 2 Market Data Service

The market-data service subscribes to Binance USDT-M futures kline streams and publishes normalized candles into Redis.

Default live trading still uses REST polling:

```env
MARKET_DATA_SOURCE=rest
```

To make the live strategy loop consume Redis-fed klines instead:

```env
MARKET_DATA_SOURCE=redis
REDIS_URL=redis://localhost:6379/0
```

Run the publisher locally:

```powershell
python main.py market-data
```

Run it inside Compose:

```powershell
docker compose --profile market-data up -d --build market-data
```

Redis channels:

- Aggregate: `market_data.kline`
- Symbol/interval: `market_data.kline.ZECUSDT.5m`

Redis history keys:

- `market_data:klines:ZECUSDT:5m`
- `market_data:klines:ZECUSDT:5m:current`

The Redis list stores closed candles. The current key stores the latest open candle update so strategy history is not filled with repeated partial candle updates.

The live strategy loop reads recent OHLCV from Redis only when `MARKET_DATA_SOURCE=redis`; otherwise it continues using the existing REST path.
