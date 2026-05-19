import os
import time
import threading
import socket
import calendar
import csv
import sqlite3
import logging
import sys
import pandas as pd
import re
import traceback

from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from database import create_database, init_rejects_db, create_reject_index_map_table
from utils import calculate_cpk, sanitize_string
from plc_reader import (
    get_unique_counts, get_last_pallet_value, get_pallet_values,
    get_probable_duplicate_ids, get_pallet_debug_status,
    reset_pallet_data,
    #####
    start_plc_threads, get_current_rejects
)

from threading import Thread
from plc_reader import read_oee_arrays
from config import plc_configuration, rejects_configuration
from datetime import datetime
from pytz import timezone
######################################################################
#  Seccion para cachar error4es de arrance de la app borrar cuando no sea necesaria
######################################################################
with open("logs/test_app_starting.txt", "a", encoding="utf-8") as f:
    f.write(f"[APP] Iniciando app.py - {datetime.now()}\n")

def write_startup_error(exc):
    try:
        tz = timezone("America/Hermosillo")
        with open("logs/startup_error.txt", "a", encoding="utf-8") as f:
            f.write(
                f"\n[{datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}] ERROR DE ARRANQUE:\n"
            )
            traceback.print_exception(
                exc.__class__, exc, exc.__traceback__, file=f
            )
    except Exception:
        pass

