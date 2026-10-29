/* Session-scoped dataset library. Each upload owns its data, semantic review,
 * and dashboard so switching a dataset cannot mix incompatible fields. */
const AppState = (() => {
  const KEY = "revenue-analytics-session-v1";

  const emptyStore = () => ({ version: 2, activeDatasetId: null, datasets: [] });
  const createId = (prefix) => globalThis.crypto?.randomUUID?.() || `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  function normalizeStore(parsed) {
    if (Array.isArray(parsed?.datasets)) {
      const datasets = parsed.datasets.filter((entry) => entry?.id && entry?.dataset).map((entry) => ({
        id: entry.id,
        dataset: entry.dataset,
        semanticModel: entry.semanticModel || {},
        dashboard: Array.isArray(entry.dashboard) ? entry.dashboard : [],
        createdAt: entry.createdAt || entry.dataset.updatedAt || new Date().toISOString(),
      }));
      const activeDatasetId = datasets.some((entry) => entry.id === parsed.activeDatasetId)
        ? parsed.activeDatasetId
        : datasets.at(-1)?.id || null;
      return { version: 2, activeDatasetId, datasets };
    }
    // Transparently retain the single dataset from earlier versions.
    if (parsed?.dataset) {
      const id = createId("dataset");
      return {
        version: 2,
        activeDatasetId: id,
        datasets: [{ id, dataset: parsed.dataset, semanticModel: parsed.semanticModel || {}, dashboard: Array.isArray(parsed.dashboard) ? parsed.dashboard : [], createdAt: parsed.dataset.updatedAt || new Date().toISOString() }],
      };
    }
    return emptyStore();
  }

  function readStore() {
    try {
      const stored = sessionStorage.getItem(KEY);
      return stored ? normalizeStore(JSON.parse(stored)) : emptyStore();
    } catch {
      return emptyStore();
    }
  }

  function writeStore(next) {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(next));
    } catch (error) {
      if (error?.name === "QuotaExceededError") {
        throw new Error("This browser session has no space for another dataset. Use smaller CSV files or start a new browser session.");
      }
      throw new Error("The browser could not save this dataset for the other workspaces.");
    }
    return project(next);
  }

  function activeEntry(store) {
    return store.datasets.find((entry) => entry.id === store.activeDatasetId) || null;
  }

  function summaries(store) {
    return store.datasets.map((entry) => ({
      id: entry.id,
      filename: entry.dataset.filename,
      rows: entry.dataset.rows,
      columns: entry.dataset.columns.length,
      createdAt: entry.createdAt,
      updatedAt: entry.dataset.updatedAt || entry.createdAt,
    }));
  }

  function project(store) {
    const active = activeEntry(store);
    return {
      dataset: active?.dataset || null,
      semanticModel: active?.semanticModel || {},
      dashboard: active?.dashboard || [],
      activeDatasetId: store.activeDatasetId,
      datasets: summaries(store),
    };
  }

  function read() {
    return project(readStore());
  }

  function activeDataset() {
    return read().dataset;
  }

  function setDataset(dataset, semanticModel) {
    const store = readStore();
    const now = new Date().toISOString();
    const normalized = {
      filename: dataset.filename,
      rows: dataset.rows,
      columns: dataset.columns,
      data: dataset.data,
      rawData: dataset.raw_data || dataset.data,
      profiles: dataset.profiles || {},
      updatedAt: now,
    };
    const id = createId("dataset");
    store.datasets.push({ id, dataset: normalized, semanticModel, dashboard: [], createdAt: now });
    store.activeDatasetId = id;
    return writeStore(store);
  }

  function selectDataset(id) {
    const store = readStore();
    if (!store.datasets.some((entry) => entry.id === id)) return project(store);
    store.activeDatasetId = id;
    return writeStore(store);
  }

  function updateActive(mutator) {
    const store = readStore();
    const active = activeEntry(store);
    if (!active) return project(store);
    mutator(active);
    return writeStore(store);
  }

  function updateSemantic(column, property, value) {
    return updateActive((active) => {
      if (!active.semanticModel[column]) return;
      active.semanticModel[column][property] = value;
      active.semanticModel[column].confidence = "user-reviewed";
    });
  }

  function replaceRows(rows) {
    return updateActive((active) => {
      active.dataset.data = rows;
      active.dataset.rows = rows.length;
      active.dataset.updatedAt = new Date().toISOString();
    });
  }

  function addVisual(visual) {
    return updateActive((active) => {
      active.dashboard.push({ ...visual, id: createId("visual"), createdAt: new Date().toISOString() });
    });
  }

  function removeVisual(id) {
    return updateActive((active) => {
      active.dashboard = active.dashboard.filter((visual) => visual.id !== id);
    });
  }

  function moveVisual(id, direction) {
    return updateActive((active) => {
      const index = active.dashboard.findIndex((visual) => visual.id === id);
      const destination = index + direction;
      if (index < 0 || destination < 0 || destination >= active.dashboard.length) return;
      [active.dashboard[index], active.dashboard[destination]] = [active.dashboard[destination], active.dashboard[index]];
    });
  }

  function clear() {
    sessionStorage.removeItem(KEY);
  }

  return { read, activeDataset, setDataset, selectDataset, updateSemantic, replaceRows, addVisual, removeVisual, moveVisual, clear };
})();
