import sqlite3
import time
import random
from datetime import datetime

DB_PATH = 'WeldParameters.db'


def create_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            distancia REAL,
            fuerza REAL,
            ampers REAL,
            volts REAL,
            watts REAL,
            estacion TEXT,
            sch TEXT,
            plc_ip TEXT,
            pallet_id TEXT,
            electrodecount INTEGER,
            welding_result TEXT
        )
    """)
    conn.commit()
    conn.close()


def simulate_data():
    stations = ["St1", "St2", "St3", "St4"]
    schedules = ["Sch1", "Sch2"]
    plc_ip = "127.0.0.1"

    print("Simulador corriendo...")

    while True:
        pallet_id = str(random.randint(1000, 9999))

        for station in stations:
            for sch in schedules:

                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                distancia = round(random.uniform(10, 15), 2)
                fuerza = round(random.uniform(200, 250), 2)
                ampers = round(random.uniform(5, 8), 2)
                volts = round(random.uniform(1, 3), 2)
                watts = round(random.uniform(10, 20), 2)
                electrodecount = random.randint(1, 1000)

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO Parameters
                    (timestamp, distancia, fuerza, ampers, volts, watts,
                     estacion, sch, plc_ip, pallet_id, electrodecount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp, distancia, fuerza, ampers, volts, watts,
                    station, sch, plc_ip, pallet_id, electrodecount
                ))

                conn.commit()
                conn.close()

        time.sleep(5)


if __name__ == "__main__":
    create_database()
    simulate_data()