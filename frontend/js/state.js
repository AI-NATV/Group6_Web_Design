/* The server database is the source of truth for datasets, their semantic
 * review and their dashboards. This module keeps a copy of the active dataset
 * in sessionStorage so the Data, Visualize and Forecast pages can read it
 * synchronously after navigation; every change is saved to the API first. */
const AppState = (() => {
  const KEY = "revenue-analytics-active-v3";
  const LEGACY_KEY = "revenue-analytics-session-v1";

  // Earlier versions kept every dataset in the browser; free that space.
  try {
    sessionStorage.removeItem(LEGACY_KEY);
  } catch {
    // Storage can be unavailable (e.g. blocked site data); the cache below copes with that.
  }

  const sameId = (left, right) => String(left) === String(right);

  function readCache() {
    try {
      const stored = JSON.parse(sessionStorage.getItem(KEY));
      return stored?.dataset?.id ? stored : null;
    } catch {
      return null;
    }
  }

  function writeCache(entry) {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(entry));
    } catch (error) {
      if (error?.name === "QuotaExceededError") {
        throw new Error("The dataset is saved on the server, but it is too large for this browser's session storage. Use a smaller CSV file.");
      }
      throw new Error("The browser could not keep this dataset for the other workspaces.");
    }
    return project(entry);
  }

  function project(entry) {
    return {
      dataset: entry?.dataset || null,
      semanticModel: entry?.semanticModel || {},
      dashboard: entry?.dashboard || [],
      activeDatasetId: entry?.dataset?.id ?? null,
    };
  }

  function toVisual(visual) {
    return {
      id: visual.id,
      chartType: visual.chart_type,
      fields: visual.fields,
      aggregation: visual.aggregation,
      createdAt: visual.created_at,
    };
  }

  function toEntry(dataset, visuals) {
    return {
      dataset: {
        id: dataset.id,
        filename: dataset.filename,
        rows: dataset.rows,
        columns: dataset.columns,
        data: dataset.data,
        rawData: dataset.raw_data || dataset.data,
        profiles: dataset.profiles || {},
        createdAt: dataset.created_at,
        updatedAt: dataset.updated_at,
      },
      semanticModel: dataset.semantic_model || {},
      dashboard: visuals.map(toVisual),
    };
  }

  // Datasets added outside the UI (e.g. the seed script) have no semantic review yet.
  async function withSemanticReview(dataset) {
    if (Object.keys(dataset.semantic_model || {}).length) return dataset;
    const semanticModel = Semantic.analyze(dataset.data, dataset.columns, dataset.profiles || {});
    return Api.updateDataset(dataset.id, { semantic_model: semanticModel });
  }

  function requireActive() {
    const entry = readCache();
    if (!entry) throw new Error("Choose a dataset first.");
    return entry;
  }

  function read() {
    return project(readCache());
  }

  function activeDataset() {
    return read().dataset;
  }

  async function create(file) {
    const dataset = await withSemanticReview(await Api.createDataset(file));
    return writeCache(toEntry(dataset, []));
  }

  async function load(id) {
    const [dataset, visuals] = await Promise.all([Api.getDataset(id), Api.listVisuals(id)]);
    return writeCache(toEntry(await withSemanticReview(dataset), visuals));
  }

  async function updateSemantic(column, property, value) {
    const entry = requireActive();
    if (!entry.semanticModel[column]) return project(entry);
    const semanticModel = structuredClone(entry.semanticModel);
    semanticModel[column][property] = value;
    semanticModel[column].confidence = "user-reviewed";
    const saved = await Api.updateDataset(entry.dataset.id, { semantic_model: semanticModel });
    entry.semanticModel = saved.semantic_model;
    entry.dataset.updatedAt = saved.updated_at;
    return writeCache(entry);
  }

  async function replaceRows(rows) {
    const entry = requireActive();
    const saved = await Api.updateDataset(entry.dataset.id, { data: rows });
    entry.dataset.data = saved.data;
    entry.dataset.rows = saved.rows;
    entry.dataset.updatedAt = saved.updated_at;
    return writeCache(entry);
  }

  async function addVisual(visual) {
    const entry = requireActive();
    const saved = await Api.createVisual(entry.dataset.id, {
      chart_type: visual.chartType, fields: visual.fields, aggregation: visual.aggregation,
    });
    entry.dashboard.push(toVisual(saved));
    return writeCache(entry);
  }

  async function removeVisual(id) {
    const entry = requireActive();
    await Api.deleteVisual(id);
    entry.dashboard = entry.dashboard.filter((visual) => !sameId(visual.id, id));
    return writeCache(entry);
  }

  async function moveVisual(id, direction) {
    const entry = requireActive();
    const index = entry.dashboard.findIndex((visual) => sameId(visual.id, id));
    const destination = index + direction;
    if (index < 0 || destination < 0 || destination >= entry.dashboard.length) return project(entry);
    await Api.moveVisual(id, destination);
    entry.dashboard = (await Api.listVisuals(entry.dataset.id)).map(toVisual);
    return writeCache(entry);
  }

  async function deleteDataset(id) {
    await Api.deleteDataset(id);
    if (sameId(readCache()?.dataset.id, id)) clear();
  }

  function clear() {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      // Nothing cached.
    }
  }

  return { read, activeDataset, create, load, updateSemantic, replaceRows, addVisual, removeVisual, moveVisual, deleteDataset, clear };
})();
