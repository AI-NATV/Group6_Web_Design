const ForecastWorkspace = (() => {
  let charts = [];
  let running = false;
  const t = (key, variables) => I18n.t(key, variables);
  const modelNames = {
    naive: "forecast.naive", moving_average: "forecast.average",
    holt_damped: "forecast.holt", seasonal_naive: "forecast.seasonal",
  };
  const number = (value) => new Intl.NumberFormat(I18n.language() === "vi" ? "vi-VN" : "en-US", { maximumFractionDigits: 4 }).format(value);
  const el = (id) => document.getElementById(id);
  const escape = (value) => UI.escapeHtml(value);

  function clearResults() {
    charts.forEach((chart) => chart.destroy());
    charts = [];
    el("forecastResults").hidden = true;
  }

  function configuration() {
    return {
      time_column: el("forecastTime").value,
      target_column: el("forecastTarget").value,
      horizon: Number(el("forecastHorizon").value),
      frequency: el("forecastFrequency").value,
      missing_policy: el("forecastMissing").value,
      duplicate_policy: el("forecastDuplicates").value,
      season_length: Number(el("forecastSeason").value),
    };
  }

  function eligibility() {
    const config = configuration();
    const dataset = AppState.activeDataset();
    const required = Math.max(40, Math.max(20, 2 * config.season_length) + 3 * config.horizon);
    let error = "";
    if (!config.time_column || !config.target_column) error = t("forecast.chooseFields");
    else if (config.time_column === config.target_column) error = t("forecast.differentColumns");
    else if (!Number.isInteger(config.horizon) || config.horizon < 1 || config.horizon > 90) error = t("forecast.horizonError");
    else if (!Number.isInteger(config.season_length) || config.season_length < 0 || config.season_length > 365 || config.season_length === 1) error = t("forecast.seasonError");
    else if (dataset.data.length > 50000) error = t("forecast.maxRows");
    else if (dataset.data.length < required) error = t("forecast.needHistory", { required, rows: dataset.data.length });
    el("forecastEligibility").textContent = error || t("forecast.eligible", { required });
    el("forecastEligibility").className = `message ${error ? "warning" : "info"}`;
    el("runForecast").disabled = Boolean(error) || running;
    return !error;
  }

  function table(caption, headers, rows) {
    return `<div class="table-scroll"><table><caption>${escape(caption)}</caption><thead><tr>${headers.map((value) => `<th scope="col">${escape(value)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((value) => `<td>${escape(value)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }

  function draw(id, labels, datasets, target) {
    charts.push(new Chart(el(id), {
      type: "line", data: { labels, datasets: datasets.map((item) => ({
        pointRadius: labels.length > 90 ? 0 : 2, borderWidth: 2, tension: 0, spanGaps: false, ...item,
      })) },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 12 }, title: { display: true, text: t("forecast.axis") } },
          y: { title: { display: true, text: target }, beginAtZero: false } },
      },
    }));
  }

  function render(result) {
    el("forecastResults").hidden = false;
    const name = t(modelNames[result.selected_model]);
    el("forecastSummary").innerHTML = [
      [t("forecast.selectedValidation"), name], [t("forecast.testMae"), number(result.test_metrics.mae)],
      [t("forecast.testRmse"), number(result.test_metrics.rmse)], [t("forecast.naiveMae"), number(result.naive_test_metrics.mae)],
      [t("forecast.periods"), `${result.horizon} · ${result.frequency}`], [t("forecast.usableDates"), result.quality.usable_dates],
    ].map(([label, value]) => `<div class="stat"><span>${escape(label)}</span><strong title="${escape(value)}">${escape(value)}</strong></div>`).join("");
    const split = result.splits;
    el("forecastSplits").innerHTML = table(t("forecast.splitsCaption"), [t("forecast.stage"), t("forecast.dates"), t("forecast.purpose")], [
      [t("forecast.initialTraining"), `${split.initial_train_start} → ${split.initial_train_end}`, t("forecast.observationsCount", { count: split.initial_train_count })],
      [t("forecast.validation"), `${split.validation_start} → ${split.validation_end}`, t("forecast.validationPurpose", { horizon: result.horizon })],
      [t("forecast.heldTest"), `${split.test_start} → ${split.test_end}`, t("forecast.testPurpose", { count: split.test_count })],
      [t("forecast.finalRefit"), `${t("forecast.date")} ${split.test_end}`, t("forecast.refitPurpose", { count: split.refit_count })],
    ]);
    el("forecastComparison").innerHTML = table(t("forecast.comparisonCaption"), [t("forecast.model"), t("forecast.validationMae"), t("forecast.validationRmse"), t("forecast.selection")],
      result.comparison.map((item) => [t(modelNames[item.model]), number(item.validation.mae), number(item.validation.rmse), item.model === result.selected_model ? t("forecast.selected") : ""]));
    el("backtestTable").innerHTML = `<details><summary>${t("forecast.viewPredictions")}</summary>${table(t("forecast.backtestCaption"), [t("forecast.date"), t("forecast.actual"), name, t("forecast.naive")], result.backtest.map((point) => [point.date, number(point.actual), number(point.predicted), number(point.naive)]))}</details>`;
    el("forecastWarnings").innerHTML = result.warnings.map((warning) => `<p class="message warning">${escape(warning)}</p>`).join("");
    el("forecastTable").innerHTML = table(t("forecast.futureCaption"), [t("forecast.step"), t("forecast.datePeriod"), t("forecast.predicted", { field: result.target_column })], result.forecast.map((point) => [point.step, point.date || t("forecast.observation", { step: point.step }), number(point.predicted)]));
    el("forecastMethod").textContent = t("forecast.fitted", { name, parameters: JSON.stringify(result.model_parameters), target: result.target_column });
    if (typeof Chart === "undefined") {
      UI.setMessage("forecastMessage", t("forecast.chartUnavailable"), "warning");
      return;
    }
    draw("backtestChart", result.backtest.map((point) => point.date), [
      { label: t("forecast.actualHeld"), data: result.backtest.map((point) => point.actual), borderColor: "#0f766e" },
      { label: name, data: result.backtest.map((point) => point.predicted), borderColor: "#4f46e5" },
      { label: t("forecast.naiveBaseline"), data: result.backtest.map((point) => point.naive), borderColor: "#94a3b8", borderDash: [4, 4] },
    ], result.target_column);
    const history = result.history;
    draw("forecastChart", [...history.map((point) => point.date), ...result.forecast.map((point) => point.date || `Observation +${point.step}`)], [
      { label: t("forecast.actualHistory"), data: [...history.map((point) => point.actual), ...result.forecast.map(() => null)], borderColor: "#0f766e" },
      { label: t("forecast.futurePoint"), data: [...history.slice(1).map(() => null), history[history.length - 1].actual, ...result.forecast.map((point) => point.predicted)], borderColor: "#4f46e5", borderDash: [6, 3] },
    ], result.target_column);
    UI.setMessage("forecastMessage", t("forecast.complete"));
  }

  async function run(event) {
    event.preventDefault();
    if (running || !eligibility()) return;
    const config = configuration();
    const dataset = AppState.activeDataset();
    clearResults();
    running = true;
    el("forecastControls").disabled = true;
    el("runForecast").textContent = t("forecast.evaluating");
    UI.setMessage("forecastMessage", t("forecast.progress"), "info");
    try {
      const result = await Api.forecast({ ...config, observations: dataset.data.map((row) => ({
        date: row[config.time_column] ?? null, value: row[config.target_column] ?? null,
      })) });
      render(result);
    } catch (error) {
      UI.setMessage("forecastMessage", error.message || t("forecast.error"), "error");
    } finally {
      running = false;
      el("forecastControls").disabled = false;
      el("runForecast").textContent = t("forecast.run");
      eligibility();
    }
  }

  function initialise() {
    if (!UI.initialiseShell("forecast")) return;
    const { dataset, semanticModel } = AppState.read();
    if (!dataset) {
      UI.showDatasetRequired("forecastRoot", t("forecast.eyebrow"));
      return;
    }
    el("forecastApp").hidden = false;
    const numericFields = dataset.columns.filter((column) => semanticModel[column]?.type === "number");
    const dates = dataset.columns.filter((column) => semanticModel[column]?.type === "date" || semanticModel[column]?.role === "date");
    const options = (columns) => columns.map((column) => `<option value="${escape(column)}">${escape(column)}</option>`).join("");
    el("forecastTime").innerHTML = `<option value="">${t("forecast.chooseTime")}</option>` + options(dataset.columns);
    el("forecastTarget").innerHTML = `<option value="">${t("forecast.chooseTarget")}</option>` + options(numericFields);
    if (dates.length === 1) el("forecastTime").value = dates[0];
    el("forecastDatasetContext").innerHTML = [
      [t("forecast.activeFile"), dataset.filename], [t("common.rowsLabel"), dataset.data.length], [t("forecast.numericTargets"), numericFields.length],
    ].map(([label, value]) => `<div class="stat"><span>${escape(label)}</span><strong>${escape(value)}</strong></div>`).join("");
    el("forecastForm").addEventListener("submit", run);
    el("forecastForm").addEventListener("input", () => {
      clearResults();
      UI.setMessage("forecastMessage", "");
      eligibility();
    });
    el("forecastHelp").addEventListener("click", () => {
      const panel = el("forecastHelpPanel");
      const expanded = el("forecastHelp").getAttribute("aria-expanded") === "true";
      panel.hidden = expanded;
      el("forecastHelp").setAttribute("aria-expanded", String(!expanded));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      el("forecastHelpPanel").hidden = true;
      el("forecastHelp").setAttribute("aria-expanded", "false");
    });
    eligibility();
  }

  return { initialise };
})();

window.addEventListener("DOMContentLoaded", ForecastWorkspace.initialise);
