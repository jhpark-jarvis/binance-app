const ONE_MINUTE_MS = 60_000;
const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
const priceNumber = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const ranges = { "1h": "1시간", "6h": "6시간", "24h": "24시간", "7d": "7일" };

let detail = window.__INITIAL_DETAIL__;
let refreshTimer = null;
let refreshInFlight = false;

function formatTime(value) {
  return value ? new Date(value).toLocaleTimeString() : "-";
}

function resizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function compactCandles(candles, maxCount) {
  if (candles.length <= maxCount) return candles;
  const step = Math.ceil(candles.length / maxCount);
  const compacted = [];
  for (let index = 0; index < candles.length; index += step) {
    const group = candles.slice(index, index + step);
    compacted.push({
      time: group[0].time,
      open: group[0].open,
      high: Math.max(...group.map((item) => item.high)),
      low: Math.min(...group.map((item) => item.low)),
      close: group.at(-1).close,
      volume: group.reduce((sum, item) => sum + item.volume, 0),
      closed: group.every((item) => item.closed),
    });
  }
  return compacted;
}

function xForTime(time, detailData, width, left, right) {
  const duration = detailData.range_end - detailData.range_start + ONE_MINUTE_MS;
  return left + ((time - detailData.range_start) / duration) * (width - left - right);
}

function drawCandleChart() {
  const canvas = document.getElementById("candle-chart");
  const { context, width, height } = resizeCanvas(canvas);
  const left = 12;
  const right = 56;
  const top = 14;
  const bottom = 24;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#0b1020";
  context.fillRect(0, 0, width, height);

  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const candles = compactCandles(detail.candles, Math.max(40, Math.floor(chartWidth / 3)));
  if (!candles.length) {
    context.fillStyle = "#93a1c6";
    context.font = "13px system-ui";
    context.fillText("선택한 구간에 저장된 캔들이 없습니다.", left, top + 24);
    return;
  }

  const minPrice = Math.min(...candles.map((item) => item.low));
  const maxPrice = Math.max(...candles.map((item) => item.high));
  const padding = Math.max((maxPrice - minPrice) * 0.08, maxPrice * 0.0002);
  const low = minPrice - padding;
  const high = maxPrice + padding;
  const yForPrice = (price) => top + ((high - price) / (high - low || 1)) * chartHeight;

  context.fillStyle = "rgba(255, 184, 91, .15)";
  detail.missing_open_times.forEach((time) => {
    const x = xForTime(time, detail, width, left, right);
    const nextX = xForTime(time + ONE_MINUTE_MS, detail, width, left, right);
    context.fillRect(x, top, Math.max(1, nextX - x), chartHeight);
  });

  context.strokeStyle = "#26335a";
  context.lineWidth = 1;
  context.fillStyle = "#93a1c6";
  context.font = "11px system-ui";
  for (let index = 0; index <= 4; index += 1) {
    const y = top + (chartHeight / 4) * index;
    const price = high - ((high - low) / 4) * index;
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(width - right, y);
    context.stroke();
    context.fillText(priceNumber.format(price), width - right + 7, y + 4);
  }

  const candleWidth = Math.max(1, Math.min(10, chartWidth / candles.length * 0.65));
  candles.forEach((candle) => {
    const x = xForTime(candle.time + ONE_MINUTE_MS / 2, detail, width, left, right);
    const rising = candle.close >= candle.open;
    const color = rising ? "#39d98a" : "#ff6572";
    context.strokeStyle = color;
    context.fillStyle = color;
    context.setLineDash(candle.closed ? [] : [3, 3]);
    context.beginPath();
    context.moveTo(x, yForPrice(candle.high));
    context.lineTo(x, yForPrice(candle.low));
    context.stroke();
    const bodyTop = Math.min(yForPrice(candle.open), yForPrice(candle.close));
    const bodyBottom = Math.max(yForPrice(candle.open), yForPrice(candle.close));
    context.fillRect(x - candleWidth / 2, bodyTop, candleWidth, Math.max(1, bodyBottom - bodyTop));
  });
  context.setLineDash([]);
  context.fillStyle = "#93a1c6";
  context.fillText(formatTime(detail.range_start), left, height - 7);
  const endLabel = formatTime(detail.range_end);
  context.fillText(endLabel, width - right - context.measureText(endLabel).width, height - 7);
}

