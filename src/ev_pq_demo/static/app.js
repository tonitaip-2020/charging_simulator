const state = {
  scenarios: [],
  policies: [],
  glossary: [],
  runs: [],
  currentResult: null,
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  bindElements();
  attachEvents();
  bootstrap();
});

function bindElements() {
  els.scenarioSelect = document.getElementById("scenarioSelect");
  els.policySelect = document.getElementById("policySelect");
  els.seedInput = document.getElementById("seedInput");
  els.durationInput = document.getElementById("durationInput");
  els.stepInput = document.getElementById("stepInput");
  els.labelInput = document.getElementById("labelInput");
  els.transformerInput = document.getElementById("transformerInput");
  els.feederInput = document.getElementById("feederInput");
  els.baseLoadInput = document.getElementById("baseLoadInput");
  els.reserveInput = document.getElementById("reserveInput");
  els.acConnectorsInput = document.getElementById("acConnectorsInput");
  els.acPowerInput = document.getElementById("acPowerInput");
  els.acPhasesInput = document.getElementById("acPhasesInput");
  els.dcConnectorsInput = document.getElementById("dcConnectorsInput");
  els.dcPowerInput = document.getElementById("dcPowerInput");
  els.thdInput = document.getElementById("thdInput");
  els.statusLine = document.getElementById("statusLine");
  els.scenarioDescription = document.getElementById("scenarioDescription");
  els.policyDescription = document.getElementById("policyDescription");
  els.runButton = document.getElementById("runButton");
  els.summaryCards = document.getElementById("summaryCards");
  els.resultTitle = document.getElementById("resultTitle");
  els.resultHeadline = document.getElementById("resultHeadline");
  els.loadChart = document.getElementById("loadChart");
  els.loadingChart = document.getElementById("loadingChart");
  els.pqChart = document.getElementById("pqChart");
  els.takeawayList = document.getElementById("takeawayList");
  els.glossaryGrid = document.getElementById("glossaryGrid");
  els.sessionTable = document.getElementById("sessionTable");
  els.comparisonTable = document.getElementById("comparisonTable");
}

function attachEvents() {
  els.scenarioSelect.addEventListener("change", () => {
    applyScenarioDefaults();
    updateScenarioDescription();
  });
  els.policySelect.addEventListener("change", updatePolicyDescription);
  els.runButton.addEventListener("click", runSimulation);
}

async function bootstrap() {
  try {
    const response = await fetch("/api/scenarios");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to load scenarios.");
    }

    state.scenarios = payload.scenarios || [];
    state.policies = payload.policies || [];
    state.glossary = payload.glossary || [];

    populateScenarioSelect();
    populatePolicySelect();
    renderGlossary(state.glossary);
    applyScenarioDefaults();
    updateScenarioDescription();
    updatePolicyDescription();
    setStatus("Presets loaded. Ready to simulate.");
    runSimulation();
  } catch (error) {
    setStatus(error.message || "Unable to load the app.");
  }
}

function populateScenarioSelect() {
  els.scenarioSelect.innerHTML = "";
  state.scenarios.forEach((scenario) => {
    const option = document.createElement("option");
    option.value = scenario.key;
    option.textContent = scenario.name;
    els.scenarioSelect.appendChild(option);
  });
}

function populatePolicySelect() {
  els.policySelect.innerHTML = "";
  state.policies.forEach((policy) => {
    const option = document.createElement("option");
    option.value = policy.key;
    option.textContent = policy.label;
    els.policySelect.appendChild(option);
  });
}

function applyScenarioDefaults() {
  const scenario = getSelectedScenario();
  if (!scenario) {
    return;
  }

  const site = scenario.recommended_site || {};
  els.durationInput.value = scenario.default_duration_hours;
  els.stepInput.value = scenario.default_step_minutes;
  els.policySelect.value = scenario.default_policy;
  els.transformerInput.value = site.transformer_limit_kw ?? "";
  els.feederInput.value = site.feeder_limit_kw ?? "";
  els.baseLoadInput.value = site.base_load_kw ?? "";
  els.reserveInput.value = site.reserve_pct ?? "";
  els.acConnectorsInput.value = site.ac_connectors ?? "";
  els.acPowerInput.value = site.ac_power_kw ?? "";
  els.acPhasesInput.value = String(site.ac_phases ?? 3);
  els.dcConnectorsInput.value = site.dc_connectors ?? "";
  els.dcPowerInput.value = site.dc_power_kw ?? "";
  els.thdInput.value = site.background_thd_pct ?? "";
  els.labelInput.value = "";
}