try:
######################################################################
#  Seccion para cachar error4es de arrance de la app
######################################################################
    
    # ======================================================
    # Logging configurado con zona horaria de Hermosillo
    # ======================================================

    hermosillo_tz = timezone('America/Hermosillo')
    LOG_DIR = "logs"
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_filename = os.path.join(
        LOG_DIR,
        f"log_{datetime.now(hermosillo_tz).strftime('%Y-%m-%d')}.txt"
    )

    def hermosillo_time(*args):
        return datetime.now(hermosillo_tz).timetuple()

    logging.basicConfig(
        filename=log_filename,
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        encoding='utf-8'
    )
    logging.Formatter.converter = hermosillo_time

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        logging.critical("❌ Error no capturado", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    logging.info("✅ app.py iniciado correctamente (pre-Flask)")

    # ======================================================
    # Flask + Variables Globales
    # ======================================================

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    app = Flask(__name__)
    socketio = SocketIO(app)

    auto_backup_enabled = False
    DB_PATH = r'Z:\DB_Cell10_All_PartsInOut.db'
    ENABLE_DBBCK = 0

    def check_connection(ip):
        """Verifica si una IP está activa probando conexión al puerto 502 (Modbus TCP)."""
        try:
            sock = socket.create_connection((ip, 44818), timeout=1)
            sock.close()
            return True  # Conectado
        except (socket.timeout, ConnectionRefusedError):
            return False  # No conectado

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/station/<station>')
    def station_page(station):
        return render_template('station.html', station=station)

    @app.route('/template/<station>/<schedule>')
    def template_page(station, schedule):
        return render_template('template.html', station=station, schedule=schedule)

    @app.route('/parameters')
    def show_parameters():
        page = int(request.args.get("page", 1))  # Página actual
        per_page = 50                            # Registros por página
        offset = (page - 1) * per_page

        conn = sqlite3.connect(os.path.join(BASE_DIR, 'WeldParameters.db'))
        cursor = conn.cursor()

        # Contar registros totales
        cursor.execute("SELECT COUNT(*) FROM Parameters")
        total_records = cursor.fetchone()[0]
        total_pages = (total_records + per_page - 1) // per_page  # redondeo hacia arriba

        # Traer solo la página actual (ordenados descendente por ID)
        cursor.execute("SELECT * FROM Parameters ORDER BY id DESC LIMIT ? OFFSET ?", (per_page, offset))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        conn.close()

        return render_template(
            'dataparameters.html',
            rows=rows,
            columns=columns,
            page=page,
            total_pages=total_pages
        )

    @app.route('/delete_parameters', methods=['POST'])
    def delete_parameters():
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'WeldParameters.db'))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Parameters")
        conn.commit()
        conn.close()
        return jsonify({"message": "Datos eliminados correctamente"})

    @app.route('/export_parameters')
    def export_parameters():
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'WeldParameters.db'))
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Parameters")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        
        csv_file = os.path.join(BASE_DIR, "parameters_export.csv")
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        conn.close()
        return send_file(csv_file, as_attachment=True)

    @app.route('/import_parameters', methods=['POST'])
    def import_parameters():
        if "file" not in request.files:
            return jsonify({"message": "No se envió archivo"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"message": "Archivo no seleccionado"}), 400

        file_path = os.path.join(BASE_DIR, "parameters_import.csv")
        file.save(file_path)

        conn = sqlite3.connect(os.path.join(BASE_DIR, 'WeldParameters.db'))
        cursor = conn.cursor()
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            columns = next(reader)
            query = f"INSERT INTO Parameters ({', '.join(columns)}) VALUES ({', '.join(['?' for _ in columns])})"
            for row in reader:
                cursor.execute(query, row)

        conn.commit()
        conn.close()
        os.remove(file_path)
        return jsonify({"message": "Datos importados correctamente"})

    @app.route('/monitor')
    def monitor():
        """Renderiza la página de monitoreo de IPs."""
        return render_template('monitor.html')

    @app.route('/get_connections')
    def get_connections():
        """Retorna el estado de conexión de cada IP en formato JSON."""
        connections = [{"ip": ip, "status": check_connection(ip)} for ip in plc_configuration.keys()]
        return jsonify(connections)

    @socketio.on('get_data')
    def handle_get_data(data):
        station = data['station']
        schedule = data['schedule']
        offset = int(data.get('offset', 0))  # Por default, 0

        if not str(schedule).startswith("Sch"):
            sch_value = "Sch" + str(schedule)
        else:
            sch_value = schedule

        print(f"[DEBUG] Buscando estación='{station}', sch='{sch_value}', offset={offset}")

        with sqlite3.connect('WeldParameters.db') as conn:
            df = pd.read_sql(
                "SELECT * FROM Parameters WHERE estacion=? AND sch=? ORDER BY id DESC LIMIT 100 OFFSET ?",
                conn,
                params=(station, sch_value, offset)
            )

        if df.empty:
            emit('update_graph', {
                "timestamp": [],
                "distancia": [],
                "fuerza": [],
                "ampers": [],
                "volts": [],
                "watts": [],
                "stats": {}
            })
            return

        df = df.iloc[::-1]

        # 🔧 FUERZA columnas numéricas (FIX CRÍTICO)
        numeric_cols = ['distancia', 'fuerza', 'ampers', 'volts', 'watts']

        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna(subset=numeric_cols)

        if df.empty:
            emit('update_graph', {
                "timestamp": [],
                "distancia": [],
                "fuerza": [],
                "ampers": [],
                "volts": [],
                "watts": [],
                "stats": {}
            })
            return


        # ✅ Construir payload para el frontend
        # Nota: asegúrate que tu tabla tenga columna "timestamp"
        if "timestamp" in df.columns:
            ts = df["timestamp"].astype(str).tolist()
        else:
            # fallback por si tu DB no tiene timestamp (mejor tenerlo)
            ts = [str(x) for x in df.index.tolist()]

        stats = {}
        for col in numeric_cols:
            s = df[col]
            stats[col] = {
                "mean": float(s.mean()) if len(s) else 0.0,
                "std_dev": float(s.std()) if len(s) > 1 else 0.0
            }

        emit('update_graph', {
            "timestamp": ts,
            "distancia": df["distancia"].tolist(),
            "fuerza": df["fuerza"].tolist(),
            "ampers": df["ampers"].tolist(),
            "volts": df["volts"].tolist(),
            "watts": df["watts"].tolist(),
            "stats": stats,
            "offset": offset
        })

    ###########################################################################
    # ======================= PALLETS (UNIFICADO) =============================
    ###########################################################################

    CELL_ALIASES = {
        "10": "cell_10",
        "40": "cell_40",
        "50": "cell_50",
        "cell_10": "cell_10",
        "cell_40": "cell_40",
        "cell_50": "cell_50",
        "c10": "cell_10",
        "c40": "cell_40",
        "c50": "cell_50",
    }

    def normalize_cell(cell):
        return CELL_ALIASES.get((cell or "").strip().lower())

    @app.route('/pallet_counts')
    def pallet_counts():
        try:
            counts_raw = get_unique_counts("cell_40")
            counts = {k: v for k, v in counts_raw.items() if k != 0}
            log_text = f"Conteos: {counts}"
            return jsonify({
                "counts": counts,
                "log": log_text
            })
        except Exception as e:
            print(f"[ERROR] en /pallet_counts: {e}")
            return jsonify({"error": f"Algo salió mal: {str(e)}"}), 500

    @app.route('/pallet_value')
    def pallet_value():
        value = get_last_pallet_value("cell_40")
        return jsonify({"pallet_value": value})

    @app.route('/pallet_debug')
    def pallet_debug():
        return jsonify(get_pallet_debug_status("cell_40"))

    @app.route('/pallets')
    def pallet_table():
        values = get_pallet_values("cell_40")
        data = [(i + 1, val) for i, val in enumerate(values)]
        return render_template('pallets.html', pallet_data=data, total=len(set(values)), cell="cell_40")

    @app.route('/pallet_data')
    def pallet_data():
        values = get_pallet_values("cell_40")
        valid_values = [v for v in values if v != 0]
        contains_zero = any(v == 0 for v in values)
        duplicates = get_probable_duplicate_ids("cell_40")
        reversed_values = list(reversed(values))
        data = [{"pos": i + 1, "id": v} for i, v in enumerate(reversed_values)]
        return jsonify({
            "data": data,
            "total": len(set(valid_values)),
            "has_zero": contains_zero,
            "duplicates": duplicates
        })

    @app.route('/reset_pallets', methods=['POST'])
    def reset_pallets():
        reset_pallet_data("cell_40")
        return jsonify({"status": "ok"})

    @app.route("/api/pallets/<cell>/counts")
    def api_pallet_counts(cell):
        if cell not in ("cell_10", "cell_40", "cell_50"):
            return jsonify({"error": "Celda inválida"}), 400

        counts_raw = get_unique_counts(cell)
        counts = {k: v for k, v in counts_raw.items() if k != 0}
        return jsonify({"counts": counts})

    @app.route("/api/pallets/<cell>/data")
    def api_pallet_data(cell):
        if cell not in ("cell_10", "cell_40", "cell_50"):
            return jsonify({"error": "Celda inválida"}), 400

        values = get_pallet_values(cell)
        duplicates = get_probable_duplicate_ids(cell)
        valid = [v for v in values if v != 0]

        return jsonify({
            "data": [{"pos": i+1, "id": v} for i, v in enumerate(reversed(values))],
            "total": len(set(valid)),
            "has_zero": any(v == 0 for v in values),
            "duplicates": duplicates
        })


    @app.route("/api/pallets/<cell>/reset", methods=["POST"])
    def api_pallet_reset(cell):
        if cell not in ("cell_10", "cell_40", "cell_50"):
            return jsonify({"error": "Celda inválida"}), 400

        reset_pallet_data(cell)
        return jsonify({"status": "ok"})

    @app.route("/pallet_view/<cell>")
    def pallet_view(cell):
        norm = normalize_cell(cell)
        if not norm:
            return "Celda inválida", 404
        return render_template("pallets.html", cell=norm)

    ###########################################################################
    ###########################################################################
    ###########################################################################
    # ---------- Celda 10: Pallets ----------
    @app.route('/pallet_counts_10')
    def pallet_counts_10():
        try:
            counts_raw = get_unique_counts("cell_10")
            counts = {k: v for k, v in counts_raw.items() if k != 0}
            return jsonify({"counts": counts, "log": f"Conteos: {counts}"})
        except Exception as e:
            print(f"[ERROR] en /pallet_counts_10: {e}")
            return jsonify({"error": f"Algo salió mal: {str(e)}"}), 500

    @app.route('/pallet_value_10')
    def pallet_value_10():
        value = get_last_pallet_value("cell_10")
        return jsonify({"pallet_value": value})

    @app.route('/pallet_debug_10')
    def pallet_debug_10():
        return jsonify(get_pallet_debug_status("cell_10"))

    @app.route('/pallets_10')
    def pallet_table_10():
        return redirect(url_for('pallet_view', cell='cell_10'))

    @app.route('/pallet_data_10')
    def pallet_data_10():
        values = get_pallet_values("cell_10")
        valid_values = [v for v in values if v != 0]
        contains_zero = any(v == 0 for v in values)
        duplicates = get_probable_duplicate_ids("cell_10")
        reversed_values = list(reversed(values))
        data = [{"pos": i + 1, "id": v} for i, v in enumerate(reversed_values)]
        return jsonify({
            "data": data,
            "total": len(set(valid_values)),
            "has_zero": contains_zero,
            "duplicates": duplicates
        })

    @app.route('/reset_pallets_10', methods=['POST'])
    def reset_pallets_10_route():
        reset_pallet_data("cell_10")
        return jsonify({"status": "ok"})

