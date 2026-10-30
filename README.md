# Revenue Analytics Dashboard

A semantic-aware Mini BI application for CSV data: upload and review fields, build a saved dashboard, then evaluate univariate forecasts on your own data.

## What works now

- Three task-focused workspaces: **Data**, **Visualize**, and **Forecast**.
- CSV validation (CSV only, no empty/header-only data, unique nonblank columns, 10 MB limit).
- Paginated preview, type/role recommendations, confidence, and user overrides.
- Datasets, semantic reviews, cleaned rows and dashboards saved in a database (SQLite by default, PostgreSQL via `DATABASE_URL`) and available again in a new browser.
- Accounts: register, sign in (OAuth2 password flow, JWT Bearer tokens), sign out. Each user sees only their own datasets; admins can access all.
- Data-quality counts and explicit removal of exact duplicates or rows with missing values.
- Semantic-aware drag-and-drop/click-to-assign field wells for Bar, Line, Pie, and Scatter charts.
- SUM, AVERAGE, COUNT, MIN, and MAX aggregation; compatibility feedback; and a saved dashboard per dataset with reorder/remove controls and KPI cards.
- REST API under `/api/v1` (SQLModel tables, `response_model` schemas, 201/204/400/404/413/422 responses), OpenAPI docs, request IDs/timing logs, and API tests on a separate test database.
- Forecast configuration, chronological backtesting, MAE/RMSE comparison and future point predictions from the uploaded target series.

## Architecture

```text
frontend/
  login.html                  Sign in / create an account
  index.html                  Data workspace
  visualize.html              Visualize workspace
  forecast.html               Forecast workspace
  css/style.css
  js/                         API, state, semantic, UI, and page-specific logic
backend/
  main.py                     FastAPI assembly, middleware, /health and /forecast
  config.py                   Environment configuration (origins, upload limit, DATABASE_URL, SECRET_KEY)
  security.py                 bcrypt hashing, JWT, get_current_user (CurrentUser), ownership checks
  database.py                 Engine, create_db_and_tables, get_session (SessionDep)
  db_models.py                SQLModel tables (User, Dataset, Visual) and their API schemas
  routers/auth.py             /api/v1/register, /api/v1/token, /api/v1/me
  models.py                   Forecast request/response contracts
  routers/datasets.py         /api/v1/datasets: upload, list, read, update, delete
  routers/visuals.py          /api/v1/datasets/{id}/visuals and /api/v1/visuals/{id}
  seed.py                     Load sample CSV files into the database for a user
  create_admin.py             Create or promote an admin account from the command line
  services/csv_service.py     CSV parsing and validation
  services/forecast_service.py  Model fitting, chronological validation and forecast
  tests/                      API tests (conftest.py provides an in-memory test database)
```

### Data model

```text
user                      dataset                               visual
  id (PK)                   id (PK)                               id (PK)
  username (unique)         owner_id (FK -> user.id)              dataset_id (FK -> dataset.id)
  hashed_password           filename, rows, columns (JSON)        chart_type, fields (JSON), aggregation
  role (user | admin)       data, raw_data, profiles (JSON)       position
  created_at                semantic_model (JSON)                 created_at
                            created_at, updated_at
```

One user owns many datasets; one dataset has many visuals (deletes cascade). The database is the source of truth; the browser keeps a copy of the active dataset in `sessionStorage` so the three pages can read it after navigation, and every change is saved through the API first. Forecast requests send only the selected date/target pairs to `/forecast`; forecasts are computed on demand and not stored.

### REST API

