-- ============================================================
--  Sistem de evidenta si analiza a consumului de energie
--  Schema baza de date: smart_home
--  Autor: Dobrinoiu David | Grupa 341C5
-- ============================================================

-- Sterge tabelele in ordine corecta (FK)
DROP TABLE IF EXISTS alerts CASCADE;
DROP TABLE IF EXISTS energy_readings CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
DROP TABLE IF EXISTS rooms CASCADE;

-- ============================================================
--  1. CAMERE
-- ============================================================
CREATE TABLE rooms (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    floor       INTEGER      NOT NULL DEFAULT 1,
    area_sqm    FLOAT,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  rooms IS 'Camerele din locuinta inteligenta';
COMMENT ON COLUMN rooms.area_sqm IS 'Suprafata camerei in metri patrati';

-- ============================================================
--  2. DISPOZITIVE
-- ============================================================
CREATE TABLE devices (
    id                  SERIAL PRIMARY KEY,
    room_id             INTEGER     NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    name                VARCHAR(100) NOT NULL,
    type                VARCHAR(50)  NOT NULL
        CHECK (type IN ('lighting','hvac','appliance','entertainment','security','other')),
    brand               VARCHAR(100),
    model               VARCHAR(100),
    power_rating_watts  FLOAT       NOT NULL CHECK (power_rating_watts > 0),
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    installed_at        DATE,
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  devices IS 'Dispozitivele electrice monitorizate';
COMMENT ON COLUMN devices.power_rating_watts IS 'Puterea nominala in wati';
COMMENT ON COLUMN devices.type IS 'Categoria dispozitivului';

-- ============================================================
--  3. CITIRI ENERGIE (tabel principal time-series)
-- ============================================================
CREATE TABLE energy_readings (
    id              BIGSERIAL   PRIMARY KEY,
    device_id       INTEGER     NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    recorded_at     TIMESTAMP   NOT NULL DEFAULT NOW(),
    power_watts     FLOAT       NOT NULL CHECK (power_watts >= 0),
    energy_kwh      FLOAT       NOT NULL CHECK (energy_kwh >= 0),
    cost_ron        FLOAT       GENERATED ALWAYS AS (energy_kwh * 1.29) STORED,
    -- 1.29 RON/kWh = tarif mediu Romania 2024
    voltage_v       FLOAT       DEFAULT 230.0,
    current_a       FLOAT       GENERATED ALWAYS AS (
                        CASE WHEN voltage_v > 0 THEN power_watts / voltage_v ELSE 0 END
                    ) STORED
);

COMMENT ON TABLE  energy_readings IS 'Citirile de consum energie per dispozitiv';
COMMENT ON COLUMN energy_readings.cost_ron IS 'Cost calculat automat (RON)';
COMMENT ON COLUMN energy_readings.current_a IS 'Curent calculat automat (A)';

-- Index pentru interogari temporale frecvente in Grafana
CREATE INDEX idx_readings_device_time ON energy_readings (device_id, recorded_at DESC);
CREATE INDEX idx_readings_time        ON energy_readings (recorded_at DESC);

-- ============================================================
--  4. ALERTE
-- ============================================================
CREATE TABLE alerts (
    id          SERIAL      PRIMARY KEY,
    device_id   INTEGER     REFERENCES devices(id) ON DELETE SET NULL,
    alert_type  VARCHAR(50) NOT NULL
        CHECK (alert_type IN ('high_consumption','anomaly','offline','threshold_exceeded')),
    severity    VARCHAR(20) NOT NULL DEFAULT 'warning'
        CHECK (severity IN ('info','warning','critical')),
    message     TEXT        NOT NULL,
    threshold   FLOAT,
    actual_val  FLOAT,
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
    resolved    BOOLEAN     NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMP
);

COMMENT ON TABLE alerts IS 'Alerte generate automat la consum anormal';

-- ============================================================
--  5. VIEW-URI UTILE (folosite de Grafana direct)
-- ============================================================

-- Consum total pe camera (ultimele 24h)
CREATE OR REPLACE VIEW vw_room_consumption_24h AS
SELECT
    r.name                              AS room_name,
    SUM(er.energy_kwh)                  AS total_kwh,
    SUM(er.cost_ron)                    AS total_cost_ron,
    COUNT(DISTINCT er.device_id)        AS active_devices,
    MAX(er.recorded_at)                 AS last_reading
FROM energy_readings er
JOIN devices d  ON d.id = er.device_id
JOIN rooms   r  ON r.id = d.room_id
WHERE er.recorded_at >= NOW() - INTERVAL '24 hours'
GROUP BY r.name;

-- Consum orar per dispozitiv (pentru grafice Grafana)
CREATE OR REPLACE VIEW vw_hourly_consumption AS
SELECT
    date_trunc('hour', er.recorded_at)  AS hour,
    d.name                              AS device_name,
    d.type                              AS device_type,
    r.name                              AS room_name,
    AVG(er.power_watts)                 AS avg_power_watts,
    SUM(er.energy_kwh)                  AS total_kwh,
    SUM(er.cost_ron)                    AS total_cost_ron
FROM energy_readings er
JOIN devices d ON d.id = er.device_id
JOIN rooms   r ON r.id = d.room_id
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC;

-- ============================================================
--  6. DATE INITIALE (seed)
-- ============================================================
INSERT INTO rooms (name, floor, area_sqm) VALUES
    ('Living',      1, 28.0),
    ('Dormitor',    1, 16.0),
    ('Bucatarie',   1, 12.0),
    ('Baie',        1,  6.0),
    ('Birou',       2, 14.0);

INSERT INTO devices (room_id, name, type, brand, power_rating_watts, installed_at) VALUES
    (1, 'Televizor Samsung',    'entertainment', 'Samsung', 120.0, '2022-01-10'),
    (1, 'Aer conditionat',      'hvac',          'Daikin',  1500.0, '2021-06-15'),
    (1, 'Lampa living',         'lighting',      'Philips',  20.0, '2023-03-01'),
    (2, 'Aer conditionat dorm', 'hvac',          'Daikin',  1200.0, '2021-06-15'),
    (2, 'Lampa dormitor',       'lighting',      'Ikea',     12.0, '2023-01-01'),
    (3, 'Frigider',             'appliance',     'Bosch',   150.0, '2020-09-20'),
    (3, 'Masina de spalat',     'appliance',     'LG',      2000.0, '2021-03-15'),
    (3, 'Cuptorul cu microunde','appliance',     'Tefal',    800.0, '2022-07-10'),
    (4, 'Boiler electric',      'appliance',     'Ariston', 2000.0, '2020-05-01'),
    (5, 'PC Desktop',           'appliance',     'Custom',   350.0, '2023-01-20'),
    (5, 'Monitor 27"',          'entertainment', 'LG',       45.0, '2023-01-20'),
    (5, 'Lampa birou',          'lighting',      'Philips',  10.0, '2023-01-20');

-- CREATE UNIQUE INDEX uq_readings_device_time ON energy_readings(device_id, recorded_at);
-- [M3 FIX] Asigura unicitatea pentru idempotenta totala
CREATE UNIQUE INDEX IF NOT EXISTS uq_readings_device_time ON energy_readings(device_id, recorded_at);