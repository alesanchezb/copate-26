-- Tabla principal de registros de soldadura
CREATE TABLE IF NOT EXISTS registros_soldadura (
    id          SERIAL PRIMARY KEY,
    pallet_id   VARCHAR(50)      NOT NULL,
    weld_id     INTEGER          NOT NULL,
    voltaje     NUMERIC(6, 2)    NOT NULL,
    presion     NUMERIC(6, 2)    NOT NULL,
    estado      VARCHAR(10)      NOT NULL,
    timestamp   TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);