| Method | URL | Success | Errors |
|---|---|---|---|
| POST | `/api/v1/register` (JSON `username`, `password`) | 201 | 409, 422 |
| POST | `/api/v1/token` (form `username`, `password`) | 200 | 401, 422 |
| GET | `/api/v1/me` | 200 | 401 |
| POST | `/api/v1/datasets` (multipart `file`) | 201 | 400, 413, 422 |
| GET | `/api/v1/datasets?offset=&limit=` | 200 | 422 |
| GET / PATCH / DELETE | `/api/v1/datasets/{dataset_id}` | 200 / 200 / 204 | 400, 404, 422 |
| GET / POST | `/api/v1/datasets/{dataset_id}/visuals` | 200 / 201 | 400, 404, 422 |
| PATCH / DELETE | `/api/v1/visuals/{visual_id}` | 200 / 204 | 404, 422 |
| POST | `/forecast` | 200 | 400, 422 |

Every `/api/v1/datasets` and `/api/v1/visuals` route needs `Authorization: Bearer <token>` (401 without a valid token) and only works on the caller's own datasets (403 otherwise; admins may access all). `/health`, `/forecast` (stateless, stores nothing) and the static pages are public; the pages themselves redirect to `login.html` when nobody is signed in.

### Authentication

- Passwords are stored only as bcrypt hashes (salted, deliberately slow) via `pwdlib`; they must be 8+ characters and at most 72 bytes.
- `POST /api/v1/token` returns a JWT signed with `SECRET_KEY` (HS256) whose payload holds only `sub` (user id) and `exp`. It expires after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30); the user then signs in again.
- `get_current_user` reloads the user from the database on every request, so deleted users are locked out and roles cannot be changed by editing a token.
- The owner of an upload and every user's role are decided by the server, never by the request. Admins are created only with `python -m backend.create_admin USERNAME`.
- The browser keeps the token in `sessionStorage` (cleared when the tab closes or on **Log out**); every page escapes the data it renders. Use HTTPS in production so tokens and passwords are not sent in plain text.

## Run locally

1. Create and activate a Python 3.11+ virtual environment.
2. Install the pinned dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Set a secret key for signing login tokens (the server refuses to start without one). Generate it once and keep it out of Git:

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   $env:SECRET_KEY="paste-the-generated-value"
   ```

   On macOS/Linux use `export SECRET_KEY="..."`.

4. Start the backend from the project root:

   ```powershell
   uvicorn backend.main:app --reload
   ```

   Tables are created on startup in `data/app.db` (git-ignored). Optionally create an admin and load the sample data for them:

   ```powershell
   python -m backend.create_admin admin
   python -m backend.seed --owner admin
   ```

5. Open [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/) in a browser. This serves the frontend from the same FastAPI origin. Create an account (or sign in), upload a CSV or choose a dataset under **Saved datasets**, review the semantic recommendations, then open **Visualize**.

**Upgrading from the version without accounts:** existing tables lack `owner_id`, and the server stops with a message saying so. In development, delete `data/app.db` and restart (saved datasets are lost; upload them again).

API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) and health status at [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health).

## Test

```powershell
python -m pytest backend/tests -q
```

Tests never touch `data/app.db`: `conftest.py` gives every test an empty in-memory SQLite database through `app.dependency_overrides`. To run the same tests on PostgreSQL, point `TEST_DATABASE_URL` at a separate, disposable database (its tables are dropped):

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://app:change-me@localhost:5432/revenue_test"; python -m pytest backend/tests -q
```

`scripts/check_forecast_browser.cjs` provides a browser integration check (Node 22+, isolated Chromium remote-debugging session on port 9228, and a backend on port 8017). It registers a throwaway account, uploads a synthetic 120-row CSV through the UI and checks forecast tables/charts, date order, decimal precision, mobile layout, insufficient-history gating, and API error recovery. Run `node scripts/check_forecast_browser.cjs`; its screenshot goes to the ignored `.tmp-forecast-qa/forecast.png`. The script uses a new tab and does not start/stop the browser or backend.

## Configuration

Copy `.env.example` values into your deployment environment. `ALLOWED_ORIGINS` is a comma-separated allowlist; set it to the real HTTPS frontend origin(s) outside local development. `MAX_FILE_SIZE_BYTES` defaults to 10 MiB.

