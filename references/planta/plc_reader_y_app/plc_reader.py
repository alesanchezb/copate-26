from threading import Thread, Lock
from datetime import datetime
from pytz import timezone
from pylogix import PLC
import time
from collections import deque
import logging

from database import (
    store_data,
    store_reject_fault,
    get_or_create_reject_index_uid
)
from utils import validate_plc_data
from config import rejects_configuration

# ============================================================
# ======================= PALLETS ============================
# ============================================================

PALLET_CELLS = {
    "cell_40": {
        "ip": "172.16.15.1",
        "values": deque(maxlen=25),
        "unique_counts": {},
        "last_value": None,
        "status_debug": {"last_status": None, "last_value": None, "timestamp": None},
        "lock": Lock()
    },
    "cell_10": {
        "ip": "172.16.7.1",
        "values": deque(maxlen=25),
        "unique_counts": {},
        "last_value": None,
        "status_debug": {"last_status": None, "last_value": None, "timestamp": None},
        "lock": Lock()
    },
    "cell_50": {
        "ip": "172.16.41.1",
        "values": deque(maxlen=25),
        "unique_counts": {},
        "last_value": None,
        "status_debug": {"last_status": None, "last_value": None, "timestamp": None},
        "lock": Lock()
    }
}

def monitor_pallet_cell(cell):
    cfg = PALLET_CELLS[cell]

    with PLC() as comm:
        comm.IPAddress = cfg["ip"]

        while True:
            try:
                result = comm.Read("PalletAdress")
                now = datetime.now().strftime("%H:%M:%S")

                with cfg["lock"]:
                    cfg["status_debug"]["last_status"] = result.Status
                    cfg["status_debug"]["timestamp"] = now

                    if result.Status == "Success":
                        val = result.Value
                        cfg["last_value"] = val
                        cfg["status_debug"]["last_value"] = val

                        if not cfg["values"] or val != cfg["values"][-1]:
                            cfg["values"].append(val)
                            cfg["unique_counts"] = {
                                v: cfg["values"].count(v)
                                for v in set(cfg["values"])
                            }
                    else:
                        cfg["status_debug"]["last_value"] = None

            except Exception as exc:
                logging.exception(f"❌ Error pallets {cell}: {exc}")

            time.sleep(1)

# ---------- Getters Pallets ----------

def get_pallet_values(cell):
    with PALLET_CELLS[cell]["lock"]:
        return list(PALLET_CELLS[cell]["values"])

def get_unique_counts(cell):
    with PALLET_CELLS[cell]["lock"]:
        return dict(PALLET_CELLS[cell]["unique_counts"])

def get_last_pallet_value(cell):
    with PALLET_CELLS[cell]["lock"]:
        return PALLET_CELLS[cell]["last_value"]

def get_pallet_debug_status(cell):
    with PALLET_CELLS[cell]["lock"]:
        return dict(PALLET_CELLS[cell]["status_debug"])

def reset_pallet_data(cell):
    with PALLET_CELLS[cell]["lock"]:
        PALLET_CELLS[cell]["values"].clear()
        PALLET_CELLS[cell]["unique_counts"].clear()
        PALLET_CELLS[cell]["last_value"] = None

def get_probable_duplicate_ids(cell):
    values = get_pallet_values(cell)
    seen = {}
    total_unique = len(set(v for v in values if v != 0))
    duplicates = []

    for idx, val in enumerate(values):
        if val == 0:
            continue
        if val in seen and (idx - seen[val]) < total_unique:
            duplicates.append(val)
        seen[val] = idx

    return list(set(duplicates))

# Tags dinámicos según estación y schedule
TAGS_TEMPLATE = {
    "Sch1St1": ["ForceLastSch1St1", "DistLastSch1St1", "AmpsLastSch1St1", "VoltsLastSch1St1", "WattsLastSch1St1", "ElctCtrSch1St1", "PalletIdSch1St1", "NewDataSch1St1HndShk"],
    "Sch2St1": ["ForceLastSch2St1", "DistLastSch2St1", "AmpsLastSch2St1", "VoltsLastSch2St1", "WattsLastSch2St1", "ElctCtrSch2St1", "PalletIdSch2St1", "NewDataSch2St1HndShk"],
    "Sch1St2": ["ForceLastSch1St2", "DistLastSch1St2", "AmpsLastSch1St2", "VoltsLastSch1St2", "WattsLastSch1St2", "ElctCtrSch1St2", "PalletIdSch1St2", "NewDataSch1St2HndShk"],
    "Sch2St2": ["ForceLastSch2St2", "DistLastSch2St2", "AmpsLastSch2St2", "VoltsLastSch2St2", "WattsLastSch2St2", "ElctCtrSch2St2", "PalletIdSch2St2", "NewDataSch2St2HndShk"],
}


