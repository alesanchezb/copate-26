from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB_PATH = "InspeccionManual.db"

# Mapeo de botones agrupado por Pieza (columna visual en la imagen)
# Pieza 1 (izquierda):      btn1=arriba, btn2=abajo
# Pieza 2 (centro-izq):     btn3=arriba, btn4=abajo
# Pieza 3 (centro-der):     btn5=arriba, btn6=abajo
# Pieza 4 (derecha):        btn7=arriba, btn8=abajo
BUTTON_MAP = {
    "btn1": ("St145", "Sch2"),   # Pieza 1 - arriba
    "btn2": ("St140", "Sch1"),   # Pieza 1 - abajo
    "btn3": ("St145", "Sch1"),   # Pieza 2 - arriba
    "btn4": ("St140", "Sch2"),   # Pieza 2 - abajo
    "btn5": ("St155", "Sch2"),   # Pieza 3 - arriba
    "btn6": ("St150", "Sch2"),   # Pieza 3 - abajo
    "btn7": ("St155", "Sch1"),   # Pieza 4 - arriba
    "btn8": ("St150", "Sch1"),   # Pieza 4 - abajo
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


@app.route("/finalizar_inspeccion", methods=["POST"])
def finalizar_inspeccion():
    """Guarda todos los defectos de la inspección de una vez al finalizar."""
    data = request.get_json()
    pallet_id = data.get("pallet_id", "").strip()
    defectos_lista = data.get("defectos", [])  # [{boton, defecto}, ...]

    if not pallet_id:
        return jsonify({"status": "error", "message": "Pallet ID requerido"}), 400
    if not isinstance(defectos_lista, list):
        return jsonify({"status": "error", "message": "Formato inválido"}), 400

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()

    for item in defectos_lista:
        boton = item.get("boton")
        defecto = item.get("defecto", "").strip()

        if boton not in BUTTON_MAP:
            conn.close()
            return jsonify({"status": "error", "message": f"Botón inválido: {boton}"}), 400
        if defecto not in DEFECTOS:
            conn.close()
            return jsonify({"status": "error", "message": f"Defecto inválido: {defecto}"}), 400

        estacion, schedule = BUTTON_MAP[boton]
        cursor.execute("""
            INSERT INTO Inspecciones (timestamp, estacion, schedule, pallet_id, defecto)
            VALUES (?, ?, ?, ?, ?)
        """, (timestamp, estacion, schedule, pallet_id, defecto))

    conn.commit()
    conn.close()

    total = len(defectos_lista)
    return jsonify({"status": "ok", "message": f"{total} defecto(s) guardado(s) correctamente"})


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