CREATE TABLE IF NOT EXISTS stations (
    station_code   VARCHAR(50) PRIMARY KEY,
    line_id        VARCHAR(50)  NOT NULL,
    node_label     VARCHAR(50)  NOT NULL,
    display_name   VARCHAR(100) NOT NULL,
    station_order  INTEGER      NOT NULL,
    weld_start     INTEGER      NOT NULL,
    weld_end       INTEGER      NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weld_events (
    event_id          VARCHAR(64) PRIMARY KEY,
    line_id           VARCHAR(50)   NOT NULL,
    station_code      VARCHAR(50)   NOT NULL REFERENCES stations(station_code),
    pallet_id         VARCHAR(50)   NOT NULL,
    weld_id           INTEGER       NOT NULL,
    source_type       VARCHAR(30)   NOT NULL,
    source_timestamp  TIMESTAMPTZ   NOT NULL,
    received_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    voltaje           NUMERIC(6, 2) NOT NULL,
    corriente         NUMERIC(8, 2),
    presion           NUMERIC(6, 2) NOT NULL,
    tiempo_ms         NUMERIC(8, 2),
    status            VARCHAR(10)   NOT NULL,
    is_anomaly        BOOLEAN       NOT NULL,
    anomaly_score     NUMERIC(6, 4),
    confidence        NUMERIC(6, 4),
    detection_source  VARCHAR(50)   NOT NULL,
    detection_reason  TEXT,
    raw_payload       JSONB         NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id      VARCHAR(64) PRIMARY KEY,
    event_id      VARCHAR(64) UNIQUE NOT NULL REFERENCES weld_events(event_id) ON DELETE CASCADE,
    line_id       VARCHAR(50)  NOT NULL,
    station_code  VARCHAR(50)  NOT NULL REFERENCES stations(station_code),
    pallet_id     VARCHAR(50)  NOT NULL,
    weld_id       INTEGER      NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    title         VARCHAR(200) NOT NULL,
    message       TEXT         NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at   TIMESTAMPTZ
);

INSERT INTO stations (station_code, line_id, node_label, display_name, station_order, weld_start, weld_end)
VALUES
    ('station_1', 'linea1', 'NODE 01', 'Estacion 1', 1, 1, 2),
    ('station_2', 'linea1', 'NODE 02', 'Estacion 2', 2, 3, 4),
    ('station_3', 'linea1', 'NODE 03', 'Estacion 3', 3, 5, 6),
    ('station_4', 'linea1', 'NODE 04', 'Estacion 4', 4, 7, 8)
ON CONFLICT (station_code) DO NOTHING;
