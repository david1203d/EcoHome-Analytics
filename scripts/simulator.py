"""
Simulator date consum energie - Smart Home Energy Monitor
Autor: Dobrinoiu David | Grupa 341C5

Genereaza date realiste tinand cont de:
  - Tiparul zilnic (ora din zi)
  - Tiparul saptamanal (zi lucratoare vs weekend)
  - Zgomot aleator realist per tip dispozitiv
  - Intervale de inactivitate (dispozitiv oprit)

Utilizare:
  python scripts/simulator.py --days 30 --interval 5
  python scripts/simulator.py --days 7  --interval 15 --device-id 1
"""

import argparse
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

# Permite import din directorul parinte
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("simulator")


# ======================================================================
#  PROFILURI DE UTILIZARE - factori multiplicatori (0.0 - 1.5)
#  Fiecare dictionar contine factor pe ora (0-23) si pe tip de zi
# ======================================================================

HOURLY_PROFILE = {
    "hvac": [
        0.1, 0.1, 0.1, 0.1, 0.1, 0.2,   # 00-05
        0.4, 0.6, 0.7, 0.5, 0.4, 0.4,   # 06-11
        0.5, 0.4, 0.4, 0.5, 0.7, 0.9,   # 12-17
        1.0, 1.0, 0.9, 0.7, 0.4, 0.2,   # 18-23
    ],
    "lighting": [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.1,   # 00-05
        0.3, 0.8, 0.5, 0.3, 0.2, 0.2,   # 06-11
        0.2, 0.2, 0.2, 0.3, 0.5, 0.8,   # 12-17
        1.0, 1.0, 0.9, 0.7, 0.4, 0.1,   # 18-23
    ],
    "entertainment": [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0,   # 00-05
        0.1, 0.2, 0.1, 0.1, 0.1, 0.1,   # 06-11
        0.3, 0.2, 0.2, 0.3, 0.5, 0.8,   # 12-17
        1.0, 1.0, 0.9, 0.7, 0.3, 0.0,   # 18-23
    ],
    "appliance": [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.1,   # 00-05
        0.4, 0.8, 0.6, 0.3, 0.3, 0.5,   # 06-11
        0.7, 0.4, 0.3, 0.3, 0.6, 0.9,   # 12-17
        0.8, 0.6, 0.4, 0.2, 0.1, 0.0,   # 18-23
    ],
    "security": [
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0,   # securitate mereu activa
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    ],
    "other": [
        0.3, 0.3, 0.3, 0.3, 0.3, 0.4,
        0.5, 0.6, 0.6, 0.6, 0.5, 0.5,
        0.5, 0.5, 0.5, 0.5, 0.6, 0.7,
        0.7, 0.6, 0.5, 0.4, 0.3, 0.3,
    ],
}

WEEKEND_BOOST = {
    "entertainment": 1.3,
    "lighting":      0.9,
    "appliance":     1.1,
    "hvac":          1.2,
    "security":      1.0,
    "other":         1.0,
}


def get_connection():
    """Conectare la PostgreSQL folosind config."""
    return psycopg2.connect(
        host     = Config.DB_HOST,
        port     = Config.DB_PORT,
        dbname   = Config.DB_NAME,
        user     = Config.DB_USER,
        password = Config.DB_PASSWORD,
    )


def simulate_power(device: dict, ts: datetime) -> float:
    """
    Calculeaza puterea instantanee (W) pentru un dispozitiv
    la momentul ts, tinand cont de profil orar + zgomot.
    """
    dev_type = device["type"]
    nominal  = device["power_rating_watts"]
    hour     = ts.hour
    weekday  = ts.weekday()  # 0=Luni, 5=Sambata, 6=Duminica

    profile  = HOURLY_PROFILE.get(dev_type, HOURLY_PROFILE["other"])
    factor   = profile[hour]

    # Amplificare weekend
    if weekday >= 5:
        factor *= WEEKEND_BOOST.get(dev_type, 1.0)

    # Frigiderul cicleaza (ON/OFF la fiecare ~20 min)
    if dev_type == "appliance" and "frigider" in device["name"].lower():
        minute = ts.minute
        factor = 1.0 if minute % 20 < 12 else 0.05

    # Boilerul - are acumulare termica, se incalzeste scurt
    if "boiler" in device["name"].lower():
        factor = 1.0 if hour in (6, 7, 20, 21) else 0.05

    # Zgomot gaussian realist (±10%)
    noise   = random.gauss(1.0, 0.05)
    power   = nominal * factor * noise

    # Probabilitate ca dispozitivul sa fie complet oprit
    off_prob = max(0.0, 0.3 - factor * 0.4)
    if random.random() < off_prob:
        power = 0.0

    return max(0.0, power)


