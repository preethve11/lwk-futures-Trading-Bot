# Database Migrations

Alembic is the production migration path for the trading platform.

Local development still defaults to SQLAlchemy `Base.metadata.create_all` for convenience. Production deployments should run migrations explicitly and disable automatic table creation.

## Commands

```powershell
py main.py db-upgrade --revision head
py main.py db-current
```

The commands use `DATABASE_URL` from the environment or `.env`.

## Production Settings

Use:

```env
DATABASE_URL=postgresql+psycopg://...
DATABASE_AUTO_CREATE_TABLES=false
```

Then run:

```bash
python main.py db-upgrade --revision head
```

before starting long-running API or trading services.

## Alembic Files

- `alembic.ini`: Alembic configuration.
- `migrations/env.py`: loads `app.persistence.models.Base.metadata`.
- `migrations/script.py.mako`: revision template.
- `migrations/versions/20260506_0001_initial_schema.py`: baseline schema for the current platform.

The older raw SQL files in `migrations/` are retained as historical transition scripts from the pre-Alembic phase. New schema changes should use Alembic revisions under `migrations/versions/`.

## Creating A New Revision

After editing SQLAlchemy models:

```powershell
$env:DATABASE_URL="sqlite:///./pytest_tmp/alembic_autogen.db"
py -m alembic revision --autogenerate -m "describe change"
Remove-Item Env:DATABASE_URL
```

Review the generated revision manually before committing it.

