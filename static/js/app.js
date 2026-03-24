// ── State ────────────────────────────────────────────────
const selectedTickers = new Set();

// ── Stock Selection ─────────────────────────────────────

function toggleStock(btn) {
    const ticker = btn.dataset.ticker;
    if (selectedTickers.has(ticker)) {
        selectedTickers.delete(ticker);
        btn.classList.remove("selected");
    } else {
        if (selectedTickers.size >= 10) return alert("Maximum 10 stocks allowed");
        selectedTickers.add(ticker);
        btn.classList.add("selected");
    }
    updateSelectedBar();
}

function addCustomTicker() {
    const input = document.getElementById("custom-input");
    const ticker = input.value.trim().toUpperCase();
    if (!ticker) return;
    if (selectedTickers.size >= 10) return alert("Maximum 10 stocks allowed");
    selectedTickers.add(ticker);
    input.value = "";

    // Highlight if exists in grid
    document.querySelectorAll(".stock-btn").forEach(btn => {
        if (btn.dataset.ticker === ticker) btn.classList.add("selected");
    });
    updateSelectedBar();
}

function removeTicker(ticker) {
    selectedTickers.delete(ticker);
    document.querySelectorAll(".stock-btn").forEach(btn => {
        if (btn.dataset.ticker === ticker) btn.classList.remove("selected");
    });
    updateSelectedBar();
}

function updateSelectedBar() {
    const count = selectedTickers.size;
    document.getElementById("selected-count").textContent = `${count} selected`;
    document.getElementById("analyze-btn").disabled = count === 0;

    const tagsEl = document.getElementById("selected-tags");
    tagsEl.innerHTML = "";
    selectedTickers.forEach(t => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.innerHTML = `${t} <span class="remove" onclick="removeTicker('${t}')">&times;</span>`;
        tagsEl.appendChild(tag);
    });
}

// ── Analysis ────────────────────────────────────────────

async function startAnalysis() {
    const tickers = Array.from(selectedTickers);
    if (!tickers.length) return;

    // Show progress, hide selector
    document.getElementById("analyze-btn").disabled = true;
    document.getElementById("progress-section").classList.remove("hidden");
    document.getElementById("results-section").classList.add("hidden");
    document.getElementById("results-grid").innerHTML = "";
    document.getElementById("summary-grid").innerHTML = "";
    document.getElementById("agent-log").innerHTML = "";
    document.getElementById("progress-bar").style.width = "0%";

    try {
        const resp = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tickers, portfolio_value: getPortfolioValue() }),
        });
        const data = await resp.json();
        if (data.error) { alert(data.error); return; }
        listenToStream(data.job_id, tickers.length);
    } catch (e) {
        alert("Failed to start analysis: " + e.message);
        document.getElementById("analyze-btn").disabled = false;
    }
}

function listenToStream(jobId, total) {
    const evtSource = new EventSource(`/api/stream/${jobId}`);
    let completed = 0;

    evtSource.addEventListener("progress", (e) => {
        const d = JSON.parse(e.data);
        document.getElementById("progress-text").textContent = d.message;
        addLog(d.message);
    });

    evtSource.addEventListener("result", (e) => {
        const result = JSON.parse(e.data);
        completed++;
        const pct = Math.round((completed / total) * 100);
        document.getElementById("progress-bar").style.width = pct + "%";
        addLog(`\u2713 ${result.ticker}: ${result.decision} (confidence ${Math.round((result.confidence || 0) * 100)}%)`, true);

        // Show results section and render card
        document.getElementById("results-section").classList.remove("hidden");
        renderResultCard(result);
        renderSummaryItem(result);
    });

    evtSource.addEventListener("done", (e) => {
        evtSource.close();
        const data = JSON.parse(e.data);
        document.getElementById("progress-text").textContent = "All analyses complete!";
        document.getElementById("progress-bar").style.width = "100%";
        document.getElementById("analyze-btn").disabled = false;
        addLog("All analyses complete!", true);

        // Render portfolio risk warnings
        if (data.portfolio_risk && data.portfolio_risk.warnings && data.portfolio_risk.warnings.length) {
            renderPortfolioWarnings(data.portfolio_risk);
        }
    });

    evtSource.onerror = () => {
        evtSource.close();
        document.getElementById("analyze-btn").disabled = false;
        addLog("Connection lost — check results below.");
    };
}

