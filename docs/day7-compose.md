# Day 7 Compose Verification

Run the local production-style stack:

```powershell
docker compose up -d --build
```

Services:

- Backend API: http://localhost:8000
- Frontend dashboard: http://localhost:8080
- Postgres: localhost:15432
- Redis: localhost:16379

The compose stack uses:

- `DATABASE_URL=postgresql+psycopg://trading_bot:trading_bot@postgres:5432/trading_bot`
- `REDIS_URL=redis://redis:6379/0`
- `API_TOKEN=` for local compose browser usability. Set `API_TOKEN` in an override file or deployment environment before exposing the API.

Check status:

```powershell
docker compose ps
docker compose config
```

Stop the stack:

```powershell
docker compose down
```
