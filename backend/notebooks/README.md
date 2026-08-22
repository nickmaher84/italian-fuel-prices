# Analysis notebooks

Exploratory data analysis against the read-only DuckDB mirror (not the live
Postgres database). Nothing here is production code - no notebook output should
be assumed stable or re-run automatically.

## Setup

```
cd backend
pip install -r requirements-dev.txt
pip install -e .
jupyter lab notebooks/
```

The `pip install -e .` (using `backend/pyproject.toml`) installs `app` as a
regular editable package in your environment, so `import app...` works from
notebooks no matter where the Jupyter kernel's working directory ends up -
this matters because it's not always the notebook's own folder or even
inside the repo (e.g. PyCharm's built-in Jupyter support runs kernels from
a temp directory outside the project tree entirely).

Each notebook opens the mirror with `Mirror().connect(read_only=True)` (see
`app.services.mirror`), which reads the DuckDB file at `Config.MIRROR_PATH`
(`MIRROR_PATH` env var, default `backend/data/mirror.duckdb`). Build or refresh that
file from Postgres with `Mirror().refresh()` / `Mirror().rebuild()` before
launching. The mirror exposes mirrored `station` and `price_change` tables plus
the `prices_daily_mirror(start_date, end_date)` table macro, which applies the
same forward-fill semantics as the app's `prices_daily()`.

Queries use DuckDB SQL with positional `?` parameters, e.g.
`con.execute(sql, [param, ...]).df()`. List parameters bind against
`WHERE station_id = ANY(?)`.
