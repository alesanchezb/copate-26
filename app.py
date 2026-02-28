from flask import Flask, render_template, request, jsonify
import sqlite3

app = Flask(__name__)
DB_PATH = "WeldParameters.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pallet_id,
               COUNT(*) as total,
               MAX(welding_result) as welding_result
        FROM Parameters
        GROUP BY pallet_id
        ORDER BY MAX(timestamp) DESC
        LIMIT 20
    """)

    pallets = cursor.fetchall()
    conn.close()

    return render_template("index.html", pallets=pallets)


@app.route("/set_result", methods=["POST"])
def set_result():
    data = request.get_json()
    pallet_id = data["pallet_id"]
    result = data["result"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Parameters
        SET welding_result = ?
        WHERE pallet_id = ?
    """, (result, pallet_id))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)