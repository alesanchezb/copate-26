function readAlertId() {
    const segments = window.location.pathname.split("/").filter(Boolean);
    return segments[segments.length - 1];
}

function formatDateTime(value) {
    const date = new Date(value);
    return {
        full: date.toLocaleString("es-MX"),
        short: date.toLocaleTimeString("es-MX", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        }),
    };
}

function formatLastSeen(seconds) {
    if (seconds == null) return "Sin lecturas";
    if (seconds < 60) return `Ultima lectura hace ${seconds}s`;
    return `Ultima lectura hace ${Math.floor(seconds / 60)}m`;
}

function pointStatusClass(item) {
    if (item.status === "MALO") {
        return "text-primary-container";
    }
    return "text-tertiary";
}

function renderModelLevel(item) {
    if (!item.model_level) return `<span class="text-[10px] font-bold text-outline">Sin modelo</span>`;
    const isWarn = item.model_level === "POSIBLE_MALA" || item.model_level === "MALA";
    const classes = isWarn ? "text-primary-container" : "text-tertiary";
    const fallback = item.model_is_fallback ? " fallback" : "";
    return `<span class="text-xs font-bold uppercase ${classes}">${item.model_level}${fallback}</span>`;
}

function formatMetric(value, decimals = 2, suffix = "") {
    if (value == null || Number.isNaN(Number(value))) return "--";
    return `${Number(value).toFixed(decimals)}${suffix}`;
}

function renderTelemetryRow(item, currentEventId) {
    const when = formatDateTime(item.source_timestamp);
    const isActive = item.event_id === currentEventId;
    const isAlert = item.status === "MALO";
    const score = item.model_score == null
        ? Number(item.anomaly_score || 0).toFixed(2)
        : Number(item.model_score).toFixed(6);
    return `
        <tr class="${isAlert ? "bg-error-container/5 border-l-2 border-error/50" : "bg-surface-lowest/30"} ${isActive ? "ring-1 ring-primary/20" : ""} hover:bg-surface-high/40 transition-colors">
            <td class="px-6 py-3 font-mono text-xs">${item.weld_id}</td>
            <td class="px-6 py-3 text-xs font-bold">${item.schedule || "--"}</td>
            <td class="px-6 py-3 font-mono text-xs">${when.short}</td>
            <td class="px-6 py-3">${formatMetric(item.distancia, 3)}</td>
            <td class="px-6 py-3">${formatMetric(item.fuerza, 1)}</td>
            <td class="px-6 py-3 ${isAlert ? "font-bold text-primary-container" : ""}">${formatMetric(item.watts, 2)}</td>
            <td class="px-6 py-3">${formatMetric(item.ampers, 2)}</td>
            <td class="px-6 py-3">${formatMetric(item.volts, 2, " V")}</td>
            <td class="px-6 py-3 ${isAlert ? "text-primary-container" : "text-outline"}">${score}</td>
            <td class="px-6 py-3">${renderModelLevel(item)}</td>
            <td class="px-6 py-3">
                <span class="inline-flex items-center gap-1 text-xs font-bold uppercase ${pointStatusClass(item)}">
                    <span class="h-1.5 w-1.5 rounded-full ${isAlert ? "bg-primary-container" : "bg-tertiary"}"></span>
                    ${item.status}
                </span>
            </td>
        </tr>
    `;
}

async function loadTelemetryStatus() {
    try {
        const response = await fetch("/api/dashboard");
        if (!response.ok) return;
        const data = await response.json();
        const status = data.telemetry_status || {};
        const state = status.state || "waiting";
        const chip = document.getElementById("telemetry-chip");
        chip.classList.remove("status-active", "status-idle", "status-waiting");
        chip.classList.add(`status-${state}`);
        document.getElementById("telemetry-icon").textContent = state === "active" ? "sensors" : state === "idle" ? "sensors_off" : "hourglass_empty";
        document.getElementById("telemetry-label").textContent = `${status.label || "Esperando datos"} · ${formatLastSeen(status.seconds_since_last_event)}`;
    } catch (error) {
        // Keep the existing label if status refresh fails.
    }
}

function renderChart(items) {
    const svg = document.getElementById("timeline-svg");
    const yAxis = document.getElementById("y-axis-labels");
    if (!items.length) {
        svg.innerHTML = "";
        yAxis.innerHTML = "";
        return;
    }

    const values = items.map((item) => Number(item.watts == null ? item.ampers || 0 : item.watts));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max((max - min) * 0.2, 1);
    const low = min - padding;
    const high = max + padding;
    const width = 1000;
    const height = 300;

    const points = items.map((item, index) => {
        const x = (index / Math.max(items.length - 1, 1)) * width;
        const value = Number(item.watts == null ? item.ampers || 0 : item.watts);
        const y = height - ((value - low) / (high - low || 1)) * height;
        return { x, y, item };
    });

    const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
    const fillPath = `${linePath} L ${width},${height} L 0,${height} Z`;

    const markers = points
        .filter((point) => point.item.status === "MALO")
        .map((point) => `
            <line x1="${point.x}" y1="0" x2="${point.x}" y2="${height}" stroke="#F28C00" stroke-width="2" class="anomaly-line"></line>
            <circle cx="${point.x}" cy="${point.y}" r="5" fill="#F28C00"></circle>
        `)
        .join("");

    const labels = [high, (high + low) / 2, low].map((value) => `<span>${value.toFixed(1)}</span>`).join("");
    yAxis.innerHTML = labels;

    svg.innerHTML = `
        <defs>
            <linearGradient id="lineGradient" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="#F28C00" stop-opacity="0.22"></stop>
                <stop offset="100%" stop-color="#F28C00" stop-opacity="0"></stop>
            </linearGradient>
        </defs>
        <path d="${fillPath}" fill="url(#lineGradient)"></path>
        <path d="${linePath}" fill="none" stroke="#F28C00" stroke-width="3"></path>
        ${markers}
    `;
}

async function loadAlertDetail() {
    const alertId = readAlertId();
    let data;
    try {
        const response = await fetch(`/api/alerts/${alertId}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        data = await response.json();
    } catch (error) {
        document.getElementById("detail-title").textContent = "Alerta no encontrada";
        document.getElementById("detail-message").textContent = `No fue posible recuperar el detalle de esta alerta: ${error.message}`;
        return;
    }

    const alert = data.alert;
    const when = formatDateTime(alert.source_timestamp);

    document.getElementById("line-label-sidebar").textContent = data.metadata.line_label;
    document.getElementById("operator-name").textContent = data.metadata.operator_name;
    document.getElementById("operator-line-label").textContent = data.metadata.operator_line_label;
    document.getElementById("detail-alert-id").textContent = alert.alert_id;
    document.getElementById("detail-title").textContent = `${alert.station_name} / ${alert.schedule || "--"} / soldadura ${alert.weld_id}`;
    document.getElementById("detail-message").textContent = alert.message;
    document.getElementById("detail-pallet").textContent = alert.pallet_run_id || alert.pallet_id;
    document.getElementById("detail-timestamp").textContent = when.full;
    document.getElementById("detail-schedule").textContent = alert.schedule || "--";
    document.getElementById("detail-model-level").textContent = alert.model_level || "--";

    document.getElementById("telemetry-table-body").innerHTML = data.timeline
        .map((item) => renderTelemetryRow(item, alert.event_id))
        .join("");

    renderChart(data.timeline);
}

loadAlertDetail();
loadTelemetryStatus();
setInterval(loadTelemetryStatus, 10000);
