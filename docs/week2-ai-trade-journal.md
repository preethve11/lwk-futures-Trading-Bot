# Week 2 AI Trade Journal

The AI trade journal is advisory-only infrastructure for explaining signal decisions after the trading system has already accepted or rejected them.

It stores reports in `ai_reports` and exposes them through:

```http
GET /ai-reports
GET /ai-reports?symbol=ZECUSDT
GET /ai-reports?event_type=signal_rejected
```

Enable it with environment variables:

```env
OPENAI_API_KEY=...
AI_JOURNAL_ENABLED=true
AI_JOURNAL_MODEL=gpt-4.1-mini
AI_JOURNAL_TIMEOUT_SECONDS=15
AI_JOURNAL_MAX_QUEUE_SIZE=1000
```

Safety boundaries:

- The AI journal queue is non-blocking for the live trading loop.
- OpenAI network calls happen on a background worker.
- The AI receives signal context, risk state, market-regime snapshot, and outcome.
- The AI can only write an advisory journal row to `ai_reports`.
- The AI is never given access to execution clients, order repositories, risk-state mutation methods, or live trading controls.
- The prompt explicitly forbids trade instructions and state mutation.

The current OpenAI client uses the Responses API endpoint configured by `OPENAI_BASE_URL`, defaulting to `https://api.openai.com/v1`.
