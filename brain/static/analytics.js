function formatLastSeen(seconds) {
    if (seconds == null) return "Sin lecturas";
    if (seconds < 60) return `Ultima lectura hace ${seconds}s`;
    return `Ultima lectura hace ${Math.floor(seconds / 60)}m`;
}

function renderTelemetryStatus(status) {
    const state = status?.state || "waiting";
    const chip = document.getElementById("telemetry-chip");
    chip.classList.remove("status-active", "status-idle", "status-waiting");
    chip.classList.add(`status-${state}`);
    document.getElementById("telemetry-icon").textContent = state === "active" ? "sensors" : state === "idle" ? "sensors_off" : "hourglass_empty";
    document.getElementById("telemetry-label").textContent = `${status?.label || "Esperando datos"} · ${formatLastSeen(status?.seconds_since_last_event)}`;
}

const MODEL_ORANGE = "#F28C00";
const MODEL_BLUE = "#006495";
const MUTED_BAR = "#E6D8CC";

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatHour(value) {
    if (!value) return "--:--";
    return new Intl.DateTimeFormat("es-MX", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    }).format(new Date(value));
}

function formatPercent(value) {
    return `${Math.round(Number(value || 0) * 100)}%`;
}

function chartBars(items, options = {}) {
    const enabledItems = items.filter((item) => item.enabled !== false);
    const maxValue = Math.max(...enabledItems.map((item) => Number(item.value || 0)), 1);
    const labelEvery = options.labelEvery || 1;
    return `
        <div class="analytics-bars ${options.compact ? "analytics-bars-compact" : ""}">
            ${items.map((item) => {
                const value = Number(item.value || 0);
                const isEnabled = item.enabled !== false;
                const height = isEnabled && value > 0 ? Math.max((value / maxValue) * 100, 8) : 0;
                const color = isEnabled ? (item.color || MODEL_ORANGE) : MUTED_BAR;
                const label = escapeHtml(item.label);
                const detail = item.detail ? `<div class="analytics-bar-detail">${escapeHtml(item.detail)}</div>` : "";
                const visibleLabel = item.forceLabel || item.index % labelEvery === 0 || item.index === items.length - 1;
                return `
                    <div class="analytics-bar-column ${isEnabled ? "" : "analytics-bar-column-disabled"}" title="${label}: ${value}">
                        <div class="analytics-bar-track">
                            <div class="analytics-bar-fill" style="height:${height}%; background:${color};"></div>
                        </div>
                        <div class="analytics-bar-label ${visibleLabel ? "" : "analytics-bar-label-hidden"}">${label}</div>
                        ${detail}
                    </div>
                `;
            }).join("")}
        </div>
    `;
}

function renderStationCharts(stations) {
    document.getElementById("station-error-charts").innerHTML = stations.map((station) => {
        const schedules = ["Sch1", "Sch2"].map((schedule, index) => {
            const data = station.schedules?.[schedule] || {};
            const enabled = Boolean(data.model_enabled);
            const malos = Number(data.malos || 0);
            const total = Number(data.total || 0);
            return {
                index,
                label: schedule,
                value: malos,
                enabled,
                forceLabel: true,
                detail: enabled ? `${malos} MALO` : "Sin modelo",
                total,
                modelKey: data.model_key,
            };
        });
        const stationMalos = schedules.reduce((sum, item) => sum + item.value, 0);
        const hasModel = schedules.some((item) => item.enabled);
        const summary = hasModel ? `${stationMalos} MALO` : "Sin modelo";
        const footer = schedules.map((item) => {
            const content = item.enabled
                ? `${escapeHtml(item.label)}: <span class="analytics-stat-strong">${item.value}</span> MALO de ${item.total}`
                : `${escapeHtml(item.label)}: <span class="analytics-stat-muted">sin modelo</span>`;
            return `<div>${content}</div>`;
        }).join("");

        return `
            <article class="surface-panel rounded-2xl p-5 card-shadow ${hasModel ? "" : "analytics-station-muted"}">
                <div class="mb-4 flex items-start justify-between gap-3">
                    <h2 class="analytics-station-title font-headline text-lg font-extrabold">${escapeHtml(station.display_name)}</h2>
                    <span class="analytics-card-kpi">${summary}</span>
                </div>
                <div class="h-36">${chartBars(schedules, { compact: true })}</div>
                <div class="mt-4 grid grid-cols-2 gap-2 text-xs font-semibold text-on-surface-variant">
                    ${footer}
                </div>
            </article>
        `;
    }).join("");
}

function renderTimeSeries(items) {
    const bars = items.map((item, index) => ({
        index,
        label: formatHour(item.bucket_start),
        value: Number(item.malos || 0),
        color: MODEL_ORANGE,
        forceLabel: Number(item.malos || 0) > 0,
    }));
    const maxValue = Math.max(...bars.map((item) => item.value), 1);
    const halfValue = Math.ceil(maxValue / 2);
    document.getElementById("time-series-chart").innerHTML = `
        <div class="analytics-chart-with-axis">
            <div class="analytics-y-axis">
                <span>${maxValue}</span>
                <span>${halfValue}</span>
                <span>0</span>
            </div>
            <div class="analytics-chart-body chart-grid rounded-lg">
                ${chartBars(bars, { labelEvery: 2 })}
            </div>
        </div>
    `;
}

function renderModelDistribution(items) {
    const bars = (items || []).map((item, index) => ({
        index,
        label: `${String(item.display_name || "").replace("Estacion ", "E")} ${item.schedule}`,
        value: Number(item.malos || 0),
        color: index % 2 === 0 ? MODEL_ORANGE : MODEL_BLUE,
        forceLabel: true,
        detail: `${Number(item.malos || 0)} MALO · ${formatPercent(item.share)}`,
    }));
    document.getElementById("model-distribution-chart").innerHTML = chartBars(bars, { compact: true });
}

async function loadAnalytics() {
    const [analyticsResponse, dashboardResponse] = await Promise.all([
        fetch("/api/analytics"),
        fetch("/api/dashboard"),
    ]);
    if (!analyticsResponse.ok) {
        throw new Error(`HTTP ${analyticsResponse.status}`);
    }
    const analytics = await analyticsResponse.json();
    const dashboard = dashboardResponse.ok ? await dashboardResponse.json() : {};

    document.getElementById("line-label-sidebar").textContent = analytics.metadata.line_label;
    document.getElementById("operator-name").textContent = analytics.metadata.operator_name;
    document.getElementById("operator-line-label").textContent = analytics.metadata.operator_line_label;
    document.getElementById("window-label").textContent = analytics.metadata.window_label;
    renderStationCharts(analytics.station_schedule_errors || []);
    renderTimeSeries(analytics.error_time_series || []);
    renderModelDistribution(analytics.model_error_distribution || []);
    renderTelemetryStatus(dashboard.telemetry_status);
}

loadAnalytics().catch((error) => {
    document.getElementById("station-error-charts").innerHTML = `
        <div class="surface-panel rounded-2xl p-6 text-sm font-semibold text-primary-container">
            No fue posible cargar analitica: ${escapeHtml(error.message)}
        </div>
    `;
});
setInterval(() => loadAnalytics().catch(() => {}), 15000);
