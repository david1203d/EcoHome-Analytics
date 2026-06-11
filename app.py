"""
EcoHome Analytics - Flask REST API + Web Dashboard
Autor: Dobrinoiu David | Grupa 341C5
"""

from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from sqlalchemy import func, text

from config import Config
from models import db, Room, Device, EnergyReading, Alert


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # UPDATE DRIVER PENTRU PYTHON 3.13+ (Psycopg 3) ---
    db_url = app.config.get("SQLALCHEMY_DATABASE_URI")
    if db_url and db_url.startswith("postgresql://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:5000", "http://localhost:5000"]}})

    # ------------------------------------------------------------------
    # Dashboard principal
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    # ------------------------------------------------------------------
    # CAMERE
    # ------------------------------------------------------------------
    @app.route("/api/rooms")
    def get_rooms():
        rooms = Room.query.order_by(Room.floor, Room.name).all()
        return jsonify([r.to_dict() for r in rooms])

    # ------------------------------------------------------------------
    # DISPOZITIVE
    # ------------------------------------------------------------------
    @app.route("/api/devices")
    def get_devices():
        room_id  = request.args.get("room_id",  type=int)
        dev_type = request.args.get("type")
        active   = request.args.get("active", "true").lower() == "true"

        q = Device.query
        if room_id:  q = q.filter_by(room_id=room_id)
        if dev_type: q = q.filter_by(type=dev_type)
        if active:   q = q.filter_by(is_active=True)

        return jsonify([d.to_dict() for d in q.order_by(Device.name).all()])

    @app.route("/api/devices/<int:device_id>")
    def get_device(device_id):
        device = Device.query.get_or_404(device_id)
        data   = device.to_dict()

        last = (EnergyReading.query
                .filter_by(device_id=device_id)
                .order_by(EnergyReading.recorded_at.desc())
                .first())
        if last:
            data["last_reading"] = last.to_dict()

        first_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
        monthly = (db.session.query(func.sum(EnergyReading.energy_kwh))
                   .filter(EnergyReading.device_id == device_id,
                           EnergyReading.recorded_at >= first_of_month)
                   .scalar() or 0.0)
        data["monthly_kwh"]      = round(monthly, 3)
        data["monthly_cost_ron"] = round(monthly * Config.TARIF_RON_PER_KWH, 2)
        return jsonify(data)

    # ------------------------------------------------------------------
    # CITIRI
    # ------------------------------------------------------------------
    @app.route("/api/devices/<int:device_id>/readings")
    def get_device_readings(device_id):
        Device.query.get_or_404(device_id)
        hours = request.args.get("hours", 24, type=int)
        limit = request.args.get("limit", 200, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        readings = (EnergyReading.query
                    .filter(EnergyReading.device_id == device_id,
                            EnergyReading.recorded_at >= since)
                    .order_by(EnergyReading.recorded_at.desc())
                    .limit(limit).all())
        return jsonify([r.to_dict() for r in readings])

    @app.route("/api/readings")
    def get_readings():
        limit = request.args.get("limit", 100, type=int)
        hours = request.args.get("hours", 1,   type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        readings = (EnergyReading.query
                    .filter(EnergyReading.recorded_at >= since)
                    .order_by(EnergyReading.recorded_at.desc())
                    .limit(limit).all())
        return jsonify([r.to_dict() for r in readings])

    @app.route("/api/readings", methods=["POST"])
    def add_reading():
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON invalid"}), 400
            
        for f in ["device_id", "power_watts"]:
            if f not in data:
                return jsonify({"error": f"Camp lipsa: {f}"}), 400

        # [M4 FIX] Validare tipuri de date și valori negative (Anti-Crash 500)
        try:
            device_id = int(data["device_id"])
            power_watts = float(data["power_watts"])
            if power_watts < 0:
                return jsonify({"error": "Puterea consumata nu poate fi negativa"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "device_id si power_watts trebuie sa fie numere valide"}), 400

        device = Device.query.get(device_id)
        if not device:
            return jsonify({"error": "Dispozitiv negasit"}), 404

        interval_h = data.get("interval_minutes", 10) / 60.0
        reading = EnergyReading(
            device_id   = device_id,
            power_watts = power_watts,
            energy_kwh  = power_watts / 1000.0 * interval_h,
            voltage_v   = data.get("voltage_v", 230.0),
            recorded_at = datetime.utcnow(),
        )
        db.session.add(reading)

        if power_watts > device.power_rating_watts * 1.5:
            limit_watts = round(device.power_rating_watts * 1.5, 1)
            
            db.session.add(Alert(
                device_id  = device.id,
                alert_type = "high_consumption",
                severity   = "warning",
                message    = (f"{device.name} consuma {power_watts}W, "
                            f"depasind limita de siguranta de {limit_watts}W "
                            f"(1.5x puterea nominala de {device.power_rating_watts}W)"),
                threshold  = limit_watts,
                actual_val = power_watts,
            ))

        # [M3 FIX] Idempotență garantată prin blocarea erorilor de index unic
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"status": "ignored", "message": "Citire duplicata ignorata cu succes (Idempotent)"}), 200

        return jsonify(reading.to_dict()), 201

    # ------------------------------------------------------------------
    # SUMAR
    # ------------------------------------------------------------------
    @app.route("/api/summary")
    def get_summary():
        now = datetime.utcnow()

        def kwh_since(dt):
            v = (db.session.query(func.sum(EnergyReading.energy_kwh))
                 .filter(EnergyReading.recorded_at >= dt).scalar() or 0.0)
            return round(v, 3)

        kwh_24h = kwh_since(now - timedelta(hours=24))
        kwh_7d  = kwh_since(now - timedelta(days=7))
        kwh_mo  = kwh_since(now.replace(day=1, hour=0, minute=0, second=0))

        t = Config.TARIF_RON_PER_KWH
        return jsonify({
            "last_24h":   {"kwh": kwh_24h, "cost_ron": round(kwh_24h * t, 2)},
            "last_7d":    {"kwh": kwh_7d,  "cost_ron": round(kwh_7d  * t, 2)},
            "this_month": {"kwh": kwh_mo,  "cost_ron": round(kwh_mo  * t, 2)},
            "total_devices": Device.query.filter_by(is_active=True).count(),
            "active_alerts": Alert.query.filter_by(resolved=False).count(),
            "generated_at":  now.isoformat(),
        })

    @app.route("/api/summary/by-room")
    def summary_by_room():
        hours = request.args.get("hours", 24, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        rows = (db.session.query(
                    Room.name.label("room"),
                    func.sum(EnergyReading.energy_kwh).label("kwh"),
                    func.count(func.distinct(EnergyReading.device_id)).label("devices"))
                .join(Device, Device.room_id == Room.id)
                .join(EnergyReading, EnergyReading.device_id == Device.id)
                .filter(EnergyReading.recorded_at >= since)
                .group_by(Room.name)
                .order_by(func.sum(EnergyReading.energy_kwh).desc())
                .all())

        return jsonify([{
            "room":     r.room,
            "kwh":      round(r.kwh, 3),
            "cost_ron": round(r.kwh * Config.TARIF_RON_PER_KWH, 2),
            "devices":  r.devices,
        } for r in rows])

    @app.route("/api/summary/by-type")
    def summary_by_type():
        hours = request.args.get("hours", 24, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        rows = (db.session.query(
                    Device.type.label("type"),
                    func.sum(EnergyReading.energy_kwh).label("kwh"),
                    func.count(func.distinct(EnergyReading.device_id)).label("devices"))
                .join(EnergyReading, EnergyReading.device_id == Device.id)
                .filter(EnergyReading.recorded_at >= since)
                .group_by(Device.type)
                .order_by(func.sum(EnergyReading.energy_kwh).desc())
                .all())

        return jsonify([{
            "type":     r.type,
            "kwh":      round(r.kwh, 3),
            "cost_ron": round(r.kwh * Config.TARIF_RON_PER_KWH, 2),
            "devices":  r.devices,
        } for r in rows])

    # ------------------------------------------------------------------
    # TOP DISPOZITIVE (endpoint nou pentru dashboard)
    # ------------------------------------------------------------------
    @app.route("/api/summary/by-device")
    def summary_by_device():
        hours = request.args.get("hours", 24, type=int)
        limit = request.args.get("limit", 10, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        rows = db.session.execute(text("""
            SELECT
                d.name        AS device_name,
                d.type        AS device_type,
                r.name        AS room_name,
                SUM(er.energy_kwh)  AS kwh,
                SUM(er.cost_ron)    AS cost_ron,
                AVG(er.power_watts) AS avg_watts
            FROM energy_readings er
            JOIN devices d ON d.id = er.device_id
            JOIN rooms   r ON r.id = d.room_id
            WHERE er.recorded_at >= :since
            GROUP BY d.name, d.type, r.name
            ORDER BY kwh DESC
            LIMIT :lim
        """), {"since": since, "lim": limit}).fetchall()

        return jsonify([{
            "device_name": r.device_name,
            "device_type": r.device_type,
            "room_name":   r.room_name,
            "kwh":         round(float(r.kwh), 3),
            "cost_ron":    round(float(r.cost_ron), 2),
            "avg_watts":   round(float(r.avg_watts), 1),
        } for r in rows])

    # ------------------------------------------------------------------
    # CONSUM ORAR (pentru graficul time series)
    # ------------------------------------------------------------------
    @app.route("/api/consumption/hourly")
    def get_hourly_consumption():
        hours = request.args.get("hours", 24, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        rows = db.session.execute(text("""
            SELECT
                date_trunc('hour', recorded_at) AS hour,
                SUM(energy_kwh)  AS kwh,
                SUM(cost_ron)    AS cost
            FROM energy_readings
            WHERE recorded_at >= :since
            GROUP BY 1
            ORDER BY 1
        """), {"since": since}).fetchall()

        return jsonify([{
            "hour": row.hour.isoformat(),
            "kwh":  round(float(row.kwh), 3),
            "cost": round(float(row.cost), 2),
        } for row in rows])

    # ------------------------------------------------------------------
    # TREND 30 ZILE cu Window Function (PostgreSQL avansat)
    # ------------------------------------------------------------------
    @app.route("/api/trends")
    def get_trends():
        rows = db.session.execute(text("""
            WITH daily AS (
                SELECT
                    DATE(recorded_at)   AS day,
                    SUM(energy_kwh)     AS kwh,
                    SUM(cost_ron)       AS cost
                FROM energy_readings
                WHERE recorded_at >= NOW() - INTERVAL '30 days'
                GROUP BY 1
            )
            SELECT
                day,
                kwh,
                cost,
                ROUND(
                    AVG(kwh) OVER (
                        ORDER BY day
                        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                    )::numeric, 3
                ) AS moving_avg_7d
            FROM daily
            ORDER BY day
        """)).fetchall()

        return jsonify([{
            "day":           str(row.day),
            "kwh":           round(float(row.kwh), 3),
            "cost":          round(float(row.cost), 2),
            "moving_avg_7d": round(float(row.moving_avg_7d), 3),
        } for row in rows])

    # ------------------------------------------------------------------
    # ALERTE
    # ------------------------------------------------------------------
    @app.route("/api/alerts")
    def get_alerts():
        resolved = request.args.get("resolved", "false").lower() == "true"
        alerts   = (Alert.query
                    .filter_by(resolved=resolved)
                    .order_by(Alert.created_at.desc())
                    .limit(50).all())
        return jsonify([a.to_dict() for a in alerts])

    @app.route("/api/alerts/<int:alert_id>/resolve", methods=["POST"])
    def resolve_alert(alert_id):
        alert             = Alert.query.get_or_404(alert_id)
        alert.resolved    = True
        alert.resolved_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"ok": True, "alert_id": alert_id})

    # ------------------------------------------------------------------
    # ANOMALY DETECTION (Z-score calculat in PostgreSQL)
    # ------------------------------------------------------------------
    @app.route("/api/anomalies")
    def get_anomalies():
        rows = db.session.execute(text("""
            WITH stats AS (
                SELECT
                    device_id,
                    AVG(power_watts)    AS mean_w,
                    STDDEV(power_watts) AS std_w
                FROM energy_readings
                WHERE recorded_at >= NOW() - INTERVAL '30 days'
                GROUP BY device_id
                HAVING STDDEV(power_watts) > 0
            ),
            recent AS (
                SELECT
                    er.device_id,
                    d.name              AS device_name,
                    d.type              AS device_type,
                    r.name              AS room_name,
                    AVG(er.power_watts) AS avg_recent_w,
                    s.mean_w,
                    s.std_w,
                    ROUND(
                        ((AVG(er.power_watts) - s.mean_w) / s.std_w)::numeric
                    , 2) AS z_score
                FROM energy_readings er
                JOIN devices d ON d.id = er.device_id
                JOIN rooms   r ON r.id = d.room_id
                JOIN stats   s ON s.device_id = er.device_id
                WHERE er.recorded_at >= NOW() - INTERVAL '3 hours'
                GROUP BY er.device_id, d.name, d.type, r.name, s.mean_w, s.std_w
            )
            SELECT *,
                CASE
                    WHEN z_score >  2 THEN 'over'
                    WHEN z_score < -2 THEN 'under'
                    ELSE 'normal'
                END AS status
            FROM recent
            WHERE ABS(z_score) > 1.5
            ORDER BY ABS(z_score) DESC
            LIMIT 10
        """)).fetchall()

        return jsonify([{
            "device_name":   r.device_name,
            "device_type":   r.device_type,
            "room_name":     r.room_name,
            "avg_recent_w":  round(float(r.avg_recent_w), 1),
            "mean_w":        round(float(r.mean_w), 1),
            "z_score":       float(r.z_score),
            "status":        r.status,
        } for r in rows])

    # ------------------------------------------------------------------
    # ROOM EFFICIENCY SCORE (kWh/m² cu RANK window function)
    # ------------------------------------------------------------------
    @app.route("/api/efficiency")
    def get_efficiency():
        hours = request.args.get("hours", 24, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        rows = db.session.execute(text("""
            SELECT
                r.name                                      AS room,
                r.area_sqm,
                SUM(er.energy_kwh)                          AS kwh,
                SUM(er.cost_ron)                            AS cost_ron,
                ROUND(
                    (SUM(er.energy_kwh) / NULLIF(r.area_sqm, 0))::numeric
                , 4)                                        AS kwh_per_sqm,
                RANK() OVER (
                    ORDER BY SUM(er.energy_kwh) / NULLIF(r.area_sqm, 0) ASC
                )                                           AS efficiency_rank
            FROM energy_readings er
            JOIN devices d ON d.id = er.device_id
            JOIN rooms   r ON r.id = d.room_id
            WHERE er.recorded_at >= :since
            GROUP BY r.name, r.area_sqm
            ORDER BY kwh_per_sqm ASC
        """), {"since": since}).fetchall()

        total_rooms = len(rows)
        grades = {1: "A", 2: "B", 3: "C", 4: "D", 5: "F"}

        return jsonify([{
            "room":             r.room,
            "area_sqm":         r.area_sqm,
            "kwh":              round(float(r.kwh), 3),
            "cost_ron":         round(float(r.cost_ron), 2),
            "kwh_per_sqm":      round(float(r.kwh_per_sqm), 4),
            "efficiency_rank":  int(r.efficiency_rank),
            "grade":            grades.get(int(r.efficiency_rank), "F"),
        } for r in rows])

    # ------------------------------------------------------------------
    # CARBON FOOTPRINT (factorul Romania: 0.287 kg CO2/kWh)
    # ------------------------------------------------------------------
    CO2_FACTOR_KG  = 0.287   # kg CO2 per kWh - Romania 2023 (ENTSO-E)
    CO2_CAR_KM     = 0.21    # kg CO2 per km - medie europeana

    @app.route("/api/carbon")
    def get_carbon():
        now = datetime.utcnow()

        def kwh_since(dt):
            v = (db.session.query(func.sum(EnergyReading.energy_kwh))
                .filter(EnergyReading.recorded_at >= dt).scalar() or 0.0)
            return round(float(v), 3)

        kwh_24h = kwh_since(now - timedelta(hours=24))
        kwh_7d  = kwh_since(now - timedelta(days=7))
        kwh_30d = kwh_since(now - timedelta(days=30))

        def co2(kwh):
            kg  = round(kwh * CO2_FACTOR_KG, 2)
            km  = round(kg  / CO2_CAR_KM,    1)
            trees = round(kg / 21.77, 2)  # un copac absoarbe ~21.77 kg CO2/an
            return {"kg_co2": kg, "equiv_km_car": km, "trees_needed": trees}

        return jsonify({
            "last_24h":   {"kwh": kwh_24h,  **co2(kwh_24h)},
            "last_7d":    {"kwh": kwh_7d,   **co2(kwh_7d)},
            "last_30d":   {"kwh": kwh_30d,  **co2(kwh_30d)},
            "factor_used": CO2_FACTOR_KG,
            "source":      "ENTSO-E 2023 - Romania grid emission factor",
        })

    # ------------------------------------------------------------------
    # SMART RECOMMENDATIONS (generate server-side din date reale)
    # ------------------------------------------------------------------
    @app.route("/api/recommendations")
    def get_recommendations():
        now   = datetime.utcnow()
        since = now - timedelta(hours=24)
        recs  = []

        # --- date de baza ---
        total_kwh = float(db.session.query(func.sum(EnergyReading.energy_kwh))
                        .filter(EnergyReading.recorded_at >= since)
                        .scalar() or 0)

        if total_kwh == 0:
            return jsonify([])

        # 1. Tip dispozitiv dominant
        top_type = db.session.execute(text("""
            SELECT d.type, SUM(er.energy_kwh) AS kwh
            FROM energy_readings er
            JOIN devices d ON d.id = er.device_id
            WHERE er.recorded_at >= :since
            GROUP BY d.type ORDER BY kwh DESC LIMIT 1
        """), {"since": since}).fetchone()

        if top_type:
            pct = round(float(top_type.kwh) / total_kwh * 100)
            tips = {
                "hvac":          ("Optimizeaza temperatura cu 1-2 grade", 12.0),
                "appliance":     ("Muta aparatele mari la ore de noapte (22:00-06:00)", 8.0),
                "entertainment": ("Activeaza modul sleep pe televizor si consola", 3.0),
                "lighting":      ("Inlocuieste becurile ramase cu LED", 4.0),
            }
            tip, saving = tips.get(top_type.type, ("Verifica dispozitivele acestui tip", 2.0))
            recs.append({
                "priority":    "high",
                "category":    top_type.type,
                "title":       f"{top_type.type.upper()} reprezinta {pct}% din consum",
                "description": f"Dispozitivele de tip {top_type.type} au consumat "
                            f"{round(float(top_type.kwh), 2)} kWh in ultimele 24h.",
                "action":      tip,
                "saving_ron":  saving,
            })

        # 2. Camera cea mai ineficienta per mp
        worst_room = db.session.execute(text("""
            SELECT r.name, r.area_sqm,
                SUM(er.energy_kwh) AS kwh,
                SUM(er.energy_kwh) / NULLIF(r.area_sqm, 0) AS kwh_per_sqm
            FROM energy_readings er
            JOIN devices d ON d.id = er.device_id
            JOIN rooms   r ON r.id = d.room_id
            WHERE er.recorded_at >= :since AND r.area_sqm IS NOT NULL
            GROUP BY r.name, r.area_sqm
            ORDER BY kwh_per_sqm DESC LIMIT 1
        """), {"since": since}).fetchone()

        if worst_room:
            recs.append({
                "priority":    "medium",
                "category":    "efficiency",
                "title":       f"Camera '{worst_room.name}' are cel mai mare consum per mp",
                "description": f"{round(float(worst_room.kwh_per_sqm), 3)} kWh/m² — "
                            f"verifica daca toate dispozitivele sunt necesare.",
                "action":      "Opreste echipamentele in standby si verifica izolatia termica.",
                "saving_ron":  5.0,
            })

        # 3. Comparatie cu saptamana trecuta
        kwh_last_week = float(db.session.query(func.sum(EnergyReading.energy_kwh))
                            .filter(EnergyReading.recorded_at >= now - timedelta(days=14),
                                    EnergyReading.recorded_at <  now - timedelta(days=7))
                            .scalar() or 0)
        kwh_this_week = float(db.session.query(func.sum(EnergyReading.energy_kwh))
                            .filter(EnergyReading.recorded_at >= now - timedelta(days=7))
                            .scalar() or 0)

        if kwh_last_week > 0:
            delta_pct = round((kwh_this_week - kwh_last_week) / kwh_last_week * 100, 1)
            if delta_pct > 10:
                recs.append({
                    "priority":    "high",
                    "category":    "trend",
                    "title":       f"Consumul a crescut cu {delta_pct}% fata de saptamana trecuta",
                    "description": f"Aceasta saptamana: {round(kwh_this_week, 1)} kWh vs "
                                f"saptamana trecuta: {round(kwh_last_week, 1)} kWh.",
                    "action":      "Identifica ce dispozitive au fost folosite mai mult si ajusteaza.",
                    "saving_ron":  round(abs(kwh_this_week - kwh_last_week) * Config.TARIF_RON_PER_KWH * 0.3, 2),
                })
            elif delta_pct < -10:
                recs.append({
                    "priority":    "low",
                    "category":    "trend",
                    "title":       f"Consum redus cu {abs(delta_pct)}% fata de saptamana trecuta",
                    "description": "Consumul a scazut — continua bunele practici.",
                    "action":      "Mentine obiceiurile actuale de utilizare.",
                    "saving_ron":  0,
                })

        # 4. Carbon footprint ridicat
        co2_kg = round(total_kwh * 0.287, 2)
        if co2_kg > 5:
            recs.append({
                "priority":    "low",
                "category":    "carbon",
                "title":       f"Amprenta de carbon azi: {co2_kg} kg CO2",
                "description": f"Echivalent cu {round(co2_kg / 0.21, 0):.0f} km condusi cu masina.",
                "action":      "Reducand consumul cu 20% elimini emisiile a "
                            f"{round(co2_kg * 0.2 / 21.77, 2)} copaci pe an.",
                "saving_ron":  round(total_kwh * 0.2 * Config.TARIF_RON_PER_KWH, 2),
            })

        recs.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]])
        return jsonify(recs)

    
    # ------------------------------------------------------------------
    # COMPARATIE SAPTAMANALA (CTE + FULL OUTER JOIN in PostgreSQL)
    # ------------------------------------------------------------------
    @app.route("/api/comparison")
    def get_comparison():
        rows = db.session.execute(text("""
            WITH this_week AS (
                SELECT
                    DATE(recorded_at)   AS day,
                    SUM(energy_kwh)     AS kwh,
                    SUM(cost_ron)       AS cost
                FROM energy_readings
                WHERE recorded_at >= NOW() - INTERVAL '7 days'
                GROUP BY 1
            ),
            last_week AS (
                SELECT
                    DATE(recorded_at)   AS day,
                    SUM(energy_kwh)     AS kwh,
                    SUM(cost_ron)       AS cost
                FROM energy_readings
                WHERE recorded_at >= NOW() - INTERVAL '14 days'
                AND recorded_at <  NOW() - INTERVAL '7 days'
                GROUP BY 1
            )
            SELECT
                COALESCE(t.day, l.day + 7) AS day,
                COALESCE(t.kwh,  0)        AS this_kwh,
                COALESCE(t.cost, 0)        AS this_cost,
                COALESCE(l.kwh,  0)        AS last_kwh,
                COALESCE(l.cost, 0)        AS last_cost,
                ROUND(
                    CASE WHEN COALESCE(l.kwh, 0) > 0
                    THEN ((COALESCE(t.kwh, 0) - l.kwh) / l.kwh * 100)::numeric
                    ELSE 0 END
                , 1) AS delta_pct
            FROM this_week t
            FULL OUTER JOIN last_week l ON t.day = l.day + 7
            ORDER BY 1
        """)).fetchall()

        return jsonify([{
            "day":       str(r.day),
            "this_kwh":  round(float(r.this_kwh), 3),
            "this_cost": round(float(r.this_cost), 2),
            "last_kwh":  round(float(r.last_kwh), 3),
            "last_cost": round(float(r.last_cost), 2),
            "delta_pct": float(r.delta_pct),
        } for r in rows])

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resursa negasita"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Eroare server intern"}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    # db.create_all() intentionally removed — sql/schema.sql este single source of truth pentru DDL
    app.run(debug=True, port=5000)
    