function addLog(msg, done = false) {
    const log = document.getElementById("agent-log");
    const entry = document.createElement("div");
    entry.className = "log-entry" + (done ? " done" : "");
    entry.textContent = msg;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

// ── Rendering ───────────────────────────────────────────

function renderSummaryItem(r) {
    const grid = document.getElementById("summary-grid");
    const item = document.createElement("div");
    item.className = "summary-item";
    const conf = Math.round((r.confidence || 0) * 100);
    const risk = r.risk_level || "unknown";
    item.innerHTML = `
        <span class="s-ticker">${r.ticker}</span>
        <span class="s-decision decision-${r.decision}">${r.decision}</span>
        <span class="s-meta">conf: ${conf}% &middot; risk: <span class="risk-${risk}">${risk}</span></span>
    `;
    grid.appendChild(item);
}

function renderResultCard(r) {
    const grid = document.getElementById("results-grid");
    const d = r.details || {};
    const conf = Math.round((r.confidence || 0) * 100);
    const risk = r.risk_level || "unknown";

    const confColor = r.decision === "BUY" ? "var(--buy)" :
                      r.decision === "SELL" ? "var(--sell)" : "var(--hold)";

    const card = document.createElement("div");
    card.className = "result-card";
    card.innerHTML = `
        <div class="result-header">
            <div class="rh-left">
                <h3>${r.ticker}</h3>
                <span class="rh-name">${r.name || r.ticker}</span>
            </div>
            <span class="decision-badge decision-${r.decision}">${r.decision}</span>
        </div>
        <div class="result-body">
            <div class="confidence-bar-container">
                <span class="confidence-label">Confidence: ${conf}%</span>
                <div class="confidence-bar-bg">
                    <div class="confidence-bar-fill" style="width:${conf}%; background:${confColor}"></div>
                </div>
            </div>
            <div class="metrics-grid">
                ${metric("Price", d.price != null ? "$" + num(d.price) : "—")}
                ${metric("Trend", d.trend || "—", "signal-" + (d.trend || ""))}
                ${metric("RSI", d.rsi != null ? num(d.rsi) : "—")}
                ${metric("MACD", d.macd_direction || "—", "signal-" + (d.macd_direction || ""))}
                ${metric("Technical", d.technical_signal || "—", "signal-" + (d.technical_signal || ""))}
                ${metric("Fundamental", d.fundamental_rating || "—", "signal-" + (d.fundamental_rating || ""))}
                ${metric("P/E Ratio", d.pe_ratio != null ? num(d.pe_ratio) : "—")}
                ${metric("Sentiment", d.sentiment_label || "—", "signal-" + (d.sentiment_label || ""))}
                ${metric("Volatility", d.volatility != null ? num(d.volatility) : "—")}
                ${metric("Risk", risk, "risk-" + risk)}
                ${metric("Stop-Loss", d.stop_loss != null ? "$" + num(d.stop_loss) : "—")}
                ${metric("Position Size", d.position_size != null ? d.position_size + " shares" : "—")}
            </div>
            <div class="result-summary">${r.summary || ""}</div>
        </div>
    `;
    grid.appendChild(card);
}

function metric(label, value, cls = "") {
    return `<div class="metric"><div class="label">${label}</div><div class="value ${cls}">${value}</div></div>`;
}

function num(v) {
    return typeof v === "number" ? v.toFixed(2) : v;
}

function getPortfolioValue() {
    const val = parseInt(document.getElementById("portfolio-value").value);
    return isNaN(val) || val < 1000 ? 100000 : val;
}

function renderPortfolioWarnings(risk) {
    const section = document.getElementById("results-section");
    // Remove old warnings if any
    const old = document.getElementById("portfolio-warnings");
    if (old) old.remove();

    const div = document.createElement("div");
    div.id = "portfolio-warnings";
    div.className = "card warnings-card";
    div.innerHTML = `
        <h3>Portfolio Risk Warnings</h3>
        <ul>${risk.warnings.map(w => `<li>${w}</li>`).join("")}</ul>
        ${risk.sector_breakdown ? `<p class="sector-info">Sectors: ${Object.entries(risk.sector_breakdown).map(([s,c]) => `${s} (${c})`).join(", ")}</p>` : ""}
    `;
    section.insertBefore(div, section.firstChild.nextSibling);
}
