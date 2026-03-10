import psycopg2
import paho.mqtt.client as mqtt
import json
import time
import os

DB_CONFIG = {
    "host": os.environ.get("POSTGRES_HOST", "db"),
    "database": os.environ.get("POSTGRES_DB", "soldadura_db"),
    "user": os.environ.get("POSTGRES_USER", "admin"),
    "password": os.environ.get("POSTGRES_PASSWORD", "industrial_pass")
}

def guardar_en_db(data, estado):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        query = """
            INSERT INTO registros_soldadura (pallet_id, weld_id, voltaje, presion, estado)
            VALUES (%s, %s, %s, %s, %s)
        """
        cur.execute(query, (
            data['pallet_id'], 
            data['weld_id'], 
            data['params']['voltaje'], 
            data['params']['presion'], 
            estado
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        # Si la DB falla, imprimimos el error pero NO detenemos el programa
        print(f"❌ Error al guardar en DB: {e}")

MQTT_BROKER = "broker" 
MQTT_TOPIC = "fabrica/linea1/soldadura"

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        params = data["params"]
        
        es_mala = params["voltaje"] > 12.5 or params["presion"] < 2.8
        status = "MALO" if es_mala else "BUENO"
        
        print(f" [ANALIZADOR] Pallet: {data['pallet_id']} | Soldadura: {data['weld_id']} | Estado: {status}")
        
        # Guardamos en la DB
        guardar_en_db(data, status)

    except Exception as e:
        print(f"Error procesando mensaje: {e}")

# --- ARRANQUE DEL SISTEMA ---

# Esperamos 10 segundos para asegurar que Postgres y Mosquitto estén listos
print("🧠 Cerebro durmiendo 10 segundos para esperar a la base de datos...")
time.sleep(10)

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message

print("🚀 Conectando al broker...")
client.connect(MQTT_BROKER, 1883, 60)
client.subscribe(MQTT_TOPIC)

client.loop_forever()