function drawVolumeChart() {
  const canvas = document.getElementById("volume-chart");
  const { context, width, height } = resizeCanvas(canvas);
  const left = 12;
  const right = 56;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#0b1020";
  context.fillRect(0, 0, width, height);
  const candles = compactCandles(detail.candles, Math.max(40, Math.floor((width - left - right) / 3)));
  const maxVolume = Math.max(...candles.map((item) => item.volume), 1);
  const baseline = height - 6;
  candles.forEach((candle) => {
    const x = xForTime(candle.time + ONE_MINUTE_MS / 2, detail, width, left, right);
    const nextX = xForTime(candle.time + ONE_MINUTE_MS, detail, width, left, right);
    const barWidth = Math.max(1, Math.min(10, nextX - x));
    const barHeight = (candle.volume / maxVolume) * (height - 12);
    context.fillStyle = candle.close >= candle.open ? "rgba(57, 217, 138, .55)" : "rgba(255, 101, 114, .55)";
    context.fillRect(x - barWidth / 2, baseline - barHeight, barWidth, barHeight);
  });
}

function renderTrades() {
  document.getElementById("trades").innerHTML = detail.trades.map((trade) => `
    <li><span><strong class="${trade.taker_side === "BUY" ? "buy" : "sell"}">${trade.taker_side}</strong><small>${formatTime(trade.time)}</small></span><span>${number.format(trade.price)}<small>${number.format(trade.quantity)}</small></span></li>`).join("") || "<li>최근 체결이 없습니다.</li>";
}

function renderRuns() {
  document.getElementById("runs").innerHTML = detail.runs.map((run) => `
    <li><span>${run.type}<small>${run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</small></span><span><strong class="${run.status === "SUCCESS" ? "buy" : "sell"}">${run.status}</strong><small>${number.format(run.rows_processed)} rows</small></span></li>`).join("") || "<li>복구 이력이 없습니다.</li>";
}

function render() {
  document.getElementById("latest-price-value").textContent = detail.latest_price === null ? "-" : number.format(detail.latest_price);
  document.getElementById("latest-price-time").textContent = detail.latest_price_time ? `마지막 이벤트 ${formatTime(detail.latest_price_time)}` : "수집 데이터 대기 중";
  document.getElementById("coverage-range").textContent = ranges[detail.window];
  document.getElementById("missing-count").textContent = `${detail.missing_open_times.length}개`;
  const refreshState = document.getElementById("refresh-state");
  refreshState.textContent = "실시간 수신 중";
  refreshState.classList.remove("refresh-error");
  document.querySelectorAll(".range-button").forEach((button) => button.classList.toggle("active", button.dataset.window === detail.window));
  drawCandleChart();
  drawVolumeChart();
  renderTrades();
  renderRuns();
}

async function loadHistory(window = detail.window) {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    const response = await fetch(`/api/markets/${detail.symbol}/history?window=${window}`);
    if (!response.ok) throw new Error("상세 데이터를 가져오지 못했습니다.");
    detail = await response.json();
    render();
  } catch (error) {
    const refreshState = document.getElementById("refresh-state");
    refreshState.textContent = "갱신 재시도 중";
    refreshState.classList.add("refresh-error");
  } finally {
    refreshInFlight = false;
  }
}

function scheduleRefresh() {
  if (refreshTimer) return;
  const delay = detail.window === "7d" ? 5000 : 1500;
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    loadHistory();
  }, delay);
}

document.querySelectorAll(".range-button").forEach((button) => {
  button.addEventListener("click", () => loadHistory(button.dataset.window));
});
window.addEventListener("resize", render);
const stream = new EventSource("/events");
stream.onmessage = (message) => {
  try {
    const event = JSON.parse(message.data);
    if (event.payload?.symbol === detail.symbol) scheduleRefresh();
  } catch (_) {
    // A malformed notification must not stop the detail view's periodic refresh.
  }
};
stream.onerror = () => window.setTimeout(scheduleRefresh, 1500);
render();