`SECRET_KEY` is required (see Run locally); `ACCESS_TOKEN_EXPIRE_MINUTES` defaults to 30. `DATABASE_URL` defaults to `sqlite:///./data/app.db`. For PostgreSQL, install `psycopg[binary]` and set, for example, `DATABASE_URL=postgresql+psycopg://app:change-me@localhost:5432/revenue_analytics`. Keep real credentials in the environment, never in Git. Tables are created when missing; changing an existing table's columns needs a migration (for example with Alembic) or, in development only, deleting `data/app.db`.

## Forecast workflow

1. Upload a CSV in Data and review normalized types/values. Re-upload datasets imported before the decimal-precision fix; changing metadata alone does not re-normalize stored values.
2. Open `/app/forecast.html`. Choose the time column and explicitly select a numeric target.
3. Choose a horizon of 1–90 **periods**. Auto frequency recognizes complete daily, weekly or monthly sequences. Irregular dates (including trading-calendar gaps) use observation steps, with no invented future calendar dates.
4. Keep missing/duplicate handling at “Stop and report”, or explicitly select skip / sum / mean when appropriate. All dates must be valid `YYYY-MM-DD`; numeric targets must already be normalized. No interpolation is applied.
5. Optionally set season length in observations (e.g. 12 for monthly annual seasonality). Seasonality is user-specified, not inferred.
6. Click **Evaluate & forecast**. Inspect the chronological splits, validation comparison, held-out actual/predicted chart, Naive baseline and future forecast table.

Models: last-value Naive, mean of the last 7 observations, damped Holt trend, and optional Seasonal Naive. Holt fits a small deterministic grid of alpha/beta/phi using **training residuals only**. It is not a full ETS optimizer or Holt-Winters seasonal model.

For horizon `h`, the last `3h` observations form two consecutive validation windows and one untouched test window. Each validation forecast uses an expanding training prefix and predicts all `h` steps without observing intervening actuals. Lowest pooled validation MAE selects the model; ties favor Naive. The selected model is evaluated on the final `h` observations, then refitted on all history to forecast beyond the last observation. Test performance never changes the chosen model.

Eligibility requires at least `max(40, max(20, 2 × season_length) + 3 × horizon)` usable distinct dates, up to 50,000 input rows. The minimum is a product guardrail, not a statistical guarantee. The six-row `sample_sales.csv` intentionally fails this check. Use a longer historical series to test forecasting.

The endpoint is now `POST /forecast` with JSON (the old `?period=1week` demo contract is removed):

```json
{
  "time_column": "Date",
  "target_column": "Close/Last",
  "observations": [{"date": "2025-01-01", "value": 123.125}],
  "horizon": 7,
  "frequency": "auto",
  "missing_policy": "error",
  "duplicate_policy": "error",
  "season_length": 0
}
```

The example illustrates the request shape; send the full eligible history. The response contains validation scores/fold dates, held-out metrics and predictions, cleaning counts, fitted parameters, recent history (at most 200 points), warnings, and future predictions. All models use the full usable history for final fitting.

Method references: [chronological validation and benchmark methods](https://otexts.com/fpp3/toolbox.html), [damped Holt trend](https://otexts.com/fpp3/exponential-smoothing.html).

## Current limitations

- Access tokens cannot be revoked before they expire (no refresh tokens or server-side logout); keep `ACCESS_TOKEN_EXPIRE_MINUTES` short. There is no password reset or rate limiting on login yet.
- Schema migrations (Alembic) are not set up; `create_all` only creates missing tables.
- Forecasting currently supports one date/target series per run, point estimates only. ARIMA/SARIMA, external predictors, grouped series, market calendars, prediction intervals and saved models are not implemented.
- Import still uses heuristics for comma-only numeric notation and ambiguous dates; review the data before forecasting. Missing periods and multi-series datasets require user preparation. Poor backtest results are shown rather than hidden.
- Chart.js is loaded from a CDN, so the visual workspaces need network access to that CDN unless it is vendored for deployment.
