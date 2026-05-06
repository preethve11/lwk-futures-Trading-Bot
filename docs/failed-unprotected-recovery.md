# Failed Unprotected Recovery

`FAILED_UNPROTECTED` means an entry may exist without verified stop-loss and take-profit protection. The recovery worker is a one-shot operator command that reloads those persisted orders, checks exchange open orders, and emergency-closes positions that remain unsafe.

## Command

```powershell
py main.py recover-unprotected --config config.yaml --limit 100
```

The command requires Binance API credentials in the selected configuration or environment. It uses the same non-blocking alert queue and emergency-close path as the live reconciliation worker.

## Recovery Behavior

- Loads orders where `state = FAILED_UNPROTECTED` or `requires_manual_review = true`.
- Skips already protected orders and orders that already have an `emergency_close_order_id`.
- Verifies stop-loss and take-profit orders still exist on Binance.
- Marks the order `PROTECTED` if protection is found.
- Submits a reduce-only emergency market close if protection is still missing after retries.
- Writes `risk_events` with `failed_unprotected_recovery_*` event types for auditability.
- Emits `EMERGENCY` alerts for missing quantity, invalid side, and emergency close actions.

## Manual Review Cases

The worker does not attempt an emergency close if the persisted order is missing a valid side or quantity. Those records remain manual-review items because closing with incomplete local state could close the wrong exposure.
