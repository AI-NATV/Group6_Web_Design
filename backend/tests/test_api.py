"""Health, static frontend and CSV upload validation."""


def test_health_check_returns_service_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "revenue-analytics-api"}
    assert response.headers["X-Request-ID"]


def test_frontend_workspaces_are_served_same_origin(client):
    data_page = client.get("/app/")
    visualize_page = client.get("/app/visualize.html")
    forecast_page = client.get("/app/forecast.html")

    assert data_page.status_code == 200
    assert "Data workspace" in data_page.text
    assert "Visualize workspace" in visualize_page.text
    assert "Define your forecasting task" in forecast_page.text
    assert "Sign in to your workspace" in client.get("/app/login.html").text
    assert client.get("/app/css/style.css").status_code == 200
    assert client.get("/app/js/visualize.js").status_code == 200


def test_upload_returns_json_safe_dataset(alice):
    response = alice.post(
        "/api/v1/datasets",
        files={"file": ("sales.csv", b"region,revenue\nNorth,1200\nSouth,\n", "text/csv")},
    )

    assert response.status_code == 201
    assert response.json()["columns"] == ["region", "revenue"]
    assert response.json()["data"][1]["revenue"] is None


def test_upload_normalizes_currency_without_losing_raw_values(alice):
    response = alice.post(
        "/api/v1/datasets",
        files={"file": ("prices.csv", b"date,close\n2026-09-01,\"$1,234.50\"\n2026-09-02,($12.25)\n", "text/csv")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["raw_data"][0]["close"] == "$1,234.50"
    assert payload["data"][0]["close"] == 1234.5
    assert payload["data"][1]["close"] == -12.25
    assert payload["profiles"]["close"]["detected_type"] == "currency"


def test_upload_normalizes_an_unambiguous_us_date_format(alice):
    response = alice.post(
        "/api/v1/datasets",
        files={"file": ("prices.csv", b"date,close\n07/31/2025,$177.87\n07/30/2025,$179.27\n", "text/csv")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["data"][0]["date"] == "2025-07-31"
    assert payload["profiles"]["date"]["date_format"] == "month/day/year"


def test_upload_rejects_invalid_files(alice):
    invalid_extension = alice.post(
        "/api/v1/datasets", files={"file": ("sales.txt", b"region,revenue\nNorth,1", "text/plain")}
    )
    empty_csv = alice.post("/api/v1/datasets", files={"file": ("sales.csv", b"", "text/csv")})

    assert invalid_extension.status_code == 400
    assert "Only CSV" in invalid_extension.json()["detail"]
    assert empty_csv.status_code == 400
    assert "empty" in empty_csv.json()["detail"].lower()


def test_upload_rejects_header_only_csv(alice):
    response = alice.post("/api/v1/datasets", files={"file": ("sales.csv", b"region,revenue\n", "text/csv")})

    assert response.status_code == 400
    assert "no data rows" in response.json()["detail"].lower()


def test_forecast_requires_real_observations(client):
    response = client.post("/forecast?period=1week")
    assert response.status_code == 422
