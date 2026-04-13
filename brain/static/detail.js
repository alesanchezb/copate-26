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

function pointStatusClass(item) {
    if (item.status === "MALO") {
        return "text-primary-container";
    }
    return "text-tertiary";
}

function renderTelemetryRow(item, currentEventId) {
    const when = formatDateTime(item.source_timestamp);
    const isActive = item.event_id === currentEventId;
    const isAlert = item.status === "MALO";
    return `
        <tr class="${isAlert ? "bg-error-container/5 border-l-2 border-error/50" : "bg-surface-lowest/30"} ${isActive ? "ring-1 ring-primary/20" : ""} hover:bg-surface-high/40 transition-colors">
            <td class="px-6 py-3 font-mono text-xs">${item.weld_id}</td>
            <td class="px-6 py-3 font-mono text-xs">${when.short}</td>
            <td class="px-6 py-3 ${isAlert ? "font-bold text-primary-container" : ""}">${Number(item.voltaje || 0).toFixed(2)}</td>
            <td class="px-6 py-3">${item.corriente == null ? "--" : Number(item.corriente).toFixed(2)}</td>
            <td class="px-6 py-3">${Number(item.presion || 0).toFixed(2)}</td>
            <td class="px-6 py-3">${item.tiempo_ms == null ? "--" : Number(item.tiempo_ms).toFixed(0)}</td>
            <td class="px-6 py-3 ${isAlert ? "text-primary-container" : "text-outline"}">${Number(item.anomaly_score || 0).toFixed(2)}</td>
            <td class="px-6 py-3">
                <span class="inline-flex items-center gap-1 text-xs font-bold uppercase ${pointStatusClass(item)}">
                    <span class="h-1.5 w-1.5 rounded-full ${isAlert ? "bg-primary-container" : "bg-tertiary"}"></span>
                    ${isAlert ? "Anomalia" : "Nominal"}
                </span>
            </td>
        </tr>
    `;
}

function renderChart(items) {
    const svg = document.getElementById("timeline-svg");
    const yAxis = document.getElementById("y-axis-labels");
    if (!items.length) {
        svg.innerHTML = "";
        yAxis.innerHTML = "";
        return;
    }

    const values = items.map((item) => Number(item.voltaje || 0));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max((max - min) * 0.2, 1);
    const low = min - padding;
    const high = max + padding;
    const width = 1000;
    const height = 300;

    const points = items.map((item, index) => {
        const x = (index / Math.max(items.length - 1, 1)) * width;
        const y = height - ((Number(item.voltaje || 0) - low) / (high - low || 1)) * height;
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

    const labels = [high, (high + low) / 2, low].map((value) => `<span>${value.toFixed(1)}V</span>`).join("");
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
    const response = await fetch(`/api/alerts/${alertId}`);
    if (!response.ok) {
        document.getElementById("detail-title").textContent = "Alerta no encontrada";
        document.getElementById("detail-message").textContent = "No fue posible recuperar el detalle de esta alerta.";
        return;
    }

    const data = await response.json();
    const alert = data.alert;
    const when = formatDateTime(alert.source_timestamp);

    document.getElementById("line-label-sidebar").textContent = data.metadata.line_label;
    document.getElementById("operator-name").textContent = data.metadata.operator_name;
    document.getElementById("operator-line-label").textContent = data.metadata.operator_line_label;
    document.getElementById("detail-alert-id").textContent = alert.alert_id;
    document.getElementById("detail-title").textContent = `${alert.station_name} / soldadura ${alert.weld_id}`;
    document.getElementById("detail-message").textContent = alert.message;
    document.getElementById("detail-pallet").textContent = alert.pallet_id;
    document.getElementById("detail-timestamp").textContent = when.full;
    document.getElementById("detail-duration").textContent = alert.tiempo_ms == null ? "--" : `${Number(alert.tiempo_ms).toFixed(0)} ms`;
    document.getElementById("detail-confidence").textContent = `${Number(alert.confidence || 0).toFixed(2)}`;

    document.getElementById("telemetry-table-body").innerHTML = data.timeline
        .map((item) => renderTelemetryRow(item, alert.event_id))
        .join("");

    renderChart(data.timeline);
}

loadAlertDetail();
