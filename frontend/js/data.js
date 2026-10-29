const DataWorkspace = (() => {
  const ROWS_PER_PAGE = 20;
  let currentPage = 1;

  function datasetState() {
    return AppState.read();
  }

  function renderWorkspace() {
    const state = datasetState();
    renderDatasetLibrary(state);
    const hasDataset = Boolean(state.dataset);
    document.getElementById("datasetWorkspace").hidden = !hasDataset;
    if (!hasDataset) return;

    renderMetadata(state.dataset);
    renderPreview(state.dataset);
    renderSemanticReview(state.dataset, state.semanticModel);
    renderQualityReport(state.dataset);
    UI.renderDatasetIndicator();
  }

  function renderDatasetLibrary(state) {
    const library = document.getElementById("datasetLibrary");
    const select = document.getElementById("datasetSelect");
    const datasets = state.datasets || [];
    library.hidden = datasets.length === 0;
    select.innerHTML = datasets.map((dataset, index) => {
      const label = `${dataset.filename} · ${I18n.t("common.rows", { count: UI.formatNumber(dataset.rows) })}`;
      return `<option value="${UI.escapeHtml(dataset.id)}" ${dataset.id === state.activeDatasetId ? "selected" : ""}>${UI.escapeHtml(label)}</option>`;
    }).join("");
  }

  function renderMetadata(dataset) {
    document.getElementById("datasetInfo").innerHTML = [
      [I18n.t("common.file"), dataset.filename],
      [I18n.t("common.rowsLabel"), UI.formatNumber(dataset.rows)],
      [I18n.t("common.columns"), UI.formatNumber(dataset.columns.length)],
    ].map(([label, value]) => `<div class="stat"><span>${label}</span><strong>${UI.escapeHtml(value)}</strong></div>`).join("");
  }

  function renderPreview(dataset) {
    const pageCount = Math.max(1, Math.ceil(dataset.data.length / ROWS_PER_PAGE));
    currentPage = Math.min(Math.max(currentPage, 1), pageCount);
    const start = (currentPage - 1) * ROWS_PER_PAGE;
    const rows = (dataset.rawData || dataset.data).slice(start, start + ROWS_PER_PAGE);
    const headers = dataset.columns.map((column) => `<th scope="col">${UI.escapeHtml(column)}</th>`).join("");
    const body = rows.map((row) => `<tr>${dataset.columns.map((column) => (
      `<td>${UI.escapeHtml(row[column] ?? "")}</td>`
    )).join("")}</tr>`).join("");

    document.getElementById("datasetTable").innerHTML = `
      <div class="table-scroll"><table><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>
      <nav class="pagination" aria-label="Dataset preview pages">
        <button class="button-secondary" type="button" data-preview-page="previous" ${currentPage === 1 ? "disabled" : ""}>${I18n.t("common.previous")}</button>
        <span>${I18n.t("common.page", { current: currentPage, total: pageCount })}</span>
        <button class="button-secondary" type="button" data-preview-page="next" ${currentPage === pageCount ? "disabled" : ""}>${I18n.t("common.next")}</button>
      </nav>`;
  }

  function selectOptions(values, chosen) {
    return values.map((value) => (
      `<option value="${UI.escapeHtml(value)}" ${value === chosen ? "selected" : ""}>${UI.escapeHtml(value)}</option>`
    )).join("");
  }

  function renderSemanticReview(dataset, semanticModel) {
    const rows = dataset.columns.map((column) => {
      const model = semanticModel[column];
      const confidence = model?.confidence || "low";
      return `<tr>
        <th scope="row">${UI.escapeHtml(column)}</th>
        <td>${UI.escapeHtml(model?.detectedType || "unknown")}</td>
        <td><label class="sr-only" for="type-${UI.escapeHtml(column)}">Final type for ${UI.escapeHtml(column)}</label><select id="type-${UI.escapeHtml(column)}" data-semantic="type" data-column="${UI.escapeHtml(column)}">${selectOptions(Semantic.TYPES, model?.type)}</select></td>
        <td>${UI.escapeHtml(model?.detectedRole || "unknown")}</td>
        <td><label class="sr-only" for="role-${UI.escapeHtml(column)}">Final role for ${UI.escapeHtml(column)}</label><select id="role-${UI.escapeHtml(column)}" data-semantic="role" data-column="${UI.escapeHtml(column)}">${selectOptions(Semantic.ROLES, model?.role)}</select></td>
        <td><span class="badge ${UI.escapeHtml(confidence)}">${UI.escapeHtml(confidence)}</span></td>
      </tr>`;
    }).join("");
    document.getElementById("semanticTable").innerHTML = `
      <div class="table-scroll"><table><thead><tr><th>${I18n.t("common.column")}</th><th>${I18n.t("common.detectedType")}</th><th>${I18n.t("common.finalType")}</th><th>${I18n.t("common.recommendedRole")}</th><th>${I18n.t("common.finalRole")}</th><th>${I18n.t("common.confidence")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function hasValue(value) {
    return value !== null && value !== undefined && String(value).trim() !== "";
  }

  function duplicateRowCount(dataset) {
    const known = new Set();
    let duplicates = 0;
    dataset.data.forEach((row) => {
      const key = JSON.stringify(dataset.columns.map((column) => row[column] ?? null));
      if (known.has(key)) duplicates += 1;
      else known.add(key);
    });
    return duplicates;
  }

  function renderQualityReport(dataset) {
    const missing = dataset.data.reduce((total, row) => (
      total + dataset.columns.filter((column) => !hasValue(row[column])).length
    ), 0);
    const duplicates = duplicateRowCount(dataset);
    const transformations = Object.entries(dataset.profiles || {})
      .filter(([, profile]) => profile.normalized_count || profile.invalid_count)
      .map(([column, profile]) => `<li><strong>${UI.escapeHtml(column)}</strong>: ${UI.escapeHtml(profile.detected_type)}; ${UI.formatNumber(profile.normalized_count)} normalized${profile.invalid_count ? `, ${UI.formatNumber(profile.invalid_count)} invalid → missing` : ""}.</li>`)
      .join("");
    document.getElementById("qualityReport").innerHTML = `
      <div class="quality-summary">
        <div><strong>${UI.formatNumber(missing)}</strong><span>${I18n.t("data.missingCells")}</span></div>
        <div><strong>${UI.formatNumber(duplicates)}</strong><span>${I18n.t("data.duplicateRows")}</span></div>
      </div>
      ${transformations ? `<section class="transformation-report"><h3>${I18n.t("data.importTransformations")}</h3><p class="muted">${I18n.t("data.transformIntro")}</p><ul>${transformations}</ul></section>` : ""}
      <p class="muted">${I18n.t("data.cleanIntro")}</p>
      <div class="inline-controls">
        <button class="button-secondary" type="button" data-clean="duplicates" ${duplicates ? "" : "disabled"}>${I18n.t("data.removeDuplicates")}</button>
        <button class="button-secondary" type="button" data-clean="missing" ${missing ? "" : "disabled"}>${I18n.t("data.removeMissing")}</button>
      </div>
      <div id="qualityMessage"></div>`;
  }

  function removeDuplicates() {
    const { dataset } = datasetState();
    const known = new Set();
    const rows = dataset.data.filter((row) => {
      const key = JSON.stringify(dataset.columns.map((column) => row[column] ?? null));
      if (known.has(key)) return false;
      known.add(key);
      return true;
    });
    const removed = dataset.data.length - rows.length;
    AppState.replaceRows(rows);
    currentPage = 1;
    renderWorkspace();
    UI.setMessage("qualityMessage", I18n.t("data.removedDuplicates", { count: removed, suffix: removed === 1 ? "" : "s" }));
  }

  function removeRowsWithMissingValues() {
    const { dataset } = datasetState();
    const rows = dataset.data.filter((row) => dataset.columns.every((column) => hasValue(row[column])));
    const removed = dataset.data.length - rows.length;
    AppState.replaceRows(rows);
    currentPage = 1;
    renderWorkspace();
    UI.setMessage("qualityMessage", I18n.t("data.removedMissing", { count: removed, suffix: removed === 1 ? "" : "s" }));
  }

  async function uploadSelectedFile() {
    const input = document.getElementById("fileInput");
    const button = document.getElementById("uploadButton");
    const file = input.files?.[0];
    if (!file) {
      UI.setMessage("uploadMessage", I18n.t("data.chooseFile"), "error");
      return;
    }

    button.disabled = true;
    button.textContent = I18n.t("data.uploading");
    UI.setMessage("uploadMessage", I18n.t("data.analysing"), "info");
    try {
      const dataset = await Api.upload(file);
      const semanticModel = Semantic.analyze(dataset.data, dataset.columns, dataset.profiles);
      AppState.setDataset(dataset, semanticModel);
      currentPage = 1;
      renderWorkspace();
      UI.setMessage("uploadMessage", I18n.t("data.saved"));
    } catch (error) {
      UI.setMessage("uploadMessage", error.message || I18n.t("data.uploadError"), "error");
    } finally {
      button.disabled = false;
      button.textContent = I18n.t("data.upload");
    }
  }

  function bindEvents() {
    document.getElementById("uploadButton").addEventListener("click", uploadSelectedFile);
    document.getElementById("datasetSelect").addEventListener("change", (event) => {
      AppState.selectDataset(event.target.value);
      currentPage = 1;
      renderWorkspace();
    });
    document.getElementById("datasetTable").addEventListener("click", (event) => {
      const button = event.target.closest("[data-preview-page]");
      if (!button) return;
      currentPage += button.dataset.previewPage === "next" ? 1 : -1;
      renderPreview(datasetState().dataset);
    });
    document.getElementById("semanticTable").addEventListener("change", (event) => {
      const select = event.target.closest("[data-semantic]");
      if (!select) return;
      AppState.updateSemantic(select.dataset.column, select.dataset.semantic, select.value);
      renderSemanticReview(datasetState().dataset, datasetState().semanticModel);
    });
    document.getElementById("qualityReport").addEventListener("click", (event) => {
      const button = event.target.closest("[data-clean]");
      if (!button) return;
      if (button.dataset.clean === "duplicates") removeDuplicates();
      if (button.dataset.clean === "missing") removeRowsWithMissingValues();
    });
  }

  function initialise() {
    UI.initialiseShell("data");
    bindEvents();
    renderWorkspace();
  }

  return { initialise };
})();

window.addEventListener("DOMContentLoaded", DataWorkspace.initialise);
