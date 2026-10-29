// Browser integration check using Node 22+ and an isolated Chromium debugging
// session. Usage: node scripts/check_forecast_browser.cjs [app URL] [debug port]
// Starts no processes itself and uses a new tab. Do not point at a user's tab.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const appUrl = process.argv[2] || "http://127.0.0.1:8017";
const debugPort = process.argv[3] || "9228";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
  const tab = await (await fetch(`http://127.0.0.1:${debugPort}/json/new?about:blank`, { method: "PUT" })).json();
  const socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let id = 0;
  const pending = new Map();
  const exceptions = [];
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text);
    if (!message.id) return;
    const waiter = pending.get(message.id);
    if (!waiter) return;
    clearTimeout(waiter.timer);
    pending.delete(message.id);
    message.error ? waiter.reject(new Error(JSON.stringify(message.error))) : waiter.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const next = ++id;
    const timer = setTimeout(() => { pending.delete(next); reject(new Error(`Timeout: ${method}`)); }, 30000);
    pending.set(next, { resolve, reject, timer });
    socket.send(JSON.stringify({ id: next, method, params }));
  });
  async function evaluate(expression) {
    const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function until(expression) {
    for (let attempt = 0; attempt < 120; attempt++) {
      try { if (await evaluate(expression)) return; } catch { /* navigation replaces context */ }
      await pause(250);
    }
    throw new Error(`Browser condition timed out: ${expression}`);
  }
  const setBase = `document.querySelector('meta[name="api-base"]').content = ${JSON.stringify(appUrl)}`;
  try {
    await send("Runtime.enable");
    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url: `${appUrl}/app/` });
    await until("document.readyState === 'complete' && typeof AppState !== 'undefined' && !!document.getElementById('uploadButton')");
    await evaluate(setBase);
    await evaluate(`(() => {
      const rows = Array.from({length: 120}, (_, index) => {
        const day = new Date(Date.UTC(2025, 0, index + 1)).toISOString().slice(0, 10);
        return day + ',$' + (100 + index + 0.125).toFixed(3);
      }).reverse();
      const csv = 'Date,Close\\n' + rows.join('\\n');
      const transfer = new DataTransfer();
      transfer.items.add(new File([csv], 'forecast-browser-test.csv', {type:'text/csv'}));
      document.getElementById('fileInput').files = transfer.files;
      document.getElementById('uploadButton').click();
    })()`);
    await until("AppState.activeDataset()?.rows === 120");
    assert.equal(await evaluate("AppState.activeDataset().data[0].Close"), 219.125);
    await evaluate(`(() => {
      const csv = 'Date,Close\\n2026-01-01,10\\n2026-01-02,11';
      const transfer = new DataTransfer();
      transfer.items.add(new File([csv], 'second-session-dataset.csv', {type:'text/csv'}));
      document.getElementById('fileInput').files = transfer.files;
      document.getElementById('uploadButton').click();
    })()`);
    await until("AppState.read().datasets.length === 2");
    assert.equal(await evaluate("document.querySelectorAll('#datasetSelect option').length"), 2);
    assert.equal(await evaluate("AppState.activeDataset().filename"), "second-session-dataset.csv");
    await evaluate("document.getElementById('datasetSelect').value = AppState.read().datasets[0].id; document.getElementById('datasetSelect').dispatchEvent(new Event('change', {bubbles:true}))");
    await until("AppState.activeDataset().filename === 'forecast-browser-test.csv'");
    await send("Page.navigate", { url: `${appUrl}/app/forecast.html` });
    await until("document.readyState === 'complete' && typeof ForecastWorkspace !== 'undefined' && !document.getElementById('forecastApp').hidden");
    await evaluate(`${setBase}; UI.initialiseShell('forecast')`);
    await evaluate("document.getElementById('forecastHelp').click()");
    assert.equal(await evaluate("!document.getElementById('forecastHelpPanel').hidden && document.getElementById('forecastHelp').getAttribute('aria-expanded') === 'true'"), true);
    await evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))");
    assert.equal(await evaluate("document.getElementById('forecastHelpPanel').hidden"), true);
    assert.equal(await evaluate("document.getElementById('runForecast').disabled"), true, "Explicit target required");
    await evaluate("document.getElementById('forecastTarget').value = 'Close'; document.getElementById('forecastTarget').dispatchEvent(new Event('input', {bubbles:true})); document.getElementById('runForecast').click()");
    await until("!document.getElementById('forecastResults').hidden && !document.getElementById('forecastControls').disabled");
    assert.equal(await evaluate("document.querySelectorAll('#forecastTable tbody tr').length"), 7);
    assert.equal(await evaluate("document.querySelectorAll('#forecastComparison tbody tr').length"), 3);
    assert.equal(await evaluate("document.querySelectorAll('#backtestTable tbody tr').length"), 7);
    assert.match(await evaluate("document.getElementById('forecastSummary').textContent"), /Holt damped trend/);
    const chartLoaded = await evaluate("typeof Chart !== 'undefined'");
    if (chartLoaded) {
      const labels = await evaluate("Chart.getChart(document.getElementById('forecastChart')).data.labels");
      assert.equal(labels[0], "2025-01-01");
      assert.equal(labels.at(-1), "2025-05-07");
    }
    fs.mkdirSync(path.resolve('.tmp-forecast-qa'), { recursive: true });
    const { cssContentSize } = await send("Page.getLayoutMetrics");
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: cssContentSize.width, height: cssContentSize.height, scale: 1 } });
    fs.writeFileSync(path.resolve('.tmp-forecast-qa/forecast.png'), Buffer.from(shot.data, 'base64'));
    await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
    await pause(500); // allow Chart.js ResizeObserver and browser layout to settle
    const overflow = await evaluate("Array.from(document.querySelectorAll('body *')).filter(e => e.getBoundingClientRect().right > innerWidth && getComputedStyle(e).position !== 'absolute').slice(0, 12).map(e => ({tag:e.tagName,id:e.id,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width}))");
    if (await evaluate("document.documentElement.scrollWidth > window.innerWidth")) console.log({overflow});
    assert.equal(await evaluate("document.documentElement.scrollWidth <= window.innerWidth"), true, "No page overflow on mobile");
    await evaluate("document.getElementById('forecastHorizon').value = '90'; document.getElementById('forecastHorizon').dispatchEvent(new Event('input', {bubbles:true}))");
    assert.equal(await evaluate("document.getElementById('forecastResults').hidden && document.getElementById('runForecast').disabled"), true);
    await evaluate(`(() => {
      const state = AppState.read(); state.dataset.data[0].Close = null;
      AppState.setDataset(state.dataset, state.semanticModel);
      document.getElementById('forecastHorizon').value = '7';
      document.getElementById('forecastHorizon').dispatchEvent(new Event('input', {bubbles:true}));
      document.getElementById('runForecast').click();
    })()`);
    await until("!document.getElementById('forecastControls').disabled && !!document.querySelector('#forecastMessage .error')");
    assert.equal(await evaluate("document.getElementById('forecastResults').hidden"), true);
    assert.match(await evaluate("document.getElementById('forecastMessage').textContent"), /invalid\/missing/);
    assert.deepEqual(exceptions, []);
    console.log(JSON.stringify({ passed: true, chartLoaded, checks: ['CSV upload', 'multiple session datasets', 'dataset switching', 'precision preservation', 'forecast help', 'target selection', 'live forecast API', 'comparison and test tables', 'chronological chart', 'mobile layout', 'stale-result removal', 'insufficient-history gating', 'API error recovery'], screenshot: '.tmp-forecast-qa/forecast.png' }));
  } finally {
    await send("Page.close");
    socket.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
