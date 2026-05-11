"""
Smart Home Energy Monitor - Flask REST API
Autor: Dobrinoiu David | Grupa 341C5

Endpoints:
  GET  /                            - Status API
  GET  /api/rooms                   - Lista camere
  GET  /api/devices                 - Lista dispozitive
  GET  /api/devices/<id>            - Detalii dispozitiv
  GET  /api/devices/<id>/readings   - Citiri dispozitiv (cu filtre temporale)
  GET  /api/readings                - Ultimele N citiri globale
  POST /api/readings                - Adauga o citire noua
  GET  /api/summary                 - Sumar consum (24h / saptamana / luna)
  GET  /api/summary/by-room         - Consum agregat pe camera
  GET  /api/summary/by-type         - Consum agregat pe tip dispozitiv
  GET  /api/alerts                  - Lista alerte active
  POST /api/alerts/<id>/resolve     - Rezolva o alerta
"""

from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import func, text

from config import Config
from models import db, Room, Device, EnergyReading, Alert


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    CORS(app)

    # ------------------------------------------------------------------
    # Health check / index
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return jsonify({
            "app":     "Smart Home Energy Monitor",
            "version": "1.0.0",
            "author":  "Dobrinoiu David",
            "status":  "running",
            "docs":    "Foloseste /api/* pentru date",
        })

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
        room_id = request.args.get("room_id", type=int)
        dev_type = request.args.get("type")
        active = request.args.get("active", "true").lower() == "true"

        q = Device.query
        if room_id:
            q = q.filter_by(room_id=room_id)
        if dev_type:
            q = q.filter_by(type=dev_type)
        if active:
            q = q.filter_by(is_active=True)

        devices = q.order_by(Device.name).all()
        return jsonify([d.to_dict() for d in devices])

    @app.route("/api/devices/<int:device_id>")
    def get_device(device_id):
        device = Device.query.get_or_404(device_id)
        data = device.to_dict()

        # Ultima citire
        last = (EnergyReading.query
                .filter_by(device_id=device_id)
                .order_by(EnergyReading.recorded_at.desc())
                .first())
        if last:
            data["last_reading"] = last.to_dict()

        # Consum total luna curenta
        first_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
        monthly = (db.session.query(func.sum(EnergyReading.energy_kwh))
                   .filter(EnergyReading.device_id == device_id,
                           EnergyReading.recorded_at >= first_of_month)
                   .scalar() or 0.0)
        data["monthly_kwh"]     = round(monthly, 3)
        data["monthly_cost_ron"] = round(monthly * 1.29, 2)

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
                    .limit(limit)
                    .all())
        return jsonify([r.to_dict() for r in readings])

    @app.route("/api/readings")
    def get_readings():
        limit = request.args.get("limit", 100, type=int)
        hours = request.args.get("hours", 1, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        readings = (EnergyReading.query
                    .filter(EnergyReading.recorded_at >= since)
                    .order_by(EnergyReading.recorded_at.desc())
                    .limit(limit)
                    .all())
        return jsonify([r.to_dict() for r in readings])

    @app.route("/api/readings", methods=["POST"])
    def add_reading():
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON invalid"}), 400

        required = ["device_id", "power_watts"]
        for f in required:
            if f not in data:
                return jsonify({"error": f"Camp lipsa: {f}"}), 400

        device = Device.query.get(data["device_id"])
        if not device:
            return jsonify({"error": "Dispozitiv negasit"}), 404

        interval_h = data.get("interval_minutes", 5) / 60.0
        reading = EnergyReading(
            device_id   = data["device_id"],
            power_watts = data["power_watts"],
            energy_kwh  = data["power_watts"] / 1000.0 * interval_h,
            voltage_v   = data.get("voltage_v", 230.0),
            recorded_at = datetime.utcnow(),
        )
        db.session.add(reading)

        # Verifica prag consum mare (150% din puterea nominala)
        if data["power_watts"] > device.power_rating_watts * 1.5:
            alert = Alert(
                device_id  = device.id,
                alert_type = "high_consumption",
                severity   = "warning",
                message    = (f"{device.name} consuma {data['power_watts']}W, "
                              f"cu mult peste puterea nominala de {device.power_rating_watts}W"),
                threshold  = device.power_rating_watts * 1.5,
                actual_val = data["power_watts"],
            )
            db.session.add(alert)

        db.session.commit()
        return jsonify(reading.to_dict()), 201

    # ------------------------------------------------------------------
    # SUMAR / STATISTICI
    # ------------------------------------------------------------------
    @app.route("/api/summary")
    def get_summary():
        now = datetime.utcnow()

        def kwh_since(dt):
            val = (db.session.query(func.sum(EnergyReading.energy_kwh))
                   .filter(EnergyReading.recorded_at >= dt)
                   .scalar() or 0.0)
            return round(val, 3)

        return jsonify({
            "last_24h": {
                "kwh":      kwh_since(now - timedelta(hours=24)),
                "cost_ron": round(kwh_since(now - timedelta(hours=24)) * 1.29, 2),
            },
            "last_7d": {
                "kwh":      kwh_since(now - timedelta(days=7)),
                "cost_ron": round(kwh_since(now - timedelta(days=7)) * 1.29, 2),
            },
            "this_month": {
                "kwh":      kwh_since(now.replace(day=1, hour=0, minute=0, second=0)),
                "cost_ron": round(
                    kwh_since(now.replace(day=1, hour=0, minute=0, second=0)) * 1.29, 2
                ),
            },
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
                    func.count(func.distinct(EnergyReading.device_id)).label("devices")
                )
                .join(Device, Device.room_id == Room.id)
                .join(EnergyReading, EnergyReading.device_id == Device.id)
                .filter(EnergyReading.recorded_at >= since)
                .group_by(Room.name)
                .order_by(func.sum(EnergyReading.energy_kwh).desc())
                .all())

        return jsonify([{
            "room":      r.room,
            "kwh":       round(r.kwh, 3),
            "cost_ron":  round(r.kwh * 1.29, 2),
            "devices":   r.devices,
        } for r in rows])

    @app.route("/api/summary/by-type")
    def summary_by_type():
        hours = request.args.get("hours", 24, type=int)
        since = datetime.utcnow() - timedelta(hours=hours)

        rows = (db.session.query(
                    Device.type.label("type"),
                    func.sum(EnergyReading.energy_kwh).label("kwh"),
                    func.count(func.distinct(EnergyReading.device_id)).label("devices")
                )
                .join(EnergyReading, EnergyReading.device_id == Device.id)
                .filter(EnergyReading.recorded_at >= since)
                .group_by(Device.type)
                .order_by(func.sum(EnergyReading.energy_kwh).desc())
                .all())

        return jsonify([{
            "type":     r.type,
            "kwh":      round(r.kwh, 3),
            "cost_ron": round(r.kwh * 1.29, 2),
            "devices":  r.devices,
        } for r in rows])

    # ------------------------------------------------------------------
    # ALERTE
    # ------------------------------------------------------------------
    @app.route("/api/alerts")
    def get_alerts():
        resolved = request.args.get("resolved", "false").lower() == "true"
        alerts = (Alert.query
                  .filter_by(resolved=resolved)
                  .order_by(Alert.created_at.desc())
                  .limit(50)
                  .all())
        return jsonify([a.to_dict() for a in alerts])

    @app.route("/api/alerts/<int:alert_id>/resolve", methods=["POST"])
    def resolve_alert(alert_id):
        alert = Alert.query.get_or_404(alert_id)
        alert.resolved    = True
        alert.resolved_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"ok": True, "alert_id": alert_id})

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
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)