const state = window.__INITIAL_DASHBOARD__;
const formatNumber = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
let refreshTimer = null;
let refreshInFlight = false;

function statusClass(status) {
  return status === "LIVE" || status === "RECOVERED" || status === "SUCCESS" ? "ok" :
    status === "RECONNECTING" || status === "STARTING" ? "warn" : "error";
}

function marketMarkup(market) {
  return `
    <a class="market-card market-link" data-symbol="${market.symbol}" href="/markets/${market.symbol}" aria-label="${market.symbol} 상세 보기">
      <div class="card-title"><h3>${market.symbol}</h3><span class="market-missing badge ${market.missing_last_hour === 0 ? "ok" : "error"}">${market.missing_last_hour ?? "-"} missing / hr</span></div>
      <div class="market-price price">${market.price === null ? "-" : formatNumber.format(market.price)}</div>
      <div class="market-meta"><span class="market-change ${((market.change_24h || 0) >= 0) ? "positive" : "negative"}">${market.change_24h === null ? "-" : `${market.change_24h.toFixed(2)}%`} / 24h</span><span class="market-lag">${market.lag_seconds ?? "-"}s candle lag</span></div>
      <span class="detail-link">상세 차트 보기 →</span>
    </a>`;
}

function renderMarkets(markets) {
  const root = document.getElementById("markets");
  const existingSymbols = [...root.querySelectorAll(".market-link")].map((card) => card.dataset.symbol);
  const expectedSymbols = markets.map((market) => market.symbol);
  if (existingSymbols.join(",") !== expectedSymbols.join(",")) {
    root.innerHTML = markets.map(marketMarkup).join("");
    return;
  }

  markets.forEach((market) => {
    const card = root.querySelector(`.market-link[data-symbol="${market.symbol}"]`);
    const missing = card.querySelector(".market-missing");
    missing.className = `market-missing badge ${market.missing_last_hour === 0 ? "ok" : "error"}`;
    missing.textContent = `${market.missing_last_hour ?? "-"} missing / hr`;
    card.querySelector(".market-price").textContent = market.price === null ? "-" : formatNumber.format(market.price);
    const change = card.querySelector(".market-change");
    change.className = `market-change ${((market.change_24h || 0) >= 0) ? "positive" : "negative"}`;
    change.textContent = market.change_24h === null ? "-" : `${market.change_24h.toFixed(2)}% / 24h`;
    card.querySelector(".market-lag").textContent = `${market.lag_seconds ?? "-"}s candle lag`;
  });
}

function render(data) {
  document.getElementById("generated-at").textContent = `Last query: ${new Date(data.generated_at).toLocaleString()}`;
  const streamStatus = document.getElementById("stream-status");
  const hasCheckpoints = data.checkpoints.length > 0;
  const isLive = hasCheckpoints && data.checkpoints.every((item) => item.status === "LIVE");
  streamStatus.classList.toggle("stale", hasCheckpoints && !isLive);
  streamStatus.innerHTML = `<span></span>${isLive ? "실시간 이벤트 수신 중" : hasCheckpoints ? "실시간 이벤트 수신 중단" : "수집기 상태 확인 중"}`;
  document.getElementById("checkpoints").innerHTML = data.checkpoints.map((item) => `
    <article class="checkpoint-card">
      <div><span class="label">${item.symbol} · ${item.source}</span><span class="badge ${statusClass(item.status)}">${item.status}</span></div>
      <strong>${item.last_event_time ? new Date(item.last_event_time).toLocaleTimeString() : "No event"}</strong>
      <small>${item.event_age_seconds === null ? "이벤트 대기 중" : `${item.event_age_seconds}s 전 수신`} · 재연결 ${item.reconnect_count}</small>
    </article>`).join("") || '<p class="empty">Waiting for ETL checkpoints…</p>';

  renderMarkets(data.markets);

  document.getElementById("runs").innerHTML = data.runs.map((run) => `
    <tr><td>${run.symbol}</td><td>${run.type}</td><td><span class="badge ${statusClass(run.status)}">${run.status}</span></td><td>${formatNumber.format(run.rows_processed)}</td><td>${run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">No backfill runs yet.</td></tr>';
}

async function refresh() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    const response = await fetch("/api/dashboard");
    if (response.ok) render(await response.json());
  } finally {
    refreshInFlight = false;
  }
}

function scheduleRefresh(delay = 1500) {
  if (refreshTimer) return;
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    refresh();
  }, delay);
}

render(state);
const stream = new EventSource("/events");
stream.onmessage = () => scheduleRefresh();
stream.onerror = () => scheduleRefresh();
setInterval(() => scheduleRefresh(0), 15000);
