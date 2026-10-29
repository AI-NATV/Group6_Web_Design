# Revenue Analytics Dashboard

A semantic-aware Mini BI application for CSV data: upload and review fields, build a session dashboard, then evaluate univariate forecasts on your own data.

## What works now

- Three task-focused workspaces: **Data**, **Visualize**, and **Forecast**.
- CSV validation (CSV only, no empty/header-only data, unique nonblank columns, 10 MB limit).
- Paginated preview, type/role recommendations, confidence, and user overrides.
- Session-scoped active dataset and semantic state across pages.
- Data-quality counts and explicit removal of exact duplicates or rows with missing values.
- Semantic-aware drag-and-drop/click-to-assign field wells for Bar, Line, Pie, and Scatter charts.
- SUM, AVERAGE, COUNT, MIN, and MAX aggregation; compatibility feedback; and a small session dashboard with reorder/remove controls and KPI cards.
- FastAPI health endpoint, OpenAPI docs, Pydantic response contracts, controlled CSV errors, request IDs/timing logs, and critical API tests.
- Forecast configuration, chronological backtesting, MAE/RMSE comparison and future point predictions from the uploaded target series.

## Architecture

```text
frontend/
  index.html                  Data workspace
  visualize.html              Visualize workspace
  forecast.html               Forecast workspace
  css/style.css
  js/                         API, state, semantic, UI, and page-specific logic
backend/
  main.py                     FastAPI assembly and routes
  config.py                   Environment configuration
  models.py                   API response contracts
  services/csv_service.py     CSV parsing and validation
  services/forecast_service.py  Model fitting, chronological validation and forecast
  tests/test_api.py           Critical API tests
```

The active CSV is kept in `sessionStorage`, so it survives navigation in the same browser session but does not survive closing that session. Forecast requests send only the selected date/target pairs to the backend; no trained model or forecast job is persisted.

## Run locally

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Start the backend from the project root:

   ```powershell
   uvicorn backend.main:app --reload
   ```

4. Open [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/) in a browser. This serves the frontend from the same FastAPI origin.
5. Upload `sample_sales.csv`, review the semantic recommendations, then open **Visualize**.

API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) and health status at [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health).

## Test

```powershell
python -m pytest backend/tests -q
```

`scripts/check_forecast_browser.cjs` provides a browser integration check (Node 22+, isolated Chromium remote-debugging session on port 9228, and a backend on port 8017). It uploads a synthetic 120-row CSV through the UI and checks forecast tables/charts, date order, decimal precision, mobile layout, insufficient-history gating, and API error recovery. Run `node scripts/check_forecast_browser.cjs`; its screenshot goes to the ignored `.tmp-forecast-qa/forecast.png`. The script uses a new tab and does not start/stop the browser or backend.

## Configuration

Copy `.env.example` values into your deployment environment. `ALLOWED_ORIGINS` is a comma-separated allowlist; set it to the real HTTPS frontend origin(s) outside local development. `MAX_FILE_SIZE_BYTES` defaults to 10 MiB.

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

- Browser-session state is a prototype state layer, not durable saved projects.
- Forecasting currently supports one date/target series per run, point estimates only. ARIMA/SARIMA, external predictors, grouped series, market calendars, prediction intervals and saved models are not implemented.
- Import still uses heuristics for comma-only numeric notation and ambiguous dates; review the data before forecasting. Missing periods and multi-series datasets require user preparation. Poor backtest results are shown rather than hidden.
- Chart.js is loaded from a CDN, so the visual workspaces need network access to that CDN unless it is vendored for deployment.
