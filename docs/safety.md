# Safety Guide

Crypto futures trading can lose money quickly. This project is designed with guardrails, but guardrails are not a guarantee. Use testnet first.

## Non-Negotiable Rules

- Keep `USE_TESTNET=true` until testnet order placement, reconciliation, kill switch, dashboard controls, alerts, and manual recovery have all been exercised.
- Keep `CONFIRM_LIVE_TRADING=false` unless intentionally testing mainnet with real funds.
- Start with very small `RISK_PER_TRADE_USD`.
- Never expose the API without `API_TOKEN`.
- Never expose `/metrics` publicly without a private network, token, or reverse-proxy auth.
- Never allow AI output to place orders or mutate trading state.
- Verify open positions directly on Binance after every incident.

## Live Trading Guard

Mainnet requires both:

```env
USE_TESTNET=false
CONFIRM_LIVE_TRADING=true
```

This two-step confirmation is intentional. Do not remove it.

## Risk Controls

The bot supports:

- fixed dollar risk per trade
- max daily loss lock
- max drawdown lock
- manual pause
- API/dashboard kill switch
- min notional enforcement
- min risk-reward enforcement
- optional ATR volatility position cap

The kill switch blocks new trading decisions. It does not replace checking the exchange directly for already-open positions.

## Order Protection

After a market entry, the reconciliation worker checks for stop-loss and take-profit protection. If protection cannot be verified, the system can:

- retry verification
- persist a critical risk event
- mark the order as requiring manual review
- attempt emergency market close
- emit critical or emergency alerts

Operators must still inspect Binance after any `FAILED_UNPROTECTED` or manual-review state.

## AI Boundary

The AI trade journal is advisory-only:

- It receives context after a signal is taken or rejected.
- It can write an explanatory report row.
- It does not receive execution clients.
- It cannot call order, risk-state mutation, or live control methods.
- It must not recommend placing, modifying, or cancelling orders.

## Incident Checklist

1. Trigger the kill switch from the dashboard or `POST /risk/kill-switch`.
2. Check Binance for open positions and open reduce-only orders.
3. Review latest `risk_events`, orders requiring manual review, and Telegram alerts.
4. Export relevant logs and database rows before restart.
5. Close or protect positions manually if needed.
6. Restart services only after the exchange state is understood.

## Production Readiness Criteria

Before mainnet:

- CI green on the target branch.
- Testnet trade lifecycle tested end to end.
- Emergency close path tested on testnet.
- Dashboard kill switch tested.
- Alerts tested.
- Prometheus/Grafana running or external monitoring configured.
- Backup plan confirmed.
- Secrets supplied only through env or secret manager.
- API and dashboard behind TLS and access control.