def generate_readings(devices: list, start: datetime, end: datetime,
                      interval_min: int) -> list:
    """
    Genereaza toate citirile intre start si end la intervalul dat.
    Returneaza lista de tuple pentru insert batch.
    """
    readings = []
    interval = timedelta(minutes=interval_min)
    interval_h = interval_min / 60.0

    current = start
    count   = 0

    while current <= end:
        for device in devices:
            power  = simulate_power(device, current)
            energy = power / 1000.0 * interval_h

            readings.append((
                device["id"],
                current,
                round(power,  2),
                round(energy, 6),
                230.0,
            ))
            count += 1

        current += interval

        if count % 5000 == 0:
            log.info(f"  Generat {count:,} citiri pana la {current.strftime('%Y-%m-%d %H:%M')}")

    return readings


def insert_batch(conn, readings: list) -> int:
    """Insert bulk in PostgreSQL."""
    sql = """
        INSERT INTO energy_readings (device_id, recorded_at, power_watts, energy_kwh, voltage_v)
        VALUES %s
        ON CONFLICT DO NOTHING
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, readings, page_size=1000)
    conn.commit()
    return len(readings)


def main():
    parser = argparse.ArgumentParser(description="Simulator consum energie smart home")
    parser.add_argument("--days",      type=int, default=30,
                        help="Numar zile simulate (implicit 30)")
    parser.add_argument("--interval",  type=int, default=5,
                        help="Interval intre citiri in minute (implicit 5)")
    parser.add_argument("--device-id", type=int, default=None,
                        help="Simuleaza doar dispozitivul cu acest id")
    parser.add_argument("--live",      action="store_true",
                        help="Mod live: insereaza o citire la fiecare interval")
    args = parser.parse_args()

    log.info("Conectare la PostgreSQL...")
    try:
        conn = get_connection()
        log.info("Conexiune stabilita.")
    except Exception as e:
        log.error(f"Nu m-am putut conecta: {e}")
        sys.exit(1)

    with conn.cursor() as cur:
        if args.device_id:
            cur.execute(
                "SELECT id, name, type, power_rating_watts FROM devices "
                "WHERE id = %s AND is_active = TRUE",
                (args.device_id,)
            )
        else:
            cur.execute(
                "SELECT id, name, type, power_rating_watts FROM devices "
                "WHERE is_active = TRUE ORDER BY id"
            )
        rows = cur.fetchall()

    devices = [
        {"id": r[0], "name": r[1], "type": r[2], "power_rating_watts": r[3]}
        for r in rows
    ]
    log.info(f"Dispozitive gasite: {len(devices)}")

    if not devices:
        log.warning("Niciun dispozitiv activ gasit. Ruleaza schema.sql mai intai.")
        conn.close()
        sys.exit(1)

    if args.live:
        # Mod live: bucla infinita, o citire la fiecare interval
        log.info(f"Mod LIVE: inserare la fiecare {args.interval} minute. Ctrl+C pentru stop.")
        try:
            while True:
                now = datetime.utcnow()
                readings = []
                for device in devices:
                    power  = simulate_power(device, now)
                    energy = power / 1000.0 * (args.interval / 60.0)
                    readings.append((device["id"], now,
                                     round(power, 2), round(energy, 6), 230.0))
                n = insert_batch(conn, readings)
                log.info(f"Inserat {n} citiri la {now.strftime('%H:%M:%S')}")
                time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            log.info("Simulator oprit.")
    else:
        # Mod historic: genereaza date pentru ultimele N zile
        end   = datetime.utcnow()
        start = end - timedelta(days=args.days)
        log.info(f"Generare date istorice: {start.date()} -> {end.date()}, "
                 f"interval {args.interval} min, {len(devices)} dispozitive")

        readings = generate_readings(devices, start, end, args.interval)
        log.info(f"Total citiri generate: {len(readings):,}. Inserare in DB...")
        n = insert_batch(conn, readings)
        log.info(f"Inserat {n:,} citiri cu succes.")

    conn.close()


if __name__ == "__main__":
    main()