# Monitorea un PLC específico
def monitor_plc(plc_ip, stations):
    tz = timezone('America/Hermosillo')
    with PLC() as comm:
        comm.IPAddress = plc_ip
        while True:
            for i, station_name in enumerate(stations, 1):
                schedules = ["Sch1", "Sch2"]

                if station_name == "Toroide":
                    schedules = ["Sch1"]

                for sch in schedules:
                    data_flag_tag = f"NewData{sch}St{i}"
                    if comm.Read(data_flag_tag).Value == 1:
                        tags = TAGS_TEMPLATE[f"{sch}St{i}"]

                        # Lecturas ordenadas
                        plc_values = [comm.Read(tag).Value for tag in tags[:5]]        # Force, Dist, Amps, Volts, Watts
                        
                        electrode_res = comm.Read(tags[5]).Value
                        pallet_id = comm.Read(tags[6]).Value                           # PalletId

                        if validate_plc_data(plc_values):
                            timestamp = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
                            store_data(
                                timestamp,
                                distancia=plc_values[1],
                                fuerza=plc_values[0],
                                ampers=plc_values[2],
                                volts=plc_values[3],
                                watts=plc_values[4],
                                estacion=station_name,
                                sch=sch,
                                plc_ip=plc_ip,
                                pallet_id=pallet_id,
                                electrodecount=electrode_res
                            )

                            # Handshake
                            comm.Write(tags[-1], 1)
                            time.sleep(0.25)
                            comm.Write(tags[-1], 0)
                        else:
                            print(f"[ERROR] Datos inválidos del PLC {plc_ip}, estación {station_name}, schedule {sch}, valores: {plc_values}")


            time.sleep(0.5)

# Inicia múltiples PLCs usando threads
def start_plc_threads(plc_configs, rejects_configs):
    # ---- PLCs de proceso (SIN CAMBIOS) ----
    for plc_ip, stations in plc_configs.items():
        Thread(
            target=monitor_plc,
            args=(plc_ip, stations),
            daemon=True
        ).start()

    # ---- Rejects (SIN CAMBIOS) ----
    for plc_ip, config in rejects_configs.items():
        name = config.get("name", "Unnamed")
        routines = config.get("routines", [])
        Thread(
            target=monitor_rejects,
            args=(plc_ip, name, routines),
            daemon=True
        ).start()

    # ---- Pallets (NUEVO, CORRECTO) ----
    for cell in PALLET_CELLS:
        Thread(
            target=monitor_pallet_cell,
            args=(cell,),
            daemon=True
        ).start()

#Funciones para contadores de piezas en celda 10.
def read_oee_arrays():
    plc_ip = "172.16.8.1"
    log_path = "oee_debug.log"  # Archivo de log
    with open(log_path, "a") as f:
        f.write(f"\n[{datetime.now()}] Intentando leer OEE arrays de {plc_ip}\n")

    with PLC() as comm:
        comm.IPAddress = plc_ip

        # Usa el scope correcto para cada tag
        good_s1 = comm.Read(f'C10_Good_Parts_S1', count=32)
        bad_s1  = comm.Read(f'C10_Bad_Parts_S1', count=32)
        good_s2 = comm.Read(f'C10_Good_Parts_S2', count=32)
        bad_s2  = comm.Read(f'C10_Bad_Parts_S2', count=32)

        #good_s1 = comm.Read(f'OEE_Good_Parts_Shift_1', count=32)
        #bad_s1  = comm.Read(f'OEE_Bad_Parts_Shift_1', count=32)
        #good_s2 = comm.Read(f'OEE_Good_Parts_Shift_2', count=32)
        #bad_s2  = comm.Read(f'OEE_Bad_Parts_Shift_2', count=32)

        with open(log_path, "a") as f:
            f.write(f"good_s1.Status={good_s1.Status} Value={good_s1.Value}\n")
            f.write(f"bad_s1.Status={bad_s1.Status} Value={bad_s1.Value}\n")
            f.write(f"good_s2.Status={good_s2.Status} Value={good_s2.Value}\n")
            f.write(f"bad_s2.Status={bad_s2.Status} Value={bad_s2.Value}\n")

        results = {
            'good_s1': good_s1.Value if good_s1.Status == 'Success' else [None]*32,
            'bad_s1':  bad_s1.Value  if bad_s1.Status  == 'Success' else [None]*32,
            'good_s2': good_s2.Value if good_s2.Status == 'Success' else [None]*32,
            'bad_s2':  bad_s2.Value  if bad_s2.Status  == 'Success' else [None]*32
        }
    return results

def monitor_oee_arrays():
    plc_ip = "172.16.8.1"
    while True:
        oee_data = read_oee_arrays()
        # Aquí decides qué hacer: ¿guardar en DB, exponer vía Flask, etc?
        print("[OEE]", oee_data)  # Por ahora solo imprime
        time.sleep(5)  # cada 5 segundos, ajusta el intervalo como prefieras

MAX_REJECTS = 20
last_reject_counters = {}