function updateScenarioDescription() {
  const scenario = getSelectedScenario();
  if (!scenario) {
    els.scenarioDescription.textContent = "";
    return;
  }
  els.scenarioDescription.textContent = `${scenario.description} ${scenario.plain_language}`;
}

function updatePolicyDescription() {
  const policy = getSelectedPolicy();
  els.policyDescription.textContent = policy ? policy.description : "";
}

function getSelectedScenario() {
  return state.scenarios.find((scenario) => scenario.key === els.scenarioSelect.value) || null;
}

function getSelectedPolicy() {
  return state.policies.find((policy) => policy.key === els.policySelect.value) || null;
}

function collectPayload() {
  const scenario = getSelectedScenario();
  return {
    scenario_key: scenario ? scenario.key : "office_commute",
    policy: els.policySelect.value,
    seed: Number(els.seedInput.value || 7),
    duration_hours: Number(els.durationInput.value || 24),
    step_minutes: Number(els.stepInput.value || 15),
    label: els.labelInput.value.trim(),
    site: {
      transformer_limit_kw: Number(els.transformerInput.value || 0),
      feeder_limit_kw: Number(els.feederInput.value || 0),
      base_load_kw: Number(els.baseLoadInput.value || 0),
      reserve_pct: Number(els.reserveInput.value || 0),
      ac_connectors: Number(els.acConnectorsInput.value || 0),
      ac_power_kw: Number(els.acPowerInput.value || 0),
      ac_phases: Number(els.acPhasesInput.value || 3),
      dc_connectors: Number(els.dcConnectorsInput.value || 0),
      dc_power_kw: Number(els.dcPowerInput.value || 0),
      background_thd_pct: Number(els.thdInput.value || 0),
    },
  };
}

async function runSimulation() {
  const scenario = getSelectedScenario();
  const policy = getSelectedPolicy();
  setStatus(`Running ${scenario ? scenario.name : "scenario"} with ${policy ? policy.label : "selected"} control...`);

  try {
    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectPayload()),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Simulation failed.");
    }

    state.currentResult = payload;
    rememberRun(payload);
    renderResult(payload);
    setStatus("Simulation finished.");
  } catch (error) {
    setStatus(error.message || "Simulation failed.");
  }
}

function rememberRun(result) {
  const summary = result.summary || {};
  const existingIndex = state.runs.findIndex((item) => item.label === result.label);
  const entry = {
    label: result.label,
    scenario: result.scenario ? result.scenario.name : "",
    policy: result.policy ? result.policy.label : "",
    peakSiteKw: summary.peak_site_kw,
    minVoltagePu: summary.min_voltage_pu,
    worstThdPct: summary.worst_thd_pct,
    completionRatePct: summary.completion_rate_pct,
  };

  if (existingIndex >= 0) {
    state.runs[existingIndex] = entry;
  } else {
    state.runs.unshift(entry);
    state.runs = state.runs.slice(0, 8);
  }
}

function renderResult(result) {
  const summary = result.summary || {};
  const scenarioName = result.scenario ? result.scenario.name : "Simulation";
  const policyName = result.policy ? result.policy.label : "Policy";
  els.resultTitle.textContent = `${scenarioName} with ${policyName}`;
  els.resultHeadline.textContent = result.headline || "";

  renderSummaryCards(summary);
  renderTakeaways(result.takeaways || []);
  renderSessionTable(result.top_sessions || []);
  renderComparisonTable();
  renderLineChart(els.loadChart, result.timeline || [], [
    { key: "site_kw", label: "Total site load", color: "#0d8f8d" },
    { key: "charging_kw", label: "Charging load", color: "#d56c2f" },
  ], "kW", 0);
  renderLineChart(els.loadingChart, result.timeline || [], [
    { key: "transformer_loading_pct", label: "Transformer", color: "#0d8f8d" },
    { key: "feeder_loading_pct", label: "Feeder", color: "#8f4727" },
  ], "%", 0);
  renderPqPanel(els.pqChart, result.timeline || []);
}

