from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB_PATH = "InspeccionManual.db"

# Mapeo de botones: key = id del botón, value = (estacion, schedule)
BUTTON_MAP = {
    "btn1": ("St145", "Sch2"),
    "btn2": ("St145", "Sch1"),
    "btn3": ("St155", "Sch2"),
    "btn4": ("St155", "Sch1"),
    "btn5": ("St140", "Sch1"),
    "btn6": ("St140", "Sch2"),
    "btn7": ("St150", "Sch2"),
    "btn8": ("St150", "Sch1"),
}

DEFECTOS = [
    "Splatter",
    "Gap",
    "Terminal Perforada",
    "Busbar Perforada",
    "MetalFlake",
    "Busbar desalineada",
    "Terminal/Kostal Desalineada",
    "Faltante de busbar",
    "Faltante de Terminal/Kostal",
    "Weld projection sin derretir",
]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Inspecciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            estacion TEXT NOT NULL,
            schedule TEXT NOT NULL,
            pallet_id TEXT NOT NULL,
            defecto TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    """Página inicial: pedir PalletId al operador."""
    return render_template("index.html")


@app.route("/inspeccion")
def inspeccion():
    """Página de inspección: grilla de 8 botones."""
    pallet_id = request.args.get("pallet_id", "").strip()
    if not pallet_id:
        return render_template("index.html", error="Debes ingresar un Pallet ID.")
    return render_template("inspeccion.html", pallet_id=pallet_id, button_map=BUTTON_MAP, defectos=DEFECTOS)


@app.route("/registrar_defecto", methods=["POST"])
def registrar_defecto():
    """Registra un defecto en la base de datos."""
    data = request.get_json()
    boton = data.get("boton")
    pallet_id = data.get("pallet_id", "").strip()
    defecto = data.get("defecto", "").strip()

    if boton not in BUTTON_MAP:
        return jsonify({"status": "error", "message": "Botón inválido"}), 400
    if not pallet_id:
        return jsonify({"status": "error", "message": "Pallet ID requerido"}), 400
    if defecto not in DEFECTOS:
        return jsonify({"status": "error", "message": "Defecto inválido"}), 400

    estacion, schedule = BUTTON_MAP[boton]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Inspecciones (timestamp, estacion, schedule, pallet_id, defecto)
        VALUES (?, ?, ?, ?, ?)
    """, (timestamp, estacion, schedule, pallet_id, defecto))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok", "message": f"Defecto '{defecto}' registrado para {estacion}/{schedule}"})


@app.route("/historial")
def historial():
    """Muestra el historial de inspecciones recientes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, estacion, schedule, pallet_id, defecto
        FROM Inspecciones
        ORDER BY id DESC
        LIMIT 50
    """)
    registros = cursor.fetchall()
    conn.close()
    return render_template("historial.html", registros=registros)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)