def monitor_rejects(plc_ip, plc_name, routines):
    global last_reject_counters

    logging.info(f"📌 monitor_rejects iniciado para {plc_name} ({plc_ip}) con rutinas {routines}")

    # Inicializa memoria si no existe
    if plc_ip not in last_reject_counters:
        last_reject_counters[plc_ip] = {
            r: [{
                "name": "",
                "number": None,   # 👈 CLAVE: None indica “no inicializado”
                "enable": 0,
                "last_reject_timestamp": None
            } for _ in range(MAX_REJECTS)]
            for r in routines
        }

    with PLC() as comm:
        comm.IPAddress = plc_ip

        while True:
            for routine in routines:
                logging.debug(f"🔁 Verificando rutina {routine} en {plc_ip}")

                for idx in range(MAX_REJECTS):
                    base_tag = f"Program:{routine}.StaRejects.Data[{idx}]"

                    # ---- Leer Enable ----
                    enable_res = comm.Read(f"{base_tag}.Enable")
                    if enable_res.Status != "Success":
                        continue
                    enable = enable_res.Value

                    # ---- Leer Name ----
                    name_res = comm.Read(f"{base_tag}.Name")
                    if name_res.Status != "Success":
                        continue
                    name = name_res.Value
                    name = (
                        name.decode("utf-8", errors="ignore").strip("\x00")
                        if isinstance(name, bytes)
                        else str(name)
                    )

                    # ---- Leer Number ----
                    num_res = comm.Read(f"{base_tag}.Number")
                    if num_res.Status != "Success":
                        continue
                    number = num_res.Value

                    prev_data = last_reject_counters[plc_ip][routine][idx]
                    prev_number = prev_data["number"]

                    logging.debug(
                        f"👀 {routine}[{idx}] Enable={enable} "
                        f"Name='{name}' Prev={prev_number} Now={number}"
                    )

                    # ==================================================
                    # PRIMERA LECTURA → SOLO INICIALIZA (NO GUARDA)
                    # ==================================================
                    if prev_number is None:
                        prev_data.update({
                            "name": name,
                            "number": number,
                            "enable": enable
                        })
                        continue

                    # ==================================================
                    # INCREMENTO REAL → GUARDAR RECHAZO
                    # ==================================================
                    if enable == 1 and isinstance(number, (int, float)) and number > prev_number:
                        pallet_res = comm.Read(f"Program:{routine}.PalletID_Hist")
                        pallet_id = pallet_res.Value if pallet_res.Status == "Success" else None

                        now_str = datetime.now(
                            timezone("America/Hermosillo")
                        ).strftime("%Y-%m-%d %H:%M:%S")

                        index_uid = get_or_create_reject_index_uid(plc_ip, routine, idx)

                        logging.info(
                            f"🚨 RECHAZO | {plc_name} | {routine}[{idx}] "
                            f"{name}: {prev_number} → {number} PalletID={pallet_id}"
                        )

                        try:
                            store_reject_fault(
                                timestamp=now_str,
                                plc_ip=plc_ip,
                                plc_name=plc_name,
                                routine=routine,
                                reject_name=name,
                                reject_counter=number,
                                pallet_id=str(pallet_id),
                                index_uid=index_uid
                            )
                            prev_data["last_reject_timestamp"] = now_str
                            logging.info("✔️ RejectFault guardado correctamente")
                        except Exception as exc:
                            logging.exception(f"❌ Error DB RejectFault: {exc}")

                    # ==================================================
                    # RESET DE CONTADOR → SOLO LOG
                    # ==================================================
                    elif isinstance(number, (int, float)) and number < prev_number:
                        logging.info(
                            f"🔄 Reset de contador | {plc_name} | "
                            f"{routine}[{idx}] {name}: {prev_number} → {number}"
                        )

                    # ---- Actualizar memoria SIEMPRE ----
                    prev_data.update({
                        "name": name,
                        "number": number,
                        "enable": enable
                    })

            time.sleep(1)

def get_current_rejects():
    """
    Retorna todos los StaRejects habilitados (Enable == 1),
    con su nombre, contador actual y último timestamp de rechazo (si existe).
    """
    results = []    

    for plc_ip, plc_data in last_reject_counters.items():
        plc_name = rejects_configuration.get(plc_ip, {}).get("name", plc_ip)

        for routine, reject_list in plc_data.items():
            for idx, data in enumerate(reject_list):

                if data.get("enable", 0) != 1:
                    continue

                # Obtener el unique_id desde la tabla de índices
                unique_id = get_or_create_reject_index_uid(plc_ip, routine, idx)

                results.append({
                    "cell": rejects_configuration.get(plc_ip, {}).get("cell", None),
                    "unique_id": unique_id,
                    "plc_ip": plc_ip,
                    "plc_name": plc_name,
                    "routine": routine,
                    "index": idx,
                    "reject_name": data.get("name", ""),
                    "reject_counter": data.get("number", 0),
                    "last_reject_timestamp": data.get("last_reject_timestamp")
                })

    return results