function renderSummaryCards(summary) {
  const cards = [
    {
      label: "Peak Site Load",
      value: `${fmt(summary.peak_site_kw, 1)} kW`,
      footnote: `Transformer peak ${fmt(summary.peak_transformer_loading_pct, 1)}%`,
    },
    {
      label: "Energy Delivered",
      value: `${fmt(summary.energy_delivered_kwh, 1)} kWh`,
      footnote: `Requested ${fmt(summary.energy_requested_kwh, 1)} kWh`,
    },
    {
      label: "Completion Rate",
      value: `${fmt(summary.completion_rate_pct, 1)}%`,
      footnote: `Unmet ${fmt(summary.unmet_energy_kwh, 1)} kWh`,
    },
    {
      label: "Minimum Voltage",
      value: `${fmt(summary.min_voltage_pu, 3)} p.u.`,
      footnote: `Lower means more local stress`,
    },
    {
      label: "Worst THD",
      value: `${fmt(summary.worst_thd_pct, 2)}%`,
      footnote: `Simple harmonic estimate`,
    },
    {
      label: "Average Wait",
      value: `${fmt(summary.average_wait_minutes, 1)} min`,
      footnote: `Peak queue ${fmt(summary.peak_queue, 0)} vehicles`,
    },
  ];

  els.summaryCards.innerHTML = cards.map((card) => `
    <div class="summary-card">
      <p class="metric-label">${escapeHtml(card.label)}</p>
      <p class="metric-value">${escapeHtml(card.value)}</p>
      <p class="metric-footnote">${escapeHtml(card.footnote)}</p>
    </div>
  `).join("");
}

function renderTakeaways(takeaways) {
  if (!takeaways.length) {
    els.takeawayList.innerHTML = `<li>No takeaways available.</li>`;
    return;
  }
  els.takeawayList.innerHTML = takeaways.map((text) => `<li>${escapeHtml(text)}</li>`).join("");
}

function renderGlossary(glossary) {
  els.glossaryGrid.innerHTML = glossary.map((item) => `
    <article class="glossary-card">
      <h4>${escapeHtml(item.term)}</h4>
      <p>${escapeHtml(item.meaning)}</p>
    </article>
  `).join("");
}

