const VisualizeWorkspace = (() => {
  let previewChart = null;
  let dashboardCharts = [];
  let selectedField = null;
  let lastGeneratedVisual = null;
  let chartType = "bar";
  let fields = freshFields(chartType);
  let aggregation = "sum";
  const t = (key, variables) => I18n.t(key, variables);

  function freshFields(type) {
    return type === "scatter" ? { x: null, y: null } : { dimension: null, measure: null };
  }

  function workspaceState() {
    return AppState.read();
  }

  function fieldMetadata(column) {
    return workspaceState().semanticModel[column];
  }

  function describeVisual(visual) {
    const fieldsText = visual.chartType === "scatter"
      ? `${visual.fields.y} vs ${visual.fields.x}`
      : `${visual.aggregation.toUpperCase()} ${visual.fields.measure} by ${visual.fields.dimension}`;
    return { title: t("visual.visual", { type: t(`visual.${visual.chartType}`) }), fields: fieldsText };
  }

  function displayRole(metadata) {
    return metadata?.role?.replaceAll("_", " ") || t("common.unknown");
  }

  function renderChartTypes() {
    const types = [
      ["bar", t("visual.bar"), t("visual.compareCategories")],
      ["line", t("visual.line"), t("visual.showTrend")],
      ["pie", t("visual.pie"), t("visual.showShare")],
      ["scatter", t("visual.scatter"), t("visual.compareNumbers")],
    ];
    document.getElementById("chartTypes").innerHTML = types.map(([value, label, description]) => `
      <button type="button" class="chart-type ${chartType === value ? "active" : ""}" data-chart-type="${value}" aria-pressed="${chartType === value}">
        <strong>${label}</strong><span>${description}</span>
      </button>`).join("");
  }

  function fieldChip(slot, column) {
    if (!column) return "";
    return `<span class="field-chip">${UI.escapeHtml(column)}<button type="button" aria-label="${UI.escapeHtml(t("visual.removeField", { field: column }))}" data-remove-field="${slot}">×</button></span>`;
  }

  function well(slot, title, help) {
    return `<div class="field-well" data-well="${slot}" tabindex="0" role="button" aria-label="${UI.escapeHtml(title)} field well. ${UI.escapeHtml(help)}">
      <span class="well-label">${UI.escapeHtml(title)}</span>
      <span class="well-help">${UI.escapeHtml(help)}</span>
      <div class="well-value">${fieldChip(slot, fields[slot]) || t("visual.dropField")}</div>
    </div>`;
  }

  function renderFieldWells() {
    const aggregationControl = chartType === "scatter" ? "" : `
      <label class="aggregation-control">${t("visual.aggregation")}
        <select id="aggregation" aria-label="${t("visual.aggregation")}">
          ${["sum", "average", "count", "min", "max"].map((value) => `<option value="${value}" ${value === aggregation ? "selected" : ""}>${value.toUpperCase()}</option>`).join("")}
        </select>
      </label>`;
    const wells = chartType === "scatter"
      ? `${well("x", t("visual.xValue"), t("visual.numericField"))}${well("y", t("visual.yValue"), t("visual.numericField"))}`
      : `${well("dimension", chartType === "pie" ? t("visual.category") : t("visual.xCategory"), t("visual.categoryField"))}${well("measure", chartType === "pie" ? t("visual.value") : t("visual.yValue"), t("visual.numericField"))}`;
    document.getElementById("fieldWells").innerHTML = `${wells}${aggregationControl}`;
  }

  function renderDataPane() {
    const { dataset, semanticModel } = workspaceState();
    const query = document.getElementById("fieldSearch")?.value.trim().toLowerCase() || "";
    const fieldsList = dataset.columns.filter((column) => column.toLowerCase().includes(query));
    document.getElementById("dataFields").innerHTML = fieldsList.length ? fieldsList.map((column) => {
      const metadata = semanticModel[column];
      return `<button type="button" class="data-field ${selectedField === column ? "selected" : ""}" draggable="true" data-field="${UI.escapeHtml(column)}">
        <strong>${UI.escapeHtml(column)}</strong><span>${UI.escapeHtml(metadata?.type || "unknown")} · ${UI.escapeHtml(displayRole(metadata))}</span>
      </button>`;
    }).join("") : `<p class="muted">${t("visual.noMatches")}</p>`;
  }

  function allowedInWell(column, slot) {
    const metadata = fieldMetadata(column);
    if (slot === "measure" || slot === "x" || slot === "y") return Semantic.isNumericField(metadata);
    return Semantic.isDimensionField(metadata);
  }

  function assignField(column, slot) {
    if (!column) return;
    if (!allowedInWell(column, slot)) {
      const expected = slot === "dimension" ? t("visual.expectedDimension") : t("visual.expectedNumeric");
      UI.setMessage("builderMessage", t("visual.invalidField", { field: column, expected }), "error");
      return;
    }
    fields[slot] = column;
    selectedField = null;
    invalidateGeneratedVisual();
    UI.setMessage("builderMessage", "");
    renderFieldWells();
    renderDataPane();
  }

  function removeField(slot) {
    fields[slot] = null;
    invalidateGeneratedVisual();
    renderFieldWells();
  }

  function invalidateGeneratedVisual() {
    lastGeneratedVisual = null;
    if (previewChart) {
      previewChart.destroy();
      previewChart = null;
    }
    document.getElementById("addToDashboard").disabled = true;
    document.getElementById("activeChart").setAttribute("aria-label", t("visual.chartPreview"));
  }

  function validationError() {
    if (chartType === "scatter") {
      if (!fields.x || !fields.y) return t("visual.addScatter");
      return null;
    }
    if (!fields.dimension || !fields.measure) return t("visual.addFields");
    return null;
  }

  function aggregateData(dimension, measure, operation, dataset) {
    const groups = new Map();
    dataset.data.forEach((row) => {
      const key = row[dimension] ?? "(blank)";
      const value = Semantic.toNumber(row[measure]);
      if (!groups.has(key)) groups.set(key, []);
      if (Number.isFinite(value)) groups.get(key).push(value);
    });
    const entries = [...groups.entries()];
    // CSV exports commonly list the newest record first. A date dimension is
    // a timeline, so present it chronologically from left (oldest) to right
    // (newest), without changing the stored dataset itself.
    const dateLabelPattern = /^\d{4}-\d{2}-\d{2}$/;
    const labelsAreDates = entries.length > 0 && entries.every(([key]) => {
      const label = String(key);
      return dateLabelPattern.test(label) && Number.isFinite(Date.parse(label));
    });
    if (fieldMetadata(dimension)?.type === "date" || labelsAreDates) {
      entries.sort(([left], [right]) => {
        const leftTime = Date.parse(String(left));
        const rightTime = Date.parse(String(right));
        if (!Number.isFinite(leftTime)) return 1;
        if (!Number.isFinite(rightTime)) return -1;
        return leftTime - rightTime;
      });
    }
    const labels = [];
    const values = [];
    entries.forEach(([key, numbers]) => {
      labels.push(String(key));
      if (operation === "count") values.push(numbers.length);
      else if (!numbers.length) values.push(0);
      else if (operation === "sum") values.push(numbers.reduce((sum, number) => sum + number, 0));
      else if (operation === "average") values.push(numbers.reduce((sum, number) => sum + number, 0) / numbers.length);
      else if (operation === "min") values.push(Math.min(...numbers));
      else values.push(Math.max(...numbers));
    });
    return { labels, values };
  }

  function chartOptions(xTitle, yTitle, type) {
    const base = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: type === "pie" } } };
    if (type === "pie") return base;
    return {
      ...base,
      scales: {
        x: { title: { display: true, text: xTitle } },
        y: { title: { display: true, text: yTitle }, beginAtZero: type !== "scatter" },
      },
    };
  }

  function chartConfiguration(visual, dataset) {
    if (visual.chartType === "scatter") {
      const points = dataset.data.map((row) => ({
        x: Semantic.toNumber(row[visual.fields.x]),
        y: Semantic.toNumber(row[visual.fields.y]),
      })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
      if (!points.length) throw new Error(t("visual.noPaired"));
      return {
        type: "scatter",
        data: { datasets: [{ label: `${visual.fields.y} vs ${visual.fields.x}`, data: points, backgroundColor: "#4f46e5" }] },
        options: chartOptions(visual.fields.x, visual.fields.y, "scatter"),
      };
    }

    const grouped = aggregateData(visual.fields.dimension, visual.fields.measure, visual.aggregation, dataset);
    if (!grouped.labels.length) throw new Error(t("visual.noData"));
    const colors = ["#4f46e5", "#0ea5e9", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6"];
    return {
      type: visual.chartType,
      data: {
        labels: grouped.labels,
        datasets: [{
          label: `${visual.aggregation.toUpperCase()} ${visual.fields.measure} by ${visual.fields.dimension}`,
          data: grouped.values,
          borderWidth: 2,
          tension: 0.25,
          borderColor: "#4f46e5",
          backgroundColor: visual.chartType === "pie" ? grouped.labels.map((_, index) => colors[index % colors.length]) : "rgba(79, 70, 229, .72)",
        }],
      },
      options: chartOptions(visual.fields.dimension, visual.fields.measure, visual.chartType),
    };
  }

  function generateChart() {
    const error = validationError();
    if (error) {
      UI.setMessage("builderMessage", error, "error");
      return;
    }
    const visual = { chartType, fields: { ...fields }, aggregation };
    try {
      const configuration = chartConfiguration(visual, workspaceState().dataset);
      if (previewChart) previewChart.destroy();
      const canvas = document.getElementById("activeChart");
      const description = describeVisual(visual);
      previewChart = new Chart(canvas, configuration);
      canvas.setAttribute("aria-label", `${description.title}: ${description.fields}`);
      lastGeneratedVisual = visual;
      document.getElementById("addToDashboard").disabled = false;
      UI.setMessage("builderMessage", t("visual.chartGenerated"));
    } catch (chartError) {
      UI.setMessage("builderMessage", chartError.message || t("visual.chartError"), "error");
    }
  }

  function saveVisual() {
    if (!lastGeneratedVisual) return;
    AppState.addVisual(lastGeneratedVisual);
    renderDashboard();
    UI.setMessage("builderMessage", t("visual.visualAdded"));
  }

  function renderKpis() {
    const { dataset, semanticModel } = workspaceState();
    const measureColumns = dataset.columns.filter((column) => semanticModel[column]?.role === "measure").slice(0, 3);
    document.getElementById("kpiCards").innerHTML = measureColumns.map((column) => {
      const total = dataset.data.reduce((sum, row) => {
        const value = Semantic.toNumber(row[column]);
        return sum + (Number.isFinite(value) ? value : 0);
      }, 0);
      return `<article class="kpi-card"><span>${UI.escapeHtml(t("visual.total", { field: column }))}</span><strong>${UI.formatNumber(total)}</strong></article>`;
    }).join("");
  }

  function renderDashboard() {
    dashboardCharts.forEach((chart) => chart.destroy());
    dashboardCharts = [];
    const { dashboard, dataset } = workspaceState();
    renderKpis();
    document.getElementById("savedVisuals").innerHTML = dashboard.length ? dashboard.map((visual, index) => {
      const description = describeVisual(visual);
      return `
      <article class="saved-visual">
        <header><div><h3>${UI.escapeHtml(description.title)}</h3><p>${UI.escapeHtml(description.fields)}</p></div>
          <div class="visual-actions"><button type="button" class="icon-button" data-move="up" data-visual-id="${visual.id}" ${index === 0 ? "disabled" : ""} aria-label="${UI.escapeHtml(t("visual.moveUp"))}">↑</button><button type="button" class="icon-button" data-move="down" data-visual-id="${visual.id}" ${index === dashboard.length - 1 ? "disabled" : ""} aria-label="${UI.escapeHtml(t("visual.moveDown"))}">↓</button><button type="button" class="icon-button danger" data-remove-visual="${visual.id}" aria-label="${UI.escapeHtml(t("visual.removeVisual"))}">×</button></div>
        </header><div class="saved-chart-wrap"><canvas id="saved-chart-${visual.id}" role="img" aria-label="${UI.escapeHtml(`${description.title}: ${description.fields}`)}"></canvas></div>
      </article>`;
    }).join("") : `<p class="muted dashboard-empty">${t("visual.dashboardEmpty")}</p>`;

    dashboard.forEach((visual) => {
      try {
        dashboardCharts.push(new Chart(document.getElementById(`saved-chart-${visual.id}`), chartConfiguration(visual, dataset)));
      } catch {
        // A visual with no longer-compatible data remains removable and does not break the dashboard.
      }
    });
  }

  function bindEvents() {
    document.getElementById("chartTypes").addEventListener("click", (event) => {
      const button = event.target.closest("[data-chart-type]");
      if (!button) return;
      chartType = button.dataset.chartType;
      fields = freshFields(chartType);
      invalidateGeneratedVisual();
      renderChartTypes();
      renderFieldWells();
      UI.setMessage("builderMessage", "");
    });
    document.getElementById("fieldSearch").addEventListener("input", renderDataPane);
    const dataFields = document.getElementById("dataFields");
    dataFields.addEventListener("dragstart", (event) => {
      const field = event.target.closest("[data-field]");
      if (!field) return;
      event.dataTransfer.setData("text/plain", field.dataset.field);
      event.dataTransfer.effectAllowed = "copy";
    });
    dataFields.addEventListener("click", (event) => {
      const field = event.target.closest("[data-field]");
      if (!field) return;
      selectedField = field.dataset.field;
      renderDataPane();
      UI.setMessage("builderMessage", t("visual.selected", { field: selectedField }));
    });
    const wells = document.getElementById("fieldWells");
    wells.addEventListener("dragover", (event) => {
      const wellElement = event.target.closest("[data-well]");
      if (!wellElement) return;
      event.preventDefault();
      wellElement.classList.add("drag-over");
    });
    wells.addEventListener("dragleave", (event) => event.target.closest("[data-well]")?.classList.remove("drag-over"));
    wells.addEventListener("drop", (event) => {
      const wellElement = event.target.closest("[data-well]");
      if (!wellElement) return;
      event.preventDefault();
      wellElement.classList.remove("drag-over");
      assignField(event.dataTransfer.getData("text/plain"), wellElement.dataset.well);
    });
    wells.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-remove-field]");
      if (remove) {
        removeField(remove.dataset.removeField);
        return;
      }
      const wellElement = event.target.closest("[data-well]");
      if (wellElement && selectedField) assignField(selectedField, wellElement.dataset.well);
    });
    wells.addEventListener("keydown", (event) => {
      const wellElement = event.target.closest("[data-well]");
      if (!wellElement || !selectedField || !["Enter", " ", "Spacebar"].includes(event.key)) return;
      event.preventDefault();
      assignField(selectedField, wellElement.dataset.well);
    });
    wells.addEventListener("change", (event) => {
      if (event.target.id === "aggregation") {
        aggregation = event.target.value;
        invalidateGeneratedVisual();
        UI.setMessage("builderMessage", t("visual.aggregationChanged"));
      }
    });
    document.getElementById("generateChart").addEventListener("click", generateChart);
    document.getElementById("addToDashboard").addEventListener("click", saveVisual);
    document.getElementById("savedVisuals").addEventListener("click", (event) => {
      const remove = event.target.closest("[data-remove-visual]");
      const move = event.target.closest("[data-move]");
      if (remove) AppState.removeVisual(remove.dataset.removeVisual);
      if (move) AppState.moveVisual(move.dataset.visualId, move.dataset.move === "up" ? -1 : 1);
      if (remove || move) renderDashboard();
    });
  }

  function initialise() {
    UI.initialiseShell("visualize");
    if (!AppState.activeDataset()) {
      UI.showDatasetRequired("visualizeRoot", t("visual.eyebrow"));
      return;
    }
    document.getElementById("visualizeApp").hidden = false;
    bindEvents();
    renderChartTypes();
    renderFieldWells();
    renderDataPane();
    renderDashboard();
  }

  return { initialise };
})();

window.addEventListener("DOMContentLoaded", VisualizeWorkspace.initialise);
