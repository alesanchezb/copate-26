const historyState = {
    page: 1,
    totalPages: 1,
};

function formatDateTime(value) {
    const date = new Date(value);
    return {
        date: date.toLocaleDateString("es-MX"),
        time: date.toLocaleTimeString("es-MX", {
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

function formatMetric(value, decimals = 2, suffix = "") {
    if (value == null || Number.isNaN(Number(value))) return "--";
    return `${Number(value).toFixed(decimals)}${suffix}`;
}

function renderParameterStack(item) {
    return `
        <div class="grid min-w-[280px] grid-cols-3 gap-2 text-xs">
            <div><span class="text-on-surface-variant">Dist</span> <b>${formatMetric(item.distancia, 3)}</b></div>
            <div><span class="text-on-surface-variant">Fuerza</span> <b>${formatMetric(item.fuerza, 1)}</b></div>
            <div><span class="text-on-surface-variant">Watts</span> <b>${formatMetric(item.watts, 2)}</b></div>
            <div><span class="text-on-surface-variant">Amps</span> <b>${formatMetric(item.ampers, 2)}</b></div>
            <div><span class="text-on-surface-variant">Volts</span> <b>${formatMetric(item.volts, 2, " V")}</b></div>
            <div><span class="text-on-surface-variant">Weld</span> <b>${item.weld_id || "--"}</b></div>
        </div>
    `;
}

function renderModelLevel(item) {
    if (!item.model_level) return `<span class="text-[10px] font-bold text-on-surface-variant/50">Sin modelo</span>`;
    const isWarn = item.model_level === "POSIBLE_MALA" || item.model_level === "MALA";
    const classes = isWarn ? "status-pill-bad" : "bg-tertiary-container text-tertiary";
    const fallback = item.model_is_fallback ? " · fallback" : "";
    return `<span class="rounded px-2 py-0.5 text-[10px] font-bold ${classes}">${item.model_level}${fallback}</span>`;
}

function renderHistoryRow(item) {
    const when = formatDateTime(item.source_timestamp);
    const isAlert = item.status === "MALO";

    return `
        <tr class="${isAlert ? "history-row-bad" : ""} group transition-colors hover:bg-surface-high/20">
            <td class="px-4 py-3">
                <p class="text-sm font-medium text-on-surface">${when.date}</p>
                <p class="text-[10px] text-outline">${when.time}</p>
            </td>
            <td class="px-4 py-3 font-mono text-xs text-primary">${item.pallet_run_id || item.pallet_id}</td>
            <td class="px-4 py-3 text-sm text-on-surface">${item.station_name}</td>
            <td class="px-4 py-3 text-xs font-bold text-on-surface-variant">${item.schedule || "--"}</td>
            <td class="px-4 py-3 ${isAlert ? "text-red-alert" : "text-on-surface"}">${renderParameterStack(item)}</td>
            <td class="px-4 py-3">${renderModelLevel(item)}</td>
            <td class="px-4 py-3 text-center">
                <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-bold ${isAlert ? "status-pill-bad" : "bg-tertiary-container text-tertiary"}">
                    <span class="h-1.5 w-1.5 rounded-full ${isAlert ? "bg-red-alert" : "bg-tertiary"}"></span>
                    ${item.status}
                </span>
            </td>
            <td class="px-4 py-3 text-right">
                ${item.alert_id ? `<a class="alert-action-button rounded-xl px-3 py-1.5 text-[10px] font-bold text-white transition-all hover:brightness-105" href="/alerts/${item.alert_id}">Ver detalle</a>` : `<span class="text-[10px] font-bold text-on-surface-variant/50">Sin detalle</span>`}
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
        // Keep the existing label if the lightweight status refresh fails.
    }
}

function readFilters() {
    return {
        station: document.getElementById("station-filter").value,
        status: document.getElementById("status-filter").value,
        pallet: document.getElementById("pallet-filter").value.trim(),
        date_from: document.getElementById("date-from").value,
        date_to: document.getElementById("date-to").value,
    };
}

function populateStationOptions(stations) {
    const select = document.getElementById("station-filter");
    if (select.dataset.loaded === "true") {
        return;
    }

    for (const station of stations) {
        const option = document.createElement("option");
        option.value = station.station_code;
        option.textContent = station.display_name;
        select.appendChild(option);
    }
    select.dataset.loaded = "true";
}

async function loadHistory(page = 1) {
    historyState.page = page;
    const params = new URLSearchParams({
        page: String(page),
        page_size: "10",
    });

    const filters = readFilters();
    Object.entries(filters).forEach(([key, value]) => {
        if (value) {
            params.set(key, value);
        }
    });

    let data;
    try {
        const response = await fetch(`/api/history?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        data = await response.json();
    } catch (error) {
        document.getElementById("history-table-body").innerHTML = `
            <tr>
                <td class="px-6 py-6 text-sm font-semibold text-primary-container" colspan="8">
                    No fue posible cargar el historial: ${error.message}
                </td>
            </tr>
        `;
        document.getElementById("pagination-summary").textContent = "Error cargando historial";
        return;
    }

    historyState.totalPages = data.total_pages;
    populateStationOptions(data.station_options || []);
    document.getElementById("line-label-sidebar").textContent = data.metadata.line_label;
    document.getElementById("operator-name").textContent = data.metadata.operator_name;
    document.getElementById("operator-line-label").textContent = data.metadata.operator_line_label;

    document.getElementById("history-table-body").innerHTML = data.items.map(renderHistoryRow).join("");
    document.getElementById("pagination-summary").textContent = `Pagina ${data.page} de ${data.total_pages} | ${data.total_records} registros`;
    document.getElementById("page-indicator").textContent = String(data.page);
    document.getElementById("summary-total").textContent = Number(data.summary.total_analyzed || 0).toLocaleString("es-MX");
    document.getElementById("summary-success").textContent = `${Number(data.summary.success_rate || 0).toFixed(1)}%`;
    document.getElementById("summary-errors").textContent = Number(data.summary.errors || 0).toLocaleString("es-MX");
    document.getElementById("summary-line").textContent = data.summary.active_line || "CONTROL";

    document.getElementById("prev-page").disabled = data.page <= 1;
    document.getElementById("next-page").disabled = data.page >= data.total_pages;
}

document.getElementById("history-filters").addEventListener("submit", (event) => {
    event.preventDefault();
    loadHistory(1);
});

document.getElementById("prev-page").addEventListener("click", () => {
    if (historyState.page > 1) {
        loadHistory(historyState.page - 1);
    }
});

document.getElementById("next-page").addEventListener("click", () => {
    if (historyState.page < historyState.totalPages) {
        loadHistory(historyState.page + 1);
    }
});

loadHistory();
loadTelemetryStatus();
setInterval(loadTelemetryStatus, 10000);