function renderSessionTable(rows) {
  if (!rows.length) {
    els.sessionTable.innerHTML = `<p class="empty-state">No stressed sessions to show yet.</p>`;
    return;
  }

  const body = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.session_id)}</td>
      <td><span class="pill ${row.unmet_kwh > 0 ? "warn" : ""}">${escapeHtml(row.mode)}</span></td>
      <td>${escapeHtml(row.arrival)}</td>
      <td>${escapeHtml(row.departure)}</td>
      <td>${fmt(row.requested_kwh, 1)}</td>
      <td>${fmt(row.delivered_kwh, 1)}</td>
      <td>${fmt(row.unmet_kwh, 1)}</td>
      <td>${fmt(row.wait_minutes, 0)}</td>
    </tr>
  `).join("");

  els.sessionTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Session</th>
          <th>Mode</th>
          <th>Arrival</th>
          <th>Departure</th>
          <th>Requested</th>
          <th>Delivered</th>
          <th>Unmet</th>
          <th>Wait</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function renderComparisonTable() {
  if (!state.runs.length) {
    els.comparisonTable.innerHTML = `<p class="empty-state">Run a few cases to compare them here.</p>`;
    return;
  }

  const body = state.runs.map((run) => `
    <tr>
      <td>${escapeHtml(run.label)}</td>
      <td>${escapeHtml(run.scenario)}</td>
      <td>${escapeHtml(run.policy)}</td>
      <td>${fmt(run.peakSiteKw, 1)}</td>
      <td>${fmt(run.minVoltagePu, 3)}</td>
      <td>${fmt(run.worstThdPct, 2)}</td>
      <td>${fmt(run.completionRatePct, 1)}%</td>
    </tr>
  `).join("");

  els.comparisonTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Run</th>
          <th>Scenario</th>
          <th>Policy</th>
          <th>Peak kW</th>
          <th>Min V</th>
          <th>Worst THD</th>
          <th>Completion</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function renderPqPanel(host, timeline) {
  host.innerHTML = `
    <div class="mini-chart-grid">
      <div class="mini-chart">
        <h4>Voltage</h4>
        <div data-chart="voltage"></div>
      </div>
      <div class="mini-chart">
        <h4>THD</h4>
        <div data-chart="thd"></div>
      </div>
      <div class="mini-chart">
        <h4>Phase Imbalance</h4>
        <div data-chart="imbalance"></div>
      </div>
    </div>
  `;

  renderLineChart(host.querySelector('[data-chart="voltage"]'), timeline, [
    { key: "voltage_pu", label: "Voltage", color: "#0d8f8d" },
  ], "", 0.9);
  renderLineChart(host.querySelector('[data-chart="thd"]'), timeline, [
    { key: "thd_pct", label: "THD", color: "#d56c2f" },
  ], "%", 0);
  renderLineChart(host.querySelector('[data-chart="imbalance"]'), timeline, [
    { key: "phase_imbalance_pct", label: "Phase imbalance", color: "#365a92" },
  ], "%", 0);
}

function renderLineChart(host, timeline, series, unitSuffix, explicitMin) {
  if (!timeline.length) {
    host.innerHTML = `<p class="empty-state">No data yet.</p>`;
    return;
  }

  const width = 760;
  const height = 280;
  const margin = { top: 18, right: 22, bottom: 34, left: 52 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const values = timeline.flatMap((point) => series.map((line) => Number(point[line.key]) || 0));
  const minValue = explicitMin === null ? Math.min(...values) : (explicitMin ?? Math.min(...values));
  const maxValue = Math.max(...values);
  const paddedMin = minValue === maxValue ? minValue - 1 : minValue - (maxValue - minValue) * 0.08;
  const paddedMax = minValue === maxValue ? maxValue + 1 : maxValue + (maxValue - minValue) * 0.12;
  const yMin = explicitMin === 0 ? 0 : paddedMin;
  const yMax = paddedMax;

  const x = (index) => margin.left + (plotWidth * index) / Math.max(timeline.length - 1, 1);
  const y = (value) => margin.top + plotHeight - ((value - yMin) / Math.max(yMax - yMin, 1e-6)) * plotHeight;
  const ticks = 4;

  const horizontalGrid = Array.from({ length: ticks + 1 }, (_, index) => {
    const value = yMin + ((yMax - yMin) * index) / ticks;
    const lineY = y(value);
    return `
      <line class="grid-line" x1="${margin.left}" y1="${lineY}" x2="${width - margin.right}" y2="${lineY}"></line>
      <text class="tick-label" x="${margin.left - 8}" y="${lineY + 4}" text-anchor="end">${fmt(value, unitSuffix === "kW" || unitSuffix === "%" ? 0 : 2)}${escapeHtml(unitSuffix)}</text>
    `;
  }).join("");

  const tickIndexes = Array.from({ length: Math.min(6, timeline.length) }, (_, index) =>
    Math.round((index * (timeline.length - 1)) / Math.max(Math.min(6, timeline.length) - 1, 1))
  );

  const xTicks = [...new Set(tickIndexes)].map((index) => {
    const label = timeline[index].clock || String(index);
    const tickX = x(index);
    return `
      <text class="tick-label" x="${tickX}" y="${height - 10}" text-anchor="middle">${escapeHtml(label)}</text>
    `;
  }).join("");

  const paths = series.map((line) => {
    const points = timeline.map((point, index) => `${x(index)},${y(Number(point[line.key]) || 0)}`).join(" ");
    return `<polyline fill="none" stroke="${line.color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" points="${points}"></polyline>`;
  }).join("");

  const legend = series.map((line) => `
    <span class="legend-chip">
      <span class="legend-swatch" style="background:${line.color}"></span>
      ${escapeHtml(line.label)}
    </span>
  `).join("");

  host.innerHTML = `
    <div class="chart-shell">
      <div class="chart-legend">${legend}</div>
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Simulation chart">
        ${horizontalGrid}
        <line class="axis-line" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}"></line>
        <line class="axis-line" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"></line>
        ${paths}
        ${xTicks}
      </svg>
    </div>
  `;
}

function setStatus(text) {
  els.statusLine.textContent = text;
}

function fmt(value, digits = 1) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return "0";
  }
  return numeric.toFixed(digits);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
