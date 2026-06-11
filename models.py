"""
Modele SQLAlchemy - Smart Home Energy Monitor
Reflecta structura din schema.sql
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


class Room(db.Model):
    __tablename__ = "rooms"

    id         = db.Column(db.Integer,    primary_key=True)
    name       = db.Column(db.String(100), nullable=False, unique=True)
    floor      = db.Column(db.Integer,    nullable=False, default=1)
    area_sqm   = db.Column(db.Float)
    created_at = db.Column(db.DateTime,   nullable=False, default=datetime.utcnow)

    devices = db.relationship("Device", back_populates="room", lazy="dynamic")

    def to_dict(self):
        return {
            "id":        self.id,
            "name":      self.name,
            "floor":     self.floor,
            "area_sqm":  self.area_sqm,
        }


class Device(db.Model):
    __tablename__ = "devices"

    id                 = db.Column(db.Integer,    primary_key=True)
    room_id            = db.Column(db.Integer,    db.ForeignKey("rooms.id"), nullable=False)
    name               = db.Column(db.String(100), nullable=False)
    type               = db.Column(db.String(50),  nullable=False)
    brand              = db.Column(db.String(100))
    model              = db.Column(db.String(100))
    power_rating_watts = db.Column(db.Float,       nullable=False)
    is_active          = db.Column(db.Boolean,     nullable=False, default=True)
    installed_at       = db.Column(db.Date)
    created_at         = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow)

    room     = db.relationship("Room",          back_populates="devices")
    readings = db.relationship("EnergyReading", back_populates="device", lazy="dynamic")

    def to_dict(self):
        return {
            "id":                  self.id,
            "room_id":             self.room_id,
            "room_name":           self.room.name if self.room else None,
            "name":                self.name,
            "type":                self.type,
            "brand":               self.brand,
            "power_rating_watts":  self.power_rating_watts,
            "is_active":           self.is_active,
        }


class EnergyReading(db.Model):
    __tablename__ = "energy_readings"

    id          = db.Column(db.BigInteger, primary_key=True)
    device_id   = db.Column(db.Integer,   db.ForeignKey("devices.id"), nullable=False)
    recorded_at = db.Column(db.DateTime,  nullable=False, default=datetime.utcnow)
    power_watts = db.Column(db.Float,     nullable=False)
    energy_kwh  = db.Column(db.Float,     nullable=False)
    voltage_v   = db.Column(db.Float,     default=230.0)

    device = db.relationship("Device", back_populates="readings")

    def to_dict(self):
        return {
            "id":          self.id,
            "device_id":   self.device_id,
            "device_name": self.device.name if self.device else None,
            "recorded_at": self.recorded_at.isoformat(),
            "power_watts": round(self.power_watts, 2),
            "energy_kwh":  round(self.energy_kwh, 4),
            "cost_ron":    round(self.energy_kwh * Config.TARIF_RON_PER_KWH, 4),
        }


class Alert(db.Model):
    __tablename__ = "alerts"

    id          = db.Column(db.Integer,    primary_key=True)
    device_id   = db.Column(db.Integer,   db.ForeignKey("devices.id"))
    alert_type  = db.Column(db.String(50), nullable=False)
    severity    = db.Column(db.String(20), nullable=False, default="warning")
    message     = db.Column(db.Text,       nullable=False)
    threshold   = db.Column(db.Float)
    actual_val  = db.Column(db.Float)
    created_at  = db.Column(db.DateTime,   nullable=False, default=datetime.utcnow)
    resolved    = db.Column(db.Boolean,    nullable=False, default=False)
    resolved_at = db.Column(db.DateTime)

    device = db.relationship("Device")

    def to_dict(self):
        return {
            "id":          self.id,
            "device_id":   self.device_id,
            "alert_type":  self.alert_type,
            "severity":    self.severity,
            "message":     self.message,
            "created_at":  self.created_at.isoformat(),
            "resolved":    self.resolved,
        }