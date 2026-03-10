import paho.mqtt.client as mqtt
import json
import time
import random

# Configuración básica
BROKER = "localhost"
PORT = 1883
TOPIC = "fabrica/linea1/soldadura"

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER, PORT, 60)

def generar_datos_soldadura(pallet_id, weld_index):
    """Genera datos simulando una distribución normal (Gauss)"""
    # Simulamos que lo ideal es: 12V, 450A, 3.0 bar, 0.8s
    return {
        "pallet_id": f"PALLET_{pallet_id}",
        "weld_id": weld_index,
        "timestamp": time.time(),
        "params": {
            "voltaje": round(random.gauss(12, 0.2), 2),
            "corriente": round(random.gauss(450, 10), 1),
            "presion": round(random.gauss(3.0, 0.05), 2),
            "tiempo_ms": round(random.gauss(800, 20), 0)
        }
    }

print("🚀 Simulador iniciado. Enviando datos al broker...")

try:
    pallet_count = 1000
    while True:
        # Un pallet tiene 8 soldaduras
        for i in range(1, 9):
            data = generar_datos_soldadura(pallet_count, i)
            
            # Convertimos a JSON y enviamos
            mensaje = json.dumps(data)
            client.publish(TOPIC, mensaje)
            
            print(f"📡 Enviada soldadura {i}/8 del {data['pallet_id']}")
            time.sleep(1) # Simula el tiempo entre soldaduras individuales
            
        print(f"✅ Pallet {pallet_count} terminado. Esperando siguiente...")
        pallet_count += 1
        time.sleep(5) # Tiempo que tarda en llegar el siguiente pallet
except KeyboardInterrupt:
    print("\n🛑 Simulador detenido.")
    client.disconnect()