######################################################################################

# ---------- Celda 50: Pallets ----------
    @app.route('/pallet_counts_50')
    def pallet_counts_50():
        try:
            counts_raw = get_unique_counts("cell_50")
            counts = {k: v for k, v in counts_raw.items() if k != 0}
            return jsonify({"counts": counts, "log": f"Conteos: {counts}"})
        except Exception as e:
            print(f"[ERROR] en /pallet_counts_50: {e}")
            return jsonify({"error": f"Algo salió mal: {str(e)}"}), 500

    @app.route('/pallet_value_50')
    def pallet_value_50():
        value = get_last_pallet_value("cell_50")
        return jsonify({"pallet_value": value})

    @app.route('/pallet_debug_50')
    def pallet_debug_50():
        return jsonify(get_pallet_debug_status("cell_50"))

    @app.route('/pallets_50')
    def pallet_table_50():
        return redirect(url_for('pallet_view', cell='cell_50'))

    @app.route('/pallet_data_50')
    def pallet_data_50():
        values = get_pallet_values("cell_50")
        valid_values = [v for v in values if v != 0]
        contains_zero = any(v == 0 for v in values)
        duplicates = get_probable_duplicate_ids("cell_50")
        reversed_values = list(reversed(values))
        data = [{"pos": i + 1, "id": v} for i, v in enumerate(reversed_values)]
        return jsonify({
            "data": data,
            "total": len(set(valid_values)),
            "has_zero": contains_zero,
            "duplicates": duplicates
        })

    @app.route('/reset_pallets_50', methods=['POST'])
    def reset_pallets_50_route():
        reset_pallet_data("cell_50")
        return jsonify({"status": "ok"})

    ######################################################################################
    ###########################################################################
    ###########################################################################
    ###########################################################################

    @app.route('/search_serial')
    def search_serial():
        serial = request.args.get('serial', '').strip().lower()
        if not serial:
            return jsonify({"results": []})

        messages = []

        # --- Función auxiliar para generar el mensaje con un registro ---
        def build_message(record):
            serial_value = str(record.get("SerialNumbIN", "")).replace("\x00", "").strip()
            year = record.get("Year", "")
            month = record.get("Month", "")
            day = record.get("Day", "")
            hour = record.get("Hour", "")
            minute = record.get("Minute", "")
            sec = record.get("Sec", "")
            in_val = record.get("In", 0)
            out_val = record.get("Out", 0)
            good = record.get("Good", 0)
            ng = record.get("NG", 0)
            reject_station = record.get("Reject_Station", record.get("Rejects_Satation", ""))
            complete_station = record.get("Complete_Station", "")

            try:
                month_abbr = calendar.month_abbr[int(month)]
                date_time_str = f"{int(day):02d}-{month_abbr}-{int(year):04d} {int(hour):02d}:{int(minute):02d}:{int(sec):02d}"
            except Exception:
                date_time_str = f"{day}-{month}-{year} {hour}:{minute}:{sec}"

            status_message = "Entró a la celda" if int(in_val) == 1 else "Salió de la celda" if int(out_val) == 1 else "Estado desconocido"
            quality = "Good" if int(good) == 1 else "NG" if int(ng) == 1 else "No especificado"

            return (
                f"Pieza con Serial '{serial_value}' {status_message} {date_time_str}Hrs. "
                f"Resultado: {quality}. Reject Station: {reject_station}, Complete Station: {complete_station}."
            )

        # --- Búsqueda en base de datos activa ---
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM DB_Cell10 WHERE LOWER(SerialNumbIN) LIKE ?", (serial + '%',))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        conn.close()

        for row in rows:
            record = dict(zip(columns, row))
            messages.append(build_message(record))

        # --- Si no se encontró nada, buscar en backups ---
        if not messages:
            backup_dir = os.path.join(BASE_DIR, "DB_Cell10_All_PartsInOut_Backups")
            if os.path.exists(backup_dir):
                for file in os.listdir(backup_dir):
                    if file.endswith(".xlsx"):
                        filepath = os.path.join(backup_dir, file)
                        try:
                            df = pd.read_excel(filepath, dtype=str)
                            df.fillna("", inplace=True)
                            matched = df[df["SerialNumbIN"].str.lower().str.startswith(serial)]
                            for _, record in matched.iterrows():
                                messages.append(build_message(record))
                        except Exception as e:
                            print(f"❌ Error leyendo backup {file}: {e}")

        return jsonify({"results": messages})

    # ----------------------------
    # Funciones para respaldo automático
    # ----------------------------

    def backup_database(automatic, num_records=None):
        """
        Función que realiza el respaldo de la base de datos DB_Cell10_All_PartsInOut.db.
        Devuelve: backup_filename, mensaje y cantidad de registros respaldados.
        """
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        Max_Records_OnDB = 20000000

        if automatic:
            cursor.execute("SELECT COUNT(*) FROM DB_Cell10")
            total_records = cursor.fetchone()[0]
            if total_records < Max_Records_OnDB:
                conn.close()
                return None, f"Aún no se han acumulado 200,000 registros (actual: {total_records}). Mantenimiento automático no ejecutado.", 0
            cursor.execute("SELECT * FROM DB_Cell10 ORDER BY SerialNumbIN ASC")
            records = cursor.fetchall()
        else:
            if num_records is None or str(num_records).lower() == "todos":
                cursor.execute("SELECT * FROM DB_Cell10 ORDER BY SerialNumbIN ASC")
                records = cursor.fetchall()
            else:
                try:
                    num = int(num_records)
                except ValueError:
                    conn.close()
                    raise ValueError("Número de registros inválido")
                cursor.execute("SELECT * FROM DB_Cell10 ORDER BY SerialNumbIN ASC LIMIT ?", (num,))
                records = cursor.fetchall()

        if not records:
            conn.close()
            return None, "No hay registros para respaldar.", 0

        columns = [description[0] for description in cursor.description]
        df = pd.DataFrame(records, columns=columns)

        first_serial = df.iloc[0]["SerialNumbIN"].replace("\x00", "").strip() if not df.empty else "no_serial"
        last_serial = df.iloc[-1]["SerialNumbIN"].replace("\x00", "").strip() if not df.empty else "no_serial"
        date_str = datetime.now().strftime("%d-%b-%Y")

        backup_folder = os.path.join(BASE_DIR, "DB_Cell10_All_PartsInOut_Backups")
        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder)

        backup_filename = f"{first_serial}_{last_serial}_{date_str}.xlsx"
        backup_filepath = os.path.join(backup_folder, backup_filename)
        # Limpia las celdas del DataFrame para eliminar caracteres ilegales
        df = df.applymap(sanitize_string)
        df.to_excel(backup_filepath, index=False)

        if automatic or (str(num_records).lower() == "todos"):
            cursor.execute("DELETE FROM DB_Cell10")
        else:
            ids = df["id"].tolist()
            query = "DELETE FROM DB_Cell10 WHERE SerialNumbIN IN ({seq})".format(seq=','.join(['?'] * len(ids)))
            cursor.execute(query, ids)

        conn.commit()
        record_count = len(df)
        conn.close()
        return backup_filename, f"Mantenimiento realizado correctamente. Se respaldaron {record_count} registros.", record_count

    def insert_backup_log(backup_file, record_count, message):
        """Inserta un registro en la tabla BackupLogs con los detalles del respaldo."""
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BackupLogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_file TEXT,
                record_count INTEGER,
                message TEXT,
                timestamp TEXT
            )
        """)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO BackupLogs (backup_file, record_count, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (backup_file, record_count, message, timestamp))
        conn.commit()
        conn.close()

    def periodic_backup():
        """Ejecuta el respaldo automáticamente cada 12 horas solo si está habilitado."""
        while True:
            if auto_backup_enabled and ENABLE_DBBCK:
                backup_file, msg, count = backup_database(automatic=True)
                if backup_file:
                    insert_backup_log(backup_file, count, msg)
                    print(f"Backup realizado: {backup_file} a las {datetime.now()}")
                else:
                    print(f"No se realizó backup: {msg}")
            time.sleep(12 * 60 * 60)  # Esperar 12 horas

    # Ruta para respaldo manual (se adapta para usar la función backup_database)
    @app.route('/maintenance_db', methods=['POST'])
    def maintenance_db():
        data = request.get_json() or {}
        automatic = data.get("automatic", False)
        num_records = data.get("num_records", None)
        try:
            backup_file, msg, count = backup_database(automatic, num_records)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        if backup_file:
            insert_backup_log(backup_file, count, msg)
            response = {"message": msg, "backup_file": backup_file}
        else:
            response = {"message": msg}
        return jsonify(response)

    # Ruta para consultar los logs de respaldo (puedes incluirla en la página del respaldo manual)
    @app.route('/backup_logs')
    def backup_logs():
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM BackupLogs ORDER BY id DESC")
        logs = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        conn.close()
        return render_template('backup_logs.html', logs=logs, columns=columns)

    @app.route('/settings', methods=['GET', 'POST'])
    def settings():
        global auto_backup_enabled
        if request.method == 'POST':
            auto_backup_enabled = not auto_backup_enabled
        return render_template('settings.html', auto_backup=auto_backup_enabled)

    #Funciones para contadores de piezas en celda 10.
    @app.route('/contadores_produccion')
    def contadores_produccion():
        return render_template('contadores_produccion_C10.html')

    @app.route('/get_oee_arrays')
    def get_oee_arrays():
        try:
            data = read_oee_arrays()
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/rejects_menu/<cell>')
    def rejects_menu_by_cell(cell):
        cell_key = cell.strip()
        return render_template("rejects_menu.html", cell=cell_key)


    @app.route('/rejects_list')
    def rejects_list():
        page = int(request.args.get("page", 1))
        per_page = 50
        offset = (page - 1) * per_page
        cell = request.args.get("cell")

        conn = sqlite3.connect("RejectsFaults.db")
        cursor = conn.cursor()

        # -----------------------------
        #  Construcción dinámica del query
        # -----------------------------
        base_query = """
            SELECT * FROM RejectsFaults
        """
        count_query = "SELECT COUNT(*) FROM RejectsFaults"
        params = []

        # Si se seleccionó una celda específica, filtramos usando RejectIndexMap
        if cell:
            filter_clause = """
                WHERE reject_index_uid IN (
                    SELECT unique_id FROM RejectIndexMap
                    WHERE cell = ?
                )
            """
            base_query += filter_clause
            count_query += filter_clause
            params.append(cell)

        # -----------------------------
        #  Total de páginas
        # -----------------------------
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]
        total_pages = max(1, (total_records + per_page - 1) // per_page)

        # -----------------------------
        #  Traer datos paginados
        # -----------------------------
        base_query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        cursor.execute(base_query, params)
        rows = cursor.fetchall()

        columns = [description[0] for description in cursor.description]
        conn.close()
        rows = [dict(zip(columns, r)) for r in rows]

        # -----------------------------
        #  Renderizado de la plantilla
        # -----------------------------
        return render_template(
            "rejects_list.html",
            rows=rows,
            page=page,
            total_pages=total_pages,
            cell=cell
        )

    @app.route('/rejects_by_date')
    def rejects_by_date():
        cell = request.args.get("cell")
        start_date = request.args.get("start")
        end_date = request.args.get("end")
        day = request.args.get("day")
        page = int(request.args.get("page", 1))
        per_page = 50
        offset = (page - 1) * per_page

        conn = sqlite3.connect("RejectsFaults.db")
        cursor = conn.cursor()

        # ==============================
        # 🔍 Construcción dinámica del query
        # ==============================
        base_query = "SELECT * FROM RejectsFaults"
        count_query = "SELECT COUNT(*) FROM RejectsFaults"
        filters = []
        params = []

        # Filtros de fecha (día o rango)
        if day:
            filters.append("DATE(timestamp) = ?")
            params.append(day)
        elif start_date and end_date:
            filters.append("DATE(timestamp) BETWEEN ? AND ?")
            params.extend([start_date, end_date])

        # Filtro por celda
        if cell:
            filters.append("""
                reject_index_uid IN (
                    SELECT unique_id FROM RejectIndexMap
                    WHERE cell = ?
                )
            """)
            params.append(cell)

        # Si existen filtros, se agregan al query
        if filters:
            where_clause = " WHERE " + " AND ".join(filters)
            base_query += where_clause
            count_query += where_clause

        # ==============================
        # 📊 Cálculo total de páginas
        # ==============================
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]
        total_pages = max(1, (total_records + per_page - 1) // per_page)

        # ==============================
        # 📋 Consulta paginada de resultados
        # ==============================
        base_query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        cursor.execute(base_query, params)
        fetched = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, r)) for r in fetched]
        conn.close()

        # ==============================
        # 🖥️ Renderizado
        # ==============================
        return render_template(
            "rejects_by_date.html",
            rows=rows,
            day=day,
            start=start_date,
            end=end_date,
            cell=cell,
            page=page,
            total_pages=total_pages
        )

    @app.route('/current_rejects')
    def current_rejects():
        cell = request.args.get("cell")
        try:
            data = get_current_rejects()

            if cell:
                data = [d for d in data if d["cell"] == cell]

            return render_template("current_rejects.html", data=data, cell=cell)
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/rejects_index_map')
    def rejects_index_map():
        cell = request.args.get("cell")

        conn = sqlite3.connect("RejectsFaults.db")
        cursor = conn.cursor()

        query = "SELECT * FROM RejectIndexMap"
        params = []

        if cell:
            query += " WHERE cell = ?"
            params.append(cell)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()

        rows = [dict(zip(columns, r)) for r in rows]

        return render_template("rejects_index_map.html", rows=rows, cell=cell)

    def get_db_connection():
        conn = sqlite3.connect('RejectsFaults.db')
        conn.row_factory = sqlite3.Row
        return conn
    
    # ✅ Mueve la función aquí, fuera del try/except
    from config import rejects_configuration

    @app.route("/rejects_by_pallet")
    def rejects_by_pallet():
        cell = request.args.get("cell", None)

        # start/end opcionales (datetime-local)
        start_arg = request.args.get("start")
        end_arg = request.args.get("end")

        start_dt, end_dt, shift_name, shift_window_label = _default_shift_window()
        user_start = _parse_dt_local(start_arg)
        user_end = _parse_dt_local(end_arg)
        if user_start:
            start_dt = user_start
        if user_end:
            end_dt = user_end

        start_sql = _dt_to_sql(start_dt)
        end_sql = _dt_to_sql(end_dt)

        conn = sqlite3.connect("RejectsFaults.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        routines = []
        if cell:
            for cfg in rejects_configuration.values():
                if cfg["cell"] == cell:
                    routines.extend(cfg["routines"])

        time_filter = "datetime(timestamp) BETWEEN datetime(?) AND datetime(?)"
        time_params = [start_sql, end_sql]

        if routines:
            placeholders = ",".join(["?"] * len(routines))
            query = f"""
                SELECT routine,
                    COALESCE(pallet_id, 'NoID') AS pallet_id,
                    COUNT(*) AS total
                FROM RejectsFaults
                WHERE routine IN ({placeholders})
                AND {time_filter}
                GROUP BY routine, pallet_id
                ORDER BY routine, pallet_id;
            """
            rows = cursor.execute(query, routines + time_params).fetchall()
        else:
            query = f"""
                SELECT routine,
                    COALESCE(pallet_id, 'NoID') AS pallet_id,
                    COUNT(*) AS total
                FROM RejectsFaults
                WHERE {time_filter}
                GROUP BY routine, pallet_id
                ORDER BY routine, pallet_id;
            """
            rows = cursor.execute(query, time_params).fetchall()

        conn.close()

        data_by_routine = {}
        for row in rows:
            routine = row["routine"] or "Desconocida"
            pallet = row["pallet_id"]
            total = int(row["total"] or 0)
            data_by_routine.setdefault(routine, {})[pallet] = total

        return render_template(
            "rejects_histogram_pallet.html",
            cell=cell,
            data=data_by_routine,
            start=_dt_to_input(start_dt),
            end=_dt_to_input(end_dt),
            shift_name=shift_name,
            shift_window_label=shift_window_label,
        )

    @app.route("/rejects_by_failure_mode")
    def rejects_by_failure_mode():
        cell = request.args.get("cell", None)

        start_arg = request.args.get("start")
        end_arg = request.args.get("end")

        start_dt, end_dt, shift_name, shift_window_label = _default_shift_window()
        user_start = _parse_dt_local(start_arg)
        user_end = _parse_dt_local(end_arg)
        if user_start:
            start_dt = user_start
        if user_end:
            end_dt = user_end

        start_sql = _dt_to_sql(start_dt)
        end_sql = _dt_to_sql(end_dt)

        conn = sqlite3.connect("RejectsFaults.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        routines = []
        if cell:
            for cfg in rejects_configuration.values():
                if str(cfg.get("cell")) == str(cell):
                    routines.extend(cfg.get("routines", []))

        time_filter = "datetime(timestamp) BETWEEN datetime(?) AND datetime(?)"
        time_params = [start_sql, end_sql]

        if routines:
            placeholders = ",".join(["?"] * len(routines))
            query = f"""
                SELECT
                    routine,
                    COALESCE(reject_name, 'Desconocido') AS reject_name,
                    COUNT(reject_index_uid) AS total
                FROM RejectsFaults
                WHERE routine IN ({placeholders})
                AND {time_filter}
                GROUP BY routine, reject_name
                ORDER BY routine, reject_name;
            """
            rows = cursor.execute(query, routines + time_params).fetchall()
        else:
            query = f"""
                SELECT
                    routine,
                    COALESCE(reject_name, 'Desconocido') AS reject_name,
                    COUNT(reject_index_uid) AS total
                FROM RejectsFaults
                WHERE {time_filter}
                GROUP BY routine, reject_name
                ORDER BY routine, reject_name;
            """
            rows = cursor.execute(query, time_params).fetchall()

        conn.close()

        data_by_routine = {}
        for r in rows:
            routine = r["routine"] or "Sin routine"
            name = r["reject_name"] or "Desconocido"
            total = int(r["total"] or 0)
            data_by_routine.setdefault(routine, {})[name] = total

        return render_template(
            "rejects_histogram.html",
            cell=cell,
            data=data_by_routine,
            start=_dt_to_input(start_dt),
            end=_dt_to_input(end_dt),
            shift_name=shift_name,
            shift_window_label=shift_window_label,
        )

    def _parse_dt_local(s: str):
        """Recibe 'YYYY-MM-DDTHH:MM' (datetime-local) o 'YYYY-MM-DD HH:MM'."""
        if not s:
            return None
        s = s.strip()
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(s, fmt)
                return hermosillo_tz.localize(dt)
            except ValueError:
                continue
        return None

    def _dt_to_sql(dt: datetime) -> str:
        """Formato compatible con SQLite datetime() cuando timestamp es TEXT."""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _dt_to_input(dt: datetime) -> str:
        """Formato para <input type=datetime-local>."""
        return dt.strftime("%Y-%m-%dT%H:%M")

    def _default_shift_window(now=None):
        """
        Turnos:
        Día   : 06:40 -> 18:40
        Noche : 18:40 -> 06:40 (cruza medianoche)

        Retorna:
        (start_dt, end_dt, shift_name, shift_window_label)
        """
        now = now or datetime.now(hermosillo_tz)
        today = now.date()

        base_today = hermosillo_tz.localize(datetime.combine(today, datetime.min.time()))
        t0640 = base_today.replace(hour=6, minute=40, second=0, microsecond=0)
        t1840 = base_today.replace(hour=18, minute=40, second=0, microsecond=0)

        if now >= t1840:
            # Noche (hoy 18:40 -> ahora)
            start = t1840
            shift_name = "Noche"
            shift_window_label = f"{t1840.strftime('%Y-%m-%d %H:%M')} → {(t0640 + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')}"
        elif now >= t0640:
            # Día (hoy 06:40 -> ahora)
            start = t0640
            shift_name = "Día"
            shift_window_label = f"{t0640.strftime('%Y-%m-%d %H:%M')} → {t1840.strftime('%Y-%m-%d %H:%M')}"
        else:
            # Noche (ayer 18:40 -> ahora)
            start = t1840 - timedelta(days=1)
            shift_name = "Noche"
            shift_window_label = f"{start.strftime('%Y-%m-%d %H:%M')} → {t0640.strftime('%Y-%m-%d %H:%M')}"

        return start, now, shift_name, shift_window_label

    # ----------------------------
    # Inicialización de hilos en el __main__
    # ----------------------------
    if __name__ == '__main__':
        try:
            logging.info("Iniciando aplicación Flask...")
            create_database()
            init_rejects_db()
            create_reject_index_map_table()
            start_plc_threads(plc_configuration, rejects_configuration)
            logging.info("Hilos PLC iniciados correctamente")
            threading.Thread(target=periodic_backup, daemon=True).start()
            print("🚀 Servidor iniciado en http://127.0.0.1:5000/")
            socketio.run(app, host='127.0.0.1', port=5000, debug=True, use_reloader=False)
        except Exception as e:
            logging.exception("💥 Error al iniciar la aplicación Flask")


######################################################################
#  Seccion para cachar error4es de arrance de la app borrar cuando no sea necesaria
######################################################################
except Exception as e:
    write_startup_error(e)
    raise
