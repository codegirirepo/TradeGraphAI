// ── State ────────────────────────────────────────────────
const selectedTickers = new Set();
let allResults = [];
let currentJobId = null;

// ── Tab Navigation ──────────────────────────────────────
function switchTab(tab) {
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    document.getElementById("tab-" + tab).classList.add("active");
    document.querySelector(`[data-tab="${tab}"]`)?.classList.add("active");
    document.getElementById("sidebar").classList.remove("open");
}

// ── Theme Toggle ────────────────────────────────────────
function toggleTheme() {
    const html = document.documentElement;
    const next = html.dataset.theme === "dark" ? "light" : "dark";
    html.dataset.theme = next;
    document.getElementById("theme-icon").textContent = next === "dark" ? "\u263E" : "\u2600";
    localStorage.setItem("theme", next);
    // Update chart colors
    Chart.helpers.each(Chart.instances, c => { updateChartTheme(c); c.update(); });
}
(function initTheme() {
    const saved = localStorage.getItem("theme");
    if (saved) { document.documentElement.dataset.theme = saved; document.getElementById("theme-icon").textContent = saved === "dark" ? "\u263E" : "\u2600"; }
})();

// ── Stock Selection ─────────────────────────────────────
function toggleStock(btn) {
    const t = btn.dataset.ticker;
    if (selectedTickers.has(t)) { selectedTickers.delete(t); btn.classList.remove("selected"); }
    else { if (selectedTickers.size >= 10) return; selectedTickers.add(t); btn.classList.add("selected"); }
    updateBar();
}
function addCustomTicker() {
    const input = document.getElementById("custom-input");
    const t = input.value.trim().toUpperCase();
    if (!t || selectedTickers.size >= 10) return;
    selectedTickers.add(t);
    input.value = "";
    document.querySelectorAll(".stock-chip").forEach(b => { if (b.dataset.ticker === t) b.classList.add("selected"); });
    updateBar();
}
function removeTicker(t) {
    selectedTickers.delete(t);
    document.querySelectorAll(".stock-chip").forEach(b => { if (b.dataset.ticker === t) b.classList.remove("selected"); });
    updateBar();
}
function selectAll() {
    document.querySelectorAll(".stock-chip").forEach(b => {
        if (selectedTickers.size < 10) { selectedTickers.add(b.dataset.ticker); b.classList.add("selected"); }
    });
    updateBar();
}
function clearAll() {
    selectedTickers.clear();
    document.querySelectorAll(".stock-chip").forEach(b => b.classList.remove("selected"));
    updateBar();
}
function updateBar() {
    document.getElementById("selected-count").textContent = `${selectedTickers.size} / 10`;
    document.getElementById("analyze-btn").disabled = selectedTickers.size === 0;
    const tags = document.getElementById("selected-tags");
    tags.innerHTML = "";
    selectedTickers.forEach(t => {
        tags.innerHTML += `<span class="tag">${t}<span class="remove" onclick="removeTicker('${t}')">&times;</span></span>`;
    });
}

// ── Analysis ────────────────────────────────────────────
async function startAnalysis() {
    const tickers = Array.from(selectedTickers);
    if (!tickers.length) return;

    allResults = [];
    document.getElementById("analyze-btn").disabled = true;
    document.getElementById("progress-card").classList.remove("hidden");
    document.getElementById("results-grid").innerHTML = "";
    document.getElementById("kpi-row").innerHTML = "";
    document.getElementById("portfolio-warnings").innerHTML = "";
    document.getElementById("summary-card").style.display = "none";
    document.getElementById("export-actions").style.display = "none";
    document.getElementById("agent-log").innerHTML = "";
    document.getElementById("progress-bar").style.width = "0%";
    document.getElementById("agent-status").textContent = "Running...";
    document.getElementById("agent-status").className = "badge running";

    // Build pipeline steps
    const steps = document.getElementById("pipeline-steps");
    steps.innerHTML = tickers.map(t => `<span class="pipeline-step" id="step-${t}">${t}</span>`).join("");

    try {
        const resp = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tickers, portfolio_value: getPortfolioValue() }),
        });
        const data = await resp.json();
        if (data.error) { alert(data.error); resetUI(); return; }
        currentJobId = data.job_id;
        listenToStream(data.job_id, tickers.length);
    } catch (e) {
        alert("Failed: " + e.message);
        resetUI();
    }
}

