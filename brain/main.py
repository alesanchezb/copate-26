import paho.mqtt.client as mqtt
import json
import time
import threading

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import API_HOST, API_PORT, APP_NAME, MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, STATIC_DIR
from repository import (
    ensure_schema,
    fetch_alert_detail,
    fetch_analytics_data,
    fetch_dashboard_data,
    fetch_history_data,
    normalize_payload,
    persist_event,
    seed_stations,
    wait_for_database,
)


app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_mqtt_thread: threading.Thread | None = None


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith(
        ("/history", "/analytics", "/alerts", "/static")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class TelemetrySubscriber:
    def __init__(self) -> None:
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"[MQTT] Conectado al broker con codigo {reason_code}")
        client.subscribe(MQTT_TOPIC)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            event = normalize_payload(payload)
            if persist_event(event):
                print(
                    f"[ALERTS] {event['pallet_id']} | {event['station_code']} | "
                    f"soldadura {event['weld_id']} | {event['status']}"
                )
        except Exception as exc:
            print(f"[ALERTS] Error procesando mensaje MQTT: {exc}")

    def run_forever(self):
        while True:
            try:
                print(f"[MQTT] Conectando a {MQTT_BROKER}:{MQTT_PORT}...")
                self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
                self.client.loop_forever()
            except Exception as exc:
                print(f"[MQTT] Conexion interrumpida: {exc}")
                time.sleep(5)


def start_subscriber() -> None:
    global _mqtt_thread
    if _mqtt_thread is not None:
        return

    subscriber = TelemetrySubscriber()
    _mqtt_thread = threading.Thread(target=subscriber.run_forever, daemon=True)
    _mqtt_thread.start()


@app.on_event("startup")
def on_startup() -> None:
    wait_for_database()
    ensure_schema()
    seed_stations()
    start_subscriber()


@app.get("/api/health")
def api_health():
    return {"status": "ok"}


@app.get("/api/dashboard")
def api_dashboard():
    return fetch_dashboard_data()


@app.get("/api/history")
def api_history(
    station: str | None = Query(default=None),
    status: str | None = Query(default=None),
    pallet: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=50),
):
    return fetch_history_data(
        station_code=station,
        status=status,
        pallet_id=pallet,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@app.get("/api/analytics")
def api_analytics():
    return fetch_analytics_data()


@app.get("/api/alerts/{alert_id}")
def api_alert_detail(alert_id: str):
    detail = fetch_alert_detail(alert_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    return detail


@app.get("/", include_in_schema=False)
def ui_dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/history", include_in_schema=False)
def ui_history():
    return FileResponse(STATIC_DIR / "history.html")


@app.get("/analytics", include_in_schema=False)
def ui_analytics():
    return FileResponse(STATIC_DIR / "analytics.html")


@app.get("/alerts/{alert_id}", include_in_schema=False)
def ui_alert_detail(alert_id: str):
    return FileResponse(STATIC_DIR / "detail.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=False)
