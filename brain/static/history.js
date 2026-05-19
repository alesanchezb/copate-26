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

function renderHistoryRow(item) {
    const when = formatDateTime(item.source_timestamp);
    const isAlert = item.status === "MALO";
    const amps = item.ampers == null ? item.corriente : item.ampers;
    const volts = item.volts == null ? item.voltaje : item.volts;

    return `
        <tr class="${isAlert ? "bg-error-container/5 border-l-4 border-error/50" : ""} group transition-colors hover:bg-surface-high/20">
            <td class="px-6 py-4">
                <p class="text-sm font-medium text-on-surface">${when.date}</p>
                <p class="text-[10px] text-outline">${when.time}</p>
            </td>
            <td class="px-6 py-4 font-mono text-sm text-primary">${item.pallet_id}</td>
            <td class="px-6 py-4 text-sm text-on-surface">${item.station_name}</td>
            <td class="px-6 py-4 text-right text-sm ${isAlert ? "text-primary-container font-medium" : "text-on-surface"}">${amps == null ? "--" : Number(amps).toFixed(2)}</td>
            <td class="px-6 py-4 text-right text-sm ${isAlert ? "text-primary-container/80" : "text-on-surface"}">${volts == null ? "--" : Number(volts).toFixed(2)} V</td>
            <td class="px-6 py-4 text-center">
                <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-bold ${isAlert ? "bg-error-container text-error" : "bg-tertiary-container text-tertiary"}">
                    <span class="h-1.5 w-1.5 rounded-full ${isAlert ? "bg-primary-container" : "bg-tertiary"}"></span>
                    ${item.status}
                </span>
            </td>
            <td class="px-6 py-4 text-right">
                ${item.alert_id ? `<a class="rounded-xl bg-primary-container px-3 py-1.5 text-[10px] font-bold text-white transition-all hover:brightness-105" href="/alerts/${item.alert_id}">Ver detalle</a>` : `<span class="text-[10px] font-bold text-on-surface-variant/50">Sin detalle</span>`}
            </td>
        </tr>
    `;
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
        page_size: "15",
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
                <td class="px-6 py-6 text-sm font-semibold text-primary-container" colspan="7">
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