function listenToStream(jobId, total) {
    const evtSource = new EventSource(`/api/stream/${jobId}`);
    let completed = 0;

    evtSource.addEventListener("progress", e => {
        const d = JSON.parse(e.data);
        const el = document.getElementById("step-" + d.ticker);
        if (el) { document.querySelectorAll(".pipeline-step").forEach(s => s.classList.remove("active")); el.classList.add("active"); }
        addLog(d.message);
    });

    evtSource.addEventListener("result", e => {
        const r = JSON.parse(e.data);
        completed++;
        allResults.push(r);
        document.getElementById("progress-bar").style.width = Math.round(completed / total * 100) + "%";
        const el = document.getElementById("step-" + r.ticker);
        if (el) { el.classList.remove("active"); el.classList.add("done"); }
        addLog(`Done: ${r.ticker} -> ${r.decision} (${Math.round((r.confidence||0)*100)}%)`, true);

        switchTab("results");
        document.getElementById("summary-card").style.display = "block";
        renderKPI(r);
        renderResultCard(r);
    });

    evtSource.addEventListener("done", e => {
        evtSource.close();
        const data = JSON.parse(e.data);
        document.getElementById("progress-bar").style.width = "100%";
        document.getElementById("agent-status").textContent = "Complete";
        document.getElementById("agent-status").className = "badge";
        document.getElementById("analyze-btn").disabled = false;
        document.getElementById("export-actions").style.display = "flex";
        addLog("All analyses complete!", true);

        if (data.portfolio_risk?.warnings?.length) renderWarnings(data.portfolio_risk);
        buildCompareTable();
    });

    evtSource.onerror = () => { evtSource.close(); resetUI(); addLog("Connection lost."); };
}

function resetUI() {
    document.getElementById("analyze-btn").disabled = false;
    document.getElementById("agent-status").textContent = "Ready";
    document.getElementById("agent-status").className = "badge";
}
function addLog(msg, done = false) {
    const log = document.getElementById("agent-log");
    const d = document.createElement("div");
    d.className = "log-entry" + (done ? " done" : "");
    d.textContent = msg;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
}
function getPortfolioValue() {
    const v = parseInt(document.getElementById("portfolio-value").value);
    return isNaN(v) || v < 1000 ? 100000 : v;
}

// ── KPI Rendering ───────────────────────────────────────
function renderKPI(r) {
    const row = document.getElementById("kpi-row");
    const conf = Math.round((r.confidence || 0) * 100);
    const color = r.decision === "BUY" ? "var(--buy)" : r.decision === "SELL" ? "var(--sell)" : "var(--hold)";
    row.innerHTML += `<div class="kpi"><div class="kpi-value" style="color:${color}">${r.ticker}</div><div class="kpi-label">${r.decision} (${conf}%)</div></div>`;
}

