function formatTime(value) {
    if (!value) return "--:--:--";
    return new Date(value).toLocaleTimeString("es-MX", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}

function formatPercent(value) {
    return `${Number(value || 0).toFixed(1)}%`;
}

function formatLastSeen(seconds) {
    if (seconds == null) return "Sin lecturas";
    if (seconds < 60) return `Ultima lectura hace ${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return `Ultima lectura hace ${minutes}m`;
}

function formatMetric(value, decimals = 2, suffix = "") {
    if (value == null || Number.isNaN(Number(value))) return "--";
    return `${Number(value).toFixed(decimals)}${suffix}`;
}

function renderModelLevel(item) {
    if (!item.model_level) return "";
    const isWarn = item.model_level === "POSIBLE_MALA" || item.model_level === "MALA";
    const classes = isWarn ? "status-pill-bad" : "bg-tertiary-container text-tertiary";
    const fallback = item.model_is_fallback ? " · fallback" : "";
    return `<span class="rounded px-2 py-0.5 text-[10px] font-bold ${classes}">${item.model_level}${fallback}</span>`;
}

function formatProcessSignal(item) {
    if (item.distancia != null || item.fuerza != null || item.watts != null) {
        return `Dist ${formatMetric(item.distancia, 3)} | Fuerza ${formatMetric(item.fuerza, 1)} | Watts ${formatMetric(item.watts, 2)}`;
    }
    if (item.ampers != null || item.volts != null) {
        return `Amps ${formatMetric(item.ampers)} | Volts ${formatMetric(item.volts, 2, " V")}`;
    }
    return "Sin telemetria";
}

function renderScheduleSlot(slot, hasLiveFlow) {
    const hasEvent = Boolean(slot.event_id);
    const isAlert = slot.status === "MALO";
    const isLiveEvent = hasEvent && hasLiveFlow;
    const statusClass = isAlert ? "text-red-alert font-extrabold" : isLiveEvent ? "text-tertiary font-semibold" : "text-on-surface-variant";
    const action = isAlert && slot.alert_id
        ? `<a class="alert-action-button rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-tight text-white hover:brightness-105 transition-colors" href="/alerts/${slot.alert_id}">Detalle</a>`
        : `<span class="text-[10px] text-on-surface-variant">${hasEvent ? `Run ${slot.pallet_run_id || slot.pallet_id}` : "Sin datos"}</span>`;

    return `
        <div class="schedule-slot rounded-lg border p-3 ${isAlert ? "schedule-slot-bad" : "border-outline-variant/30 bg-surface-lowest"}">
            <div class="mb-2 flex items-center justify-between gap-2">
                <span class="text-[11px] font-extrabold uppercase tracking-widest ${isAlert ? "text-red-alert" : "text-on-surface"}">${slot.schedule}</span>
                <span class="h-2.5 w-2.5 rounded-full ${isAlert ? "alert-dot" : isLiveEvent ? "bg-tertiary" : "bg-outline"}"></span>
            </div>
            <p class="text-xs ${statusClass}">${isAlert ? "MALO" : isLiveEvent ? "BUENO" : "Esperando"}</p>
            <p class="mt-1 text-[10px] text-on-surface-variant">${hasEvent ? formatProcessSignal(slot) : "Sin telemetria"}</p>
            <div class="mt-3 flex items-center justify-between gap-2">
                <div>${renderModelLevel(slot)}</div>
                <div>${action}</div>
            </div>
        </div>
    `;
}

function renderStationCard(group, hasLiveFlow) {
    const slots = group.schedules || [];
    const hasEvent = slots.some((slot) => Boolean(slot.event_id));
    const isAlert = slots.some((slot) => slot.status === "MALO");
    const isLiveEvent = hasEvent && hasLiveFlow;
    const glowClass = isAlert ? "station-card-bad" : isLiveEvent ? "hud-glow-normal" : "hud-glow-idle";
    const dotColor = isAlert ? "alert-dot" : isLiveEvent ? "bg-tertiary shadow-[0_0_8px_rgba(0,100,149,0.35)]" : "bg-outline";
    const statusLabel = isAlert ? "MALO detectado" : isLiveEvent ? "BUENO en flujo" : "Esperando datos";
    const statusClass = isAlert ? "text-red-alert font-extrabold" : isLiveEvent ? "text-tertiary font-medium" : "text-on-surface-variant";

    return `
        <div class="surface-card-high relative overflow-hidden rounded-lg p-6 ${glowClass}">
            <div class="mb-4 flex items-start justify-between">
                <span class="text-[10px] font-bold uppercase tracking-widest ${isAlert ? "text-red-alert" : "text-on-surface-variant"}">${group.node_label}</span>
                <div class="h-3 w-3 rounded-full ${dotColor}"></div>
            </div>
            <h3 class="font-headline mb-1 text-2xl font-bold text-on-surface">${group.display_name}</h3>
            <p class="text-sm ${statusClass}">${statusLabel}</p>
            <div class="mt-5 grid grid-cols-1 gap-3">${slots.map((slot) => renderScheduleSlot(slot, hasLiveFlow)).join("")}</div>
        </div>
    `;
}

function renderRecentLogRow(item) {
    const statusClass = item.status === "MALO"
        ? "status-pill-bad"
        : "bg-tertiary/10 text-tertiary";
    const rowClass = item.status === "MALO" ? "recent-row-bad" : "";

    const action = item.alert_id
        ? `<a class="text-[10px] font-bold text-primary hover:text-primary-container transition-colors" href="/alerts/${item.alert_id}">Ver detalle</a>`
        : `<span class="text-[10px] text-on-surface-variant/60">Sin detalle</span>`;

    return `
        <tr class="border-b border-outline-variant/5 hover:bg-surface-low transition-colors ${rowClass}">
            <td class="px-4 py-3 text-xs font-medium text-on-surface-variant">${formatTime(item.source_timestamp)}</td>
            <td class="px-4 py-3 text-xs font-mono text-primary">${item.pallet_run_id || item.pallet_id}</td>
            <td class="px-4 py-3 text-xs text-on-surface">${item.station_name}</td>
            <td class="px-4 py-3 text-xs font-bold text-on-surface-variant">${item.schedule || "--"} / ${item.weld_id || "--"}</td>
            <td class="px-4 py-3 text-xs text-on-surface-variant">${formatProcessSignal(item)}</td>
            <td class="px-4 py-3"><span class="rounded px-2 py-0.5 text-[10px] font-bold ${statusClass}">${item.status}</span></td>
            <td class="px-4 py-3 text-right">${action}</td>
        </tr>
    `;
}

function renderThroughput(throughput) {
    const bars = document.getElementById("throughput-bars");
    const labels = document.getElementById("throughput-labels");
    const maxValue = Math.max(...throughput.map((item) => item.welds), 1);

    bars.innerHTML = throughput.map((item, index) => {
        const height = Math.max((item.welds / maxValue) * 100, 10);
        const color = index === throughput.length - 1 ? "bg-primary" : index > throughput.length - 3 ? "bg-primary/60" : "bg-primary/20";
        return `<div class="w-full rounded-t-sm ${color}" style="height:${height}%"></div>`;
    }).join("");

    labels.innerHTML = `
        <span>${throughput[0]?.bucket || "--"}</span>
        <span>${throughput[Math.floor(throughput.length / 2)]?.bucket || "--"}</span>
        <span>${throughput[throughput.length - 1]?.bucket || "--"}</span>
    `;
}

function renderActiveAlert(alert) {
    const container = document.getElementById("active-alert-card");
    if (!alert) {
        container.innerHTML = `
            <div class="flex items-center space-x-3">
                <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-tertiary-container text-tertiary">
                    <span class="material-symbols-outlined">check_circle</span>
                </div>
                <div>
                    <p class="text-xs font-bold text-on-surface">No hay alertas activas</p>
                    <p class="text-[10px] text-on-surface-variant">Las cuatro estaciones estan operando dentro de parametros.</p>
                </div>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <a class="flex items-center space-x-3 hover:opacity-90 transition-opacity" href="/alerts/${alert.alert_id}">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl alert-icon-box">
                <span class="material-symbols-outlined">warning</span>
            </div>
            <div>
                <p class="text-xs font-bold text-on-surface">Alerta activa</p>
                <p class="text-[10px] text-on-surface-variant">${alert.message}</p>
            </div>
        </a>
    `;
}

function renderTelemetryStatus(status) {
    const chip = document.getElementById("telemetry-chip");
    const icon = document.getElementById("telemetry-icon");
    const label = document.getElementById("telemetry-label");
    const state = status?.state || "waiting";
    chip.classList.remove("status-active", "status-idle", "status-waiting");
    chip.classList.add(`status-${state}`);
    icon.textContent = state === "active" ? "sensors" : state === "idle" ? "sensors_off" : "hourglass_empty";
    label.textContent = `${status?.label || "Esperando datos"} · ${formatLastSeen(status?.seconds_since_last_event)}`;
}

function groupStationSchedules(items) {
    const groups = new Map();
    for (const item of items || []) {
        if (!groups.has(item.station_code)) {
            groups.set(item.station_code, {
                station_code: item.station_code,
                display_name: item.display_name,
                node_label: item.node_label,
                station_order: item.station_order,
                schedules: [],
            });
        }
        groups.get(item.station_code).schedules.push(item);
    }
    return [...groups.values()].sort((a, b) => a.station_order - b.station_order);
}

let dashboardInflight = false;

async function loadDashboard() {
    if (dashboardInflight) {
        return;
    }
    dashboardInflight = true;
    let data;
    try {
        const response = await fetch("/api/dashboard");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        data = await response.json();
    } catch (error) {
        document.getElementById("stations-grid").innerHTML = `
            <div class="surface-panel rounded-lg p-6 text-sm font-semibold text-primary-container">
                No fue posible cargar el dashboard: ${error.message}
            </div>
        `;
        return;
    } finally {
        dashboardInflight = false;
    }

    document.getElementById("line-label").textContent = data.metadata.line_label;
    document.getElementById("line-label-sidebar").textContent = data.metadata.line_label;
    document.getElementById("operator-name").textContent = data.metadata.operator_name;
    document.getElementById("operator-line-label").textContent = data.metadata.operator_line_label;
    const hasLiveFlow = data.telemetry_status?.state === "active";
    document.getElementById("stations-grid").innerHTML = groupStationSchedules(data.station_schedules).map((group) => renderStationCard(group, hasLiveFlow)).join("");
    document.getElementById("recent-logs-body").innerHTML = data.recent_logs.map(renderRecentLogRow).join("");
    document.getElementById("stat-total-welds").textContent = Number(data.stats.total_welds || 0).toLocaleString("es-MX");
    document.getElementById("stat-success-rate-badge").textContent = formatPercent(data.stats.success_rate);
    document.getElementById("stat-success-rate").textContent = formatPercent(data.stats.success_rate);
    document.getElementById("stat-success-bar").style.width = `${Math.min(Number(data.stats.success_rate || 0), 100)}%`;
    document.getElementById("stat-anomalies").textContent = Number(data.stats.anomaly_count || 0).toLocaleString("es-MX");

    const anomalyPercent = data.stats.total_welds
        ? Math.min((Number(data.stats.anomaly_count || 0) / Number(data.stats.total_welds || 1)) * 100, 100)
        : 0;
    document.getElementById("stat-anomaly-bar").style.width = `${anomalyPercent}%`;

    renderThroughput(data.stats.throughput || []);
    renderActiveAlert(data.active_alert);
    renderTelemetryStatus(data.telemetry_status);
}

loadDashboard();
setInterval(loadDashboard, 2000);
