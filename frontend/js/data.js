const DataWorkspace = (() => {
  const ROWS_PER_PAGE = 20;
  // Mirrors the server default (MAX_FILE_SIZE_BYTES). The server still re-validates every upload.
  const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;
  let currentPage = 1;
  let library = [];
  let busy = false;

  function datasetState() {
    return AppState.read();
  }

  function renderWorkspace() {
    const state = datasetState();
    renderDatasetLibrary(state);
    UI.renderDatasetIndicator();
    const hasDataset = Boolean(state.dataset);
    document.getElementById("datasetWorkspace").hidden = !hasDataset;
    if (!hasDataset) return;

    renderMetadata(state.dataset);
    renderPreview(state.dataset);
    renderSemanticReview(state.dataset, state.semanticModel);
    renderQualityReport(state.dataset);
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(I18n.language() === "vi" ? "vi-VN" : "en-US", { dateStyle: "medium" }).format(date);
  }

  function renderDatasetLibrary(state) {
    const libraryElement = document.getElementById("datasetLibrary");
    const select = document.getElementById("datasetSelect");
    libraryElement.hidden = library.length === 0;
    const placeholder = state.activeDatasetId === null
      ? `<option value="" selected>${UI.escapeHtml(I18n.t("data.chooseSaved"))}</option>`
      : "";
    select.innerHTML = placeholder + library.map((dataset) => {
      const label = `${dataset.filename} · ${I18n.t("common.rows", { count: UI.formatNumber(dataset.rows) })} · ${formatDate(dataset.created_at)}`;
      const selected = String(dataset.id) === String(state.activeDatasetId) ? "selected" : "";
      return `<option value="${UI.escapeHtml(dataset.id)}" ${selected}>${UI.escapeHtml(label)}</option>`;
    }).join("");
    select.disabled = busy;
    document.getElementById("deleteDataset").disabled = busy || state.activeDatasetId === null;
  }

  async function refreshLibrary() {
    try {
      library = await Api.listDatasets();
    } catch (error) {
      library = [];
      UI.setMessage("uploadMessage", I18n.t("data.libraryError", { error: error.message }), "error");
      return;
    }
    // A dataset deleted elsewhere (another tab or teammate) must not stay active here.
    const activeId = datasetState().activeDatasetId;
    const listIsComplete = library.length < 100;
    if (activeId !== null && listIsComplete && !library.some((dataset) => String(dataset.id) === String(activeId))) {
      AppState.clear();
    }
  }

  async function whileBusy(task) {
    busy = true;
    renderDatasetLibrary(datasetState());
    try {
      return await task();
    } finally {
      busy = false;
      renderDatasetLibrary(datasetState());
    }
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
    const caption = I18n.t("data.previewCaption", {
      start: UI.formatNumber(rows.length ? start + 1 : 0),
      end: UI.formatNumber(start + rows.length),
      total: UI.formatNumber(dataset.data.length),
    });
    const headers = dataset.columns.map((column) => `<th scope="col">${UI.escapeHtml(column)}</th>`).join("");
    const body = rows.map((row) => `<tr>${dataset.columns.map((column) => (
      `<td>${UI.escapeHtml(row[column] ?? "")}</td>`
    )).join("")}</tr>`).join("");

    document.getElementById("datasetTable").innerHTML = `
      <div class="table-scroll"><table><caption>${UI.escapeHtml(caption)}</caption><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>
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
      <div class="table-scroll"><table><caption>${I18n.t("data.semanticCaption")}</caption><thead><tr><th scope="col">${I18n.t("common.column")}</th><th scope="col">${I18n.t("common.detectedType")}</th><th scope="col">${I18n.t("common.finalType")}</th><th scope="col">${I18n.t("common.recommendedRole")}</th><th scope="col">${I18n.t("common.finalRole")}</th><th scope="col">${I18n.t("common.confidence")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
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

  async function saveCleanedRows(rows, messageKey) {
    const removed = datasetState().dataset.data.length - rows.length;
    document.querySelectorAll("[data-clean]").forEach((button) => { button.disabled = true; });
    try {
      await AppState.replaceRows(rows);
    } catch (error) {
      renderWorkspace();
      UI.setMessage("qualityMessage", I18n.t("data.saveError", { error: error.message }), "error");
      return;
    }
    currentPage = 1;
    renderWorkspace();
    UI.setMessage("qualityMessage", I18n.t(messageKey, { count: removed, suffix: removed === 1 ? "" : "s" }));
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
    return saveCleanedRows(rows, "data.removedDuplicates");
  }

  function removeRowsWithMissingValues() {
    const { dataset } = datasetState();
    const rows = dataset.data.filter((row) => dataset.columns.every((column) => hasValue(row[column])));
    return saveCleanedRows(rows, "data.removedMissing");
  }

  function fileError(file) {
    if (!file) return I18n.t("data.chooseFile");
    if (!file.name.toLowerCase().endsWith(".csv")) return I18n.t("data.notCsv");
    if (file.size === 0) return I18n.t("data.emptyFile");
    if (file.size > MAX_FILE_SIZE_BYTES) {
      const toMegabytes = (bytes) => UI.formatNumber(bytes / (1024 * 1024));
      return I18n.t("data.tooLarge", { size: toMegabytes(file.size), max: toMegabytes(MAX_FILE_SIZE_BYTES) });
    }
    return "";
  }

  async function uploadSelectedFile(event) {
    event.preventDefault();
    const input = document.getElementById("fileInput");
    const button = document.getElementById("uploadButton");
    const file = input.files?.[0];
    const error = fileError(file);
    if (error) {
      UI.setMessage("uploadMessage", error, "error");
      return;
    }

    button.disabled = true;
    button.textContent = I18n.t("data.uploading");
    UI.setMessage("uploadMessage", I18n.t("data.analysing"), "info");
    try {
      await AppState.create(file);
      await refreshLibrary();
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
    document.getElementById("uploadForm").addEventListener("submit", uploadSelectedFile);
    document.getElementById("fileInput").addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      UI.setMessage("uploadMessage", file ? fileError(file) : "", "error");
    });
    document.getElementById("datasetSelect").addEventListener("change", async (event) => {
      // Read the choice before whileBusy re-renders the select.
      const datasetId = event.target.value;
      if (!datasetId) return;
      UI.setMessage("libraryMessage", I18n.t("data.loading"), "info");
      try {
        await whileBusy(() => AppState.load(datasetId));
        currentPage = 1;
        UI.setMessage("libraryMessage", "");
      } catch (error) {
        UI.setMessage("libraryMessage", error.message, "error");
      }
      renderWorkspace();
    });
    document.getElementById("deleteDataset").addEventListener("click", async () => {
      const { dataset } = datasetState();
      if (!dataset || !window.confirm(I18n.t("data.confirmDelete", { name: dataset.filename }))) return;
      try {
        await whileBusy(async () => {
          await AppState.deleteDataset(dataset.id);
          await refreshLibrary();
        });
        UI.setMessage("libraryMessage", "");
        UI.setMessage("uploadMessage", I18n.t("data.deleted", { name: dataset.filename }));
      } catch (error) {
        UI.setMessage("libraryMessage", error.message, "error");
      }
      renderWorkspace();
    });
    document.getElementById("datasetTable").addEventListener("click", (event) => {
      const button = event.target.closest("[data-preview-page]");
      if (!button) return;
      currentPage += button.dataset.previewPage === "next" ? 1 : -1;
      renderPreview(datasetState().dataset);
    });
    document.getElementById("semanticTable").addEventListener("change", async (event) => {
      const select = event.target.closest("[data-semantic]");
      if (!select) return;
      select.disabled = true;
      try {
        await AppState.updateSemantic(select.dataset.column, select.dataset.semantic, select.value);
        UI.setMessage("semanticMessage", "");
      } catch (error) {
        // Re-rendering below restores the last saved value.
        UI.setMessage("semanticMessage", I18n.t("data.saveError", { error: error.message }), "error");
      }
      renderSemanticReview(datasetState().dataset, datasetState().semanticModel);
    });
    document.getElementById("qualityReport").addEventListener("click", (event) => {
      const button = event.target.closest("[data-clean]");
      if (!button) return;
      if (button.dataset.clean === "duplicates") removeDuplicates();
      if (button.dataset.clean === "missing") removeRowsWithMissingValues();
    });
  }

  async function initialise() {
    if (!UI.initialiseShell("data")) return;
    bindEvents();
    renderWorkspace();
    await refreshLibrary();
    renderWorkspace();
  }

  return { initialise };
})();

window.addEventListener("DOMContentLoaded", DataWorkspace.initialise);