// ── Result Card ─────────────────────────────────────────
function renderResultCard(r) {
    const grid = document.getElementById("results-grid");
    const d = r.details || {};
    const conf = Math.round((r.confidence || 0) * 100);
    const risk = r.risk_level || "unknown";
    const confColor = r.decision === "BUY" ? "var(--buy)" : r.decision === "SELL" ? "var(--sell)" : "var(--hold)";
    const chartId = "chart-" + r.ticker;
    const elapsed = r.elapsed_seconds ? `${r.elapsed_seconds}s` : "";

    let sentHtml = "";
    if (r.sentiment_details?.length) {
        sentHtml = `<div class="sentiment-list">${r.sentiment_details.map(s =>
            `<div class="sent-item"><span class="sent-title">${esc(s.title)}</span><span class="sent-badge sent-${s.label}">${s.label} ${(s.score*100).toFixed(0)}%</span></div>`
        ).join("")}</div>`;
    }

    const card = document.createElement("div");
    card.className = "result-card";
    card.innerHTML = `
        <div class="result-header">
            <div class="rh-left">
                <h3>${r.ticker} <span class="rh-time">${elapsed}</span></h3>
                <span class="rh-name">${r.name || r.ticker}</span>
            </div>
            <span class="decision-badge decision-${r.decision}">${r.decision}</span>
        </div>
        <div class="result-body">
            <div class="confidence-row">
                <span class="conf-label">Confidence: ${conf}%</span>
                <div class="conf-bar-bg"><div class="conf-bar-fill" style="width:${conf}%;background:${confColor}"></div></div>
            </div>
            ${r.chart_data ? `<div class="chart-container"><canvas id="${chartId}" height="180"></canvas></div>` : ""}
            <div class="metrics-grid">
                ${m("Price", d.price != null ? "$" + n(d.price) : "-")}
                ${m("Trend", d.trend || "-", "signal-" + (d.trend || ""))}
                ${m("RSI", d.rsi != null ? n(d.rsi) : "-")}
                ${m("MACD", d.macd_direction || "-", "signal-" + (d.macd_direction || ""))}
                ${m("Technical", d.technical_signal || "-", "signal-" + (d.technical_signal || ""))}
                ${m("Fundamental", d.fundamental_rating || "-", "signal-" + (d.fundamental_rating || ""))}
                ${m("P/E Ratio", d.pe_ratio != null ? n(d.pe_ratio) : "-")}
                ${m("Sentiment", d.sentiment_label || "-", "signal-" + (d.sentiment_label || ""))}
                ${m("Volatility", d.volatility != null ? n(d.volatility) : "-")}
                ${m("Risk", risk, "risk-" + risk)}
                ${m("Stop-Loss", d.stop_loss != null ? "$" + n(d.stop_loss) : "-")}
                ${m("Position", d.position_size != null ? d.position_size + " shares" : "-")}
            </div>
            ${sentHtml}
            <div class="result-summary">${r.summary || ""}</div>
        </div>`;
    grid.appendChild(card);

    // Render chart
    if (r.chart_data) setTimeout(() => renderChart(chartId, r.chart_data), 50);
}

function m(label, value, cls = "") {
    return `<div class="metric"><div class="label">${label}</div><div class="value ${cls}">${value}</div></div>`;
}
function n(v) { return typeof v === "number" ? v.toFixed(2) : v; }
function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

// ── Charts ──────────────────────────────────────────────
function renderChart(canvasId, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    const isDark = document.documentElement.dataset.theme === "dark";
    const gridColor = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)";
    const textColor = isDark ? "#6b7394" : "#6b7394";

    new Chart(ctx, {
        type: "line",
        data: {
            labels: data.dates,
            datasets: [
                { label: "Close", data: data.close, borderColor: "#7c6cf0", borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.1 },
                { label: "SMA 20", data: data.sma_20, borderColor: "#34d399", borderWidth: 1, pointRadius: 0, borderDash: [4,2], fill: false },
                { label: "SMA 50", data: data.sma_50, borderColor: "#f87171", borderWidth: 1, pointRadius: 0, borderDash: [4,2], fill: false },
            ],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: { legend: { labels: { color: textColor, font: { size: 10 } } } },
            scales: {
                x: { display: true, ticks: { color: textColor, maxTicksLimit: 8, font: { size: 9 } }, grid: { color: gridColor } },
                y: { ticks: { color: textColor, font: { size: 9 } }, grid: { color: gridColor } },
            },
        },
    });
}

