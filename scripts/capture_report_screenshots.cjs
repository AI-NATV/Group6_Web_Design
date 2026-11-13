// Capture report UI evidence from an isolated Chrome remote-debugging session.
// Usage: node scripts/capture_report_screenshots.cjs [app URL] [debug port]
// The app must use a disposable database; this script creates a throwaway account and dataset.
const fs = require("node:fs");
const path = require("node:path");

const appUrl = process.argv[2] || "http://127.0.0.1:8017";
const debugPort = process.argv[3] || "9228";
const outputDirectory = path.resolve("report_screenshots");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
  const tab = await (await fetch(`http://127.0.0.1:${debugPort}/json/new?about:blank`, { method: "PUT" })).json();
  const socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });

  let nextId = 0;
  const pending = new Map();
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (!message.id) return;
    const waiter = pending.get(message.id);
    if (!waiter) return;
    clearTimeout(waiter.timer);
    pending.delete(message.id);
    message.error ? waiter.reject(new Error(JSON.stringify(message.error))) : waiter.resolve(message.result);
  };

  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for ${method}`));
    }, 30000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });

  async function evaluate(expression) {
    const response = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
    return response.result.value;
  }

  async function until(expression) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      try {
        if (await evaluate(expression)) return;
      } catch {
        // Navigation replaces the execution context.
      }
      await sleep(250);
    }
    throw new Error(`Browser condition timed out: ${expression}`);
  }

  async function navigate(pathname, condition) {
    await send("Page.navigate", { url: `${appUrl}${pathname}` });
    await until(`document.readyState === 'complete' && (${condition})`);
  }

  async function setViewport(width, height, mobile) {
    await send("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile,
    });
    await sleep(350);
  }

  async function capture(name) {
    const shot = await send("Page.captureScreenshot", { format: "png", fromSurface: true });
    fs.writeFileSync(path.join(outputDirectory, `${name}.png`), Buffer.from(shot.data, "base64"));
    console.log(`Captured ${name}.png`);
  }

  async function scrollTo(selector) {
    await evaluate(`(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      window.scrollTo(0, Math.max(0, element.getBoundingClientRect().top + window.scrollY - 90));
    })()`);
    await sleep(350);
  }

  fs.mkdirSync(outputDirectory, { recursive: true });
  await send("Runtime.enable");
  await send("Page.enable");
  await setViewport(1440, 1000, false);

  await navigate("/app/login.html", "!!document.getElementById('loginForm')");
  await scrollTo("#login");
  await capture("login_desktop");

  await setViewport(390, 844, true);
  await scrollTo("#login");
  await capture("login_mobile");

  await setViewport(1440, 1000, false);
  await navigate("/app/register.html", "!!document.getElementById('registerForm')");
  await scrollTo("#registerForm");
  await capture("register_desktop");

  await setViewport(390, 844, true);
  await scrollTo("#registerForm");
  await capture("register_mobile");

  await setViewport(1440, 1000, false);
  await navigate("/app/login.html", "typeof Api !== 'undefined' && typeof Auth !== 'undefined'");
  const email = `report-${Date.now()}@example.com`;
  await evaluate(`(async () => {
    await Api.register(${JSON.stringify(email)}, "report-demo-password-123");
    Auth.setToken((await Api.login(${JSON.stringify(email)}, "report-demo-password-123")).access_token);
    Auth.setUser(await Api.me());
  })()`);

  await navigate("/app/", "typeof AppState !== 'undefined' && !!document.getElementById('uploadForm')");
  const csv = fs.readFileSync(path.resolve("sample_sales.csv"), "utf8");
  await evaluate(`(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([${JSON.stringify(csv)}], "report-sample-sales.csv", {type: "text/csv"}));
    const input = document.getElementById("fileInput");
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", {bubbles: true}));
    document.getElementById("uploadForm").requestSubmit();
  })()`);
  await until("AppState.activeDataset()?.filename === 'report-sample-sales.csv'");
  await scrollTo("#overviewHeading");
  await capture("data_desktop");

  await setViewport(390, 844, true);
  await scrollTo("#overviewHeading");
  await capture("data_mobile");

  await setViewport(1440, 1000, false);
  await navigate("/app/visualize.html", "typeof VisualizeWorkspace !== 'undefined' && !document.getElementById('visualizeApp').hidden");
  await evaluate(`(() => {
    const dimension = document.querySelector('[data-well-select="dimension"]');
    dimension.value = "region";
    dimension.dispatchEvent(new Event("change", {bubbles: true}));
    const measure = document.querySelector('[data-well-select="measure"]');
    measure.value = "revenue";
    measure.dispatchEvent(new Event("change", {bubbles: true}));
    document.getElementById("generateChart").click();
  })()`);
  await until("document.getElementById('addToDashboard') && !document.getElementById('addToDashboard').disabled");
  await evaluate("document.getElementById('addToDashboard').click()");
  await until("document.querySelector('#savedVisuals article')");
  await capture("visualize_desktop");

  await setViewport(390, 844, true);
  await capture("visualize_mobile");

  await setViewport(1440, 1000, false);
  await navigate("/app/forecast.html", "typeof ForecastWorkspace !== 'undefined' && !document.getElementById('forecastApp').hidden");
  await evaluate(`(() => {
    const time = document.getElementById("forecastTime");
    time.value = "date";
    time.dispatchEvent(new Event("change", {bubbles: true}));
    const target = document.getElementById("forecastTarget");
    target.value = "revenue";
    target.dispatchEvent(new Event("change", {bubbles: true}));
    document.getElementById("forecastHorizon").value = "7";
    document.getElementById("forecastHorizon").dispatchEvent(new Event("input", {bubbles: true}));
  })()`);
  await capture("forecast_desktop");

  await setViewport(390, 844, true);
  await capture("forecast_mobile");

  await setViewport(1440, 1000, false);
  await evaluate("document.getElementById('runForecast').click()");
  await until("!document.getElementById('forecastResults').hidden && !document.getElementById('forecastControls').disabled");
  await scrollTo("#forecastEvaluationSection");
  await capture("forecast_results_desktop");

  await setViewport(390, 844, true);
  await scrollTo("#forecastEvaluationSection");
  await capture("forecast_results_mobile");

  console.log(JSON.stringify({ account: email, screenshots: fs.readdirSync(outputDirectory).filter((name) => name.endsWith(".png")) }));
  await send("Page.close");
  socket.close();
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
