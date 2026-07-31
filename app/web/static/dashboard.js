const state = window.__INITIAL_DASHBOARD__;
const formatNumber = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });

function statusClass(status) {
  return status === "LIVE" || status === "RECOVERED" || status === "SUCCESS" ? "ok" :
    status === "RECONNECTING" ? "warn" : "error";
}

function render(data) {
  document.getElementById("generated-at").textContent = `Last query: ${new Date(data.generated_at).toLocaleString()}`;
  document.getElementById("checkpoints").innerHTML = data.checkpoints.map((item) => `
    <article class="checkpoint-card">
      <div><span class="label">${item.symbol} · ${item.source}</span><span class="badge ${statusClass(item.status)}">${item.status}</span></div>
      <strong>${item.last_event_time ? new Date(item.last_event_time).toLocaleTimeString() : "No event"}</strong>
      <small>Reconnects ${item.reconnect_count}</small>
    </article>`).join("") || '<p class="empty">Waiting for ETL checkpoints…</p>';

  document.getElementById("markets").innerHTML = data.markets.map((market) => `
    <article class="market-card">
      <div class="card-title"><h3>${market.symbol}</h3><span class="badge ${market.missing_last_hour === 0 ? "ok" : "error"}">${market.missing_last_hour ?? "-"} missing / hr</span></div>
      <div class="price">${market.price === null ? "-" : formatNumber.format(market.price)}</div>
      <div class="market-meta"><span class="${(market.change_24h || 0) >= 0 ? "positive" : "negative"}">${market.change_24h === null ? "-" : `${market.change_24h.toFixed(2)}%`} / 24h</span><span>${market.lag_seconds ?? "-"}s candle lag</span></div>
    </article>`).join("");

  document.getElementById("runs").innerHTML = data.runs.map((run) => `
    <tr><td>${run.symbol}</td><td>${run.type}</td><td><span class="badge ${statusClass(run.status)}">${run.status}</span></td><td>${formatNumber.format(run.rows_processed)}</td><td>${run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">No backfill runs yet.</td></tr>';
}

async function refresh() {
  const response = await fetch("/api/dashboard");
  if (response.ok) render(await response.json());
}

render(state);
const stream = new EventSource("/events");
stream.onmessage = () => refresh();
stream.onerror = () => setTimeout(refresh, 1500);
setInterval(refresh, 15000);