function updateChartTheme(chart) {
    const isDark = document.documentElement.dataset.theme === "dark";
    const gc = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)";
    const tc = "#6b7394";
    chart.options.scales.x.ticks.color = tc; chart.options.scales.x.grid.color = gc;
    chart.options.scales.y.ticks.color = tc; chart.options.scales.y.grid.color = gc;
    chart.options.plugins.legend.labels.color = tc;
}

// ── Warnings ────────────────────────────────────────────
function renderWarnings(risk) {
    const el = document.getElementById("portfolio-warnings");
    el.innerHTML = risk.warnings.map(w => `<div class="warning-item">${w}</div>`).join("");
}

// ── Compare Table ───────────────────────────────────────
function buildCompareTable() {
    if (!allResults.length) return;
    const wrap = document.getElementById("compare-table-wrap");
    const metrics = ["decision","confidence","risk_level","price","trend","rsi","macd_direction","technical_signal","fundamental_rating","pe_ratio","sentiment_label","volatility","stop_loss","position_size"];
    const labels = ["Decision","Confidence","Risk","Price","Trend","RSI","MACD","Technical","Fundamental","P/E","Sentiment","Volatility","Stop-Loss","Position"];

    let html = `<table class="compare-table"><thead><tr><th>Metric</th>`;
    allResults.forEach(r => html += `<th>${r.ticker}</th>`);
    html += `</tr></thead><tbody>`;

    metrics.forEach((key, i) => {
        html += `<tr><td>${labels[i]}</td>`;
        allResults.forEach(r => {
            let val = key === "confidence" ? Math.round((r.confidence||0)*100)+"%" :
                      (r.details?.[key] ?? r[key] ?? "-");
            if (typeof val === "number") val = val.toFixed(2);
            const cls = key === "decision" ? `decision-${val}` :
                        ["trend","macd_direction","technical_signal","fundamental_rating","sentiment_label"].includes(key) ? `signal-${val}` :
                        key === "risk_level" ? `risk-${val}` : "";
            html += `<td class="${cls}">${val}</td>`;
        });
        html += `</tr>`;
    });
    html += `</tbody></table>`;
    wrap.innerHTML = html;
}

// ── Watchlist ───────────────────────────────────────────
function getWatchlist() { return JSON.parse(localStorage.getItem("watchlist") || "[]"); }
function saveWatchlist(list) { localStorage.setItem("watchlist", JSON.stringify(list)); }

function addToWatchlist() {
    const input = document.getElementById("watchlist-input");
    const t = input.value.trim().toUpperCase();
    if (!t) return;
    const list = getWatchlist();
    if (!list.includes(t)) { list.push(t); saveWatchlist(list); }
    input.value = "";
    renderWatchlist();
}
function removeFromWatchlist(t) {
    saveWatchlist(getWatchlist().filter(x => x !== t));
    renderWatchlist();
}
function analyzeFromWatchlist(t) {
    selectedTickers.clear(); selectedTickers.add(t);
    document.querySelectorAll(".stock-chip").forEach(b => b.classList.toggle("selected", b.dataset.ticker === t));
    updateBar(); switchTab("analyze");
}
function renderWatchlist() {
    const list = getWatchlist();
    const grid = document.getElementById("watchlist-grid");
    const empty = document.getElementById("watchlist-empty");
    if (!list.length) { grid.innerHTML = ""; empty.classList.remove("hidden"); return; }
    empty.classList.add("hidden");
    grid.innerHTML = list.map(t => `
        <div class="watchlist-item">
            <span class="wl-ticker">${t}</span>
            <span class="wl-analyze" onclick="analyzeFromWatchlist('${t}')">Analyze</span>
            <span class="wl-remove" onclick="removeFromWatchlist('${t}')">&times;</span>
        </div>
    `).join("");
}
renderWatchlist();

// ── PDF Export ──────────────────────────────────────────
function exportPDF() {
    if (currentJobId) window.open(`/api/export/pdf/${currentJobId}`, "_blank");
}
