# Analysis notebooks

Exploratory data analysis against the live Postgres database. Nothing here is
production code - no notebook output should be assumed stable or re-run
automatically.

## Setup

From `backend/`:

```
pip install -r requirements-dev.txt
jupyter lab notebooks/
```

Notebooks connect using the same `DATABASE_URL` env var as the Flask app
(see `app.config.Config`), so point it at whichever database you want to
query (e.g. a local copy, or the real one read-only) before launching.
