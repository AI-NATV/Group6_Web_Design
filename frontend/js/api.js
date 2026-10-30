const Api = (() => {
  function baseUrl() {
    const configured = document.querySelector('meta[name="api-base"]')?.content?.trim();
    if (configured && configured !== "auto") return configured.replace(/\/$/, "");

    const host = window.location.hostname;
    const sameOriginApp = window.location.protocol.startsWith("http")
      && (window.location.port === "8000" || (host !== "localhost" && host !== "127.0.0.1"));
    return sameOriginApp ? window.location.origin : "http://127.0.0.1:8000";
  }

  const LOGIN_PATH = "/api/v1/token";

  async function request(path, options = {}) {
    const token = Auth.token();
    const response = await fetch(`${baseUrl()}${path}`, {
      ...options,
      headers: {
        "X-Request-ID": globalThis.crypto?.randomUUID?.() || String(Date.now()),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
    });
    // 401 = not (or no longer) logged in: send the user to the login page. A failed login itself is just an error.
    if (response.status === 401 && path !== LOGIN_PATH) {
      Auth.handleUnauthorized();
    }
    let body = null;
    try {
      body = await response.json();
    } catch {
      // A non-JSON response is still represented by the HTTP status below.
    }
    if (!response.ok) {
      const detail = body?.detail;
      throw new Error(Array.isArray(detail)
        ? detail.map((item) => `${item.loc?.slice(1).join(".") || "Request"}: ${item.msg}`).join("; ")
        : detail || "The server could not complete that request.");
    }
    return body;
  }

  const json = (method, payload) => ({
    method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });

  return {
    health: () => request("/health"),
    // OAuth2 password flow: the login is a form (username, password), not JSON.
    login: (username, password) => request(LOGIN_PATH, { method: "POST", body: new URLSearchParams({ username, password }) }),
    register: (username, password) => request("/api/v1/register", json("POST", { username, password })),
    me: () => request("/api/v1/me"),
    // Datasets and their dashboard visuals are stored in the server database.
    listDatasets: () => request("/api/v1/datasets?limit=100"),
    getDataset: (id) => request(`/api/v1/datasets/${encodeURIComponent(id)}`),
    createDataset: (file) => {
      const body = new FormData();
      body.append("file", file);
      return request("/api/v1/datasets", { method: "POST", body });
    },
    updateDataset: (id, changes) => request(`/api/v1/datasets/${encodeURIComponent(id)}`, json("PATCH", changes)),
    deleteDataset: (id) => request(`/api/v1/datasets/${encodeURIComponent(id)}`, { method: "DELETE" }),
    listVisuals: (datasetId) => request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/visuals`),
    createVisual: (datasetId, visual) => request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/visuals`, json("POST", visual)),
    moveVisual: (id, position) => request(`/api/v1/visuals/${encodeURIComponent(id)}`, json("PATCH", { position })),
    deleteVisual: (id) => request(`/api/v1/visuals/${encodeURIComponent(id)}`, { method: "DELETE" }),
    forecast: (payload) => request("/forecast", json("POST", payload)),
  };
})();
