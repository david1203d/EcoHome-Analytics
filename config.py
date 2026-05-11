"""
Configuratie aplicatie Flask - Smart Home Energy Monitor
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Baza de date
    DB_HOST     = os.getenv("DB_HOST",     "localhost")
    DB_PORT     = os.getenv("DB_PORT",     "5432")
    DB_NAME     = os.getenv("DB_NAME",     "smart_home")
    DB_USER     = os.getenv("DB_USER",     "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-smart-home-2024")

    # Grafana (pentru context documentatie)
    GRAFANA_URL  = os.getenv("GRAFANA_URL",  "http://localhost:3000")

    # Setari simulator
    TARIF_RON_PER_KWH = 1.29   # tarif mediu Romania