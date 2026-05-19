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

function formatProcessSignal(item) {
    if (item.ampers != null || item.volts != null) {
        const amps = item.ampers == null ? "--" : Number(item.ampers).toFixed(2);
        const volts = item.volts == null ? "--" : Number(item.volts).toFixed(2);
        return `Amps: ${amps} | Volts: ${volts}`;
    }
    return `Voltaje: ${Number(item.voltaje || 0).toFixed(2)} V`;
}

function renderStationCard(station) {
    const hasEvent = Boolean(station.event_id);
    const isAlert = station.status === "MALO";
    const glowClass = isAlert ? "hud-glow-error ring-1 ring-primary-container/20" : hasEvent ? "hud-glow-normal" : "hud-glow-idle";
    const dotColor = isAlert ? "bg-primary-container shadow-[0_0_12px_rgba(242,140,0,0.45)]" : hasEvent ? "bg-tertiary shadow-[0_0_8px_rgba(0,100,149,0.35)]" : "bg-outline";
    const statusLabel = isAlert ? "Anomalia detectada" : hasEvent ? "Operacion estable" : "Esperando datos";
    const statusClass = isAlert ? "text-primary-container font-bold" : hasEvent ? "text-tertiary font-medium" : "text-on-surface-variant";
    const action = isAlert && station.alert_id
        ? `<a class="inline-flex rounded-xl bg-primary-container px-3 py-1.5 text-[10px] font-bold uppercase tracking-tight text-white hover:brightness-105 transition-colors" href="/alerts/${station.alert_id}">Ver detalle</a>`
        : `<span class="text-[10px] text-on-surface-variant">${hasEvent ? `Pallet ${station.pallet_id}` : "Sin actividad"}</span>`;

    return `
        <div class="surface-card-high relative overflow-hidden rounded-lg p-6 ${glowClass}">
            <div class="mb-4 flex items-start justify-between">
                <span class="text-[10px] font-bold uppercase tracking-widest ${isAlert ? "text-primary-container" : "text-on-surface-variant"}">${station.node_label}</span>
                <div class="h-2 w-2 rounded-full ${dotColor}"></div>
            </div>
            <h3 class="font-headline mb-1 text-2xl font-bold text-on-surface">${station.display_name}</h3>
            <p class="text-sm ${statusClass}">${statusLabel}</p>
            <p class="mt-2 inline-block rounded-full bg-error-container px-2.5 py-0.5 text-[11px] text-primary-container ${isAlert ? "" : "opacity-0"}">
                ${isAlert ? `Alerta en soldadura ${station.weld_id}/8` : "Sin alerta"}
            </p>
            <div class="mt-6 flex items-end justify-between gap-3">
                <div class="text-[10px] text-on-surface-variant">
                    ${hasEvent ? formatProcessSignal(station) : "Esperando telemetria"}
                </div>
                <div class="text-right">${action}</div>
            </div>
        </div>
    `;
}

function renderRecentLogRow(item) {
    const statusClass = item.status === "MALO"
        ? "bg-error-container text-error"
        : "bg-tertiary/10 text-tertiary";

    const action = item.alert_id
        ? `<a class="text-[10px] font-bold text-primary hover:text-primary-container transition-colors" href="/alerts/${item.alert_id}">Ver detalle</a>`
        : `<span class="text-[10px] text-on-surface-variant/60">Sin detalle</span>`;

    return `
        <tr class="border-b border-outline-variant/5 hover:bg-surface-low transition-colors">
            <td class="px-6 py-4 text-xs font-medium text-on-surface-variant">${formatTime(item.source_timestamp)}</td>
            <td class="px-6 py-4 text-xs font-mono text-primary">${item.pallet_id}</td>
            <td class="px-6 py-4 text-xs text-on-surface">${item.station_name}</td>
            <td class="px-6 py-4"><span class="rounded px-2 py-0.5 text-[10px] font-bold ${statusClass}">${item.status}</span></td>
            <td class="px-6 py-4 text-right">${action}</td>
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
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-error-container text-error">
                <span class="material-symbols-outlined">warning</span>
            </div>
            <div>
                <p class="text-xs font-bold text-on-surface">Alerta activa</p>
                <p class="text-[10px] text-on-surface-variant">${alert.message}</p>
            </div>
        </a>
    `;
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
    document.getElementById("stations-grid").innerHTML = data.stations.map(renderStationCard).join("");
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
}

loadDashboard();
setInterval(loadDashboard, 5000);
