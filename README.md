# Sistem de Evidență și Analiză a Consumului de Energie într-o Locuință Inteligentă

**Lucrare de licență** | Autor: Dobrinoiu David | Grupa 341C5  
Facultatea de Automatică și Calculatoare — Universitatea Politehnica București  
Coordonator: Prof. dr. ...

---

## Descriere

Aplicația colectează (sau simulează) date despre consumul de energie al dispozitivelor
dintr-o locuință inteligentă. Datele sunt stocate într-o bază de date relațională PostgreSQL,
analizate prin interogări SQL optimizate și vizualizate în Grafana prin dashboard-uri interactive.

Accentul este pus pe:
- Modelarea corectă a datelor (ER diagram, constrângeri, view-uri)
- Performanța interogărilor (indecși pe coloane temporale)
- Generarea realistă de date prin simulare (profiluri orare + zgomot gaussian)
- API REST curat pentru integrarea cu Grafana

---

## Arhitectură

```
┌─────────────────────┐     INSERT      ┌──────────────────────┐
│  Simulator Python   │ ──────────────► │   PostgreSQL         │
│  (profiluri orare)  │                 │   smart_home DB      │
└─────────────────────┘                 └──────────┬───────────┘
                                                   │
┌─────────────────────┐   SQLAlchemy               │
│  Flask REST API     │ ◄──────────────────────────┘
│  /api/*             │
└──────────┬──────────┘
           │  JSON
┌──────────▼──────────┐   PostgreSQL   ┌──────────────────────┐
│  Grafana            │ ◄──────────────│   PostgreSQL         │
│  Dashboards         │   datasource   │   (aceeași instanță) │
└─────────────────────┘                └──────────────────────┘
```

---

## Tehnologii

| Componentă       | Tehnologie              | Versiune |
|------------------|-------------------------|----------|
| Backend API      | Python Flask            | 3.0.3    |
| ORM              | SQLAlchemy              | 2.0.30   |
| Baza de date     | PostgreSQL              | 16+      |
| Vizualizare      | Grafana                 | 11+      |
| Simulare date    | Python (psycopg2)       | 3.11+    |
| Driverul BD      | psycopg2-binary         | 2.9.9    |

---

## Structura proiectului

```
smart_home/
├── app.py              # Flask app principal — toate endpoint-urile REST
├── models.py           # Modele SQLAlchemy (Room, Device, EnergyReading, Alert)
├── config.py           # Configurație (DB, cheie secretă)
├── requirements.txt    # Dependențe Python
├── .env.example        # Template variabile de mediu
│
├── sql/
│   └── schema.sql      # Schema completă PostgreSQL (tabele, indecși, view-uri, seed)
│
└── scripts/
    └── simulator.py    # Script simulare date (mod istoric + mod live)
```

---

## Model de date (ER)

```
rooms ─────────────────── devices ──────────────── energy_readings
  id PK                     id PK                    id PK
  name                      room_id FK               device_id FK
  floor                     name                     recorded_at
  area_sqm                  type                     power_watts
  created_at                brand                    energy_kwh
                            power_rating_watts       cost_ron (generat)
                            is_active                voltage_v
                            installed_at             current_a (generat)
                            created_at
                                │
                                └──────────────── alerts
                                                   id PK
                                                   device_id FK
                                                   alert_type
                                                   severity
                                                   message
                                                   resolved
```

**Indecși de performanță:**
```sql
CREATE INDEX idx_readings_device_time ON energy_readings (device_id, recorded_at DESC);
CREATE INDEX idx_readings_time        ON energy_readings (recorded_at DESC);
```

---

## Instalare și rulare

### 1. Cerințe prealabile
- Python 3.11+
- PostgreSQL 16+
- Grafana 11+ (opțional, pentru vizualizare)

### 2. Clonare și setup Python

```bash
git clone https://github.com/<user>/smart-home-energy.git
cd smart-home-energy

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Editează .env cu datele tale PostgreSQL
```

### 3. Inițializare baza de date

```bash
# Creează baza de date (dacă nu există)
psql -U postgres -c "CREATE DATABASE smart_home;"

# Aplică schema + date inițiale
psql -U postgres -d smart_home -f sql/schema.sql
```

### 4. Generare date simulate (30 zile)

```bash
# Date istorice — ultimele 30 zile, citire la 5 minute
python scripts/simulator.py --days 30 --interval 5

# Sau mod live (o citire la 5 min, rulează continuu)
python scripts/simulator.py --live --interval 5
```

### 5. Pornire Flask API

```bash
python app.py
# API disponibil la http://localhost:5000
```

### 6. Configurare Grafana

1. Adaugă datasource: **PostgreSQL** → `localhost:5432 / smart_home`
2. Importă dashboard-urile din `/grafana-dashboards/` (JSON)
3. Interogare exemplu pentru consum orar:
```sql
SELECT
  date_trunc('hour', recorded_at) AS time,
  SUM(energy_kwh) AS "Consum (kWh)"
FROM energy_readings
JOIN devices ON devices.id = energy_readings.device_id
WHERE $__timeFilter(recorded_at)
GROUP BY 1
ORDER BY 1
```

---

## API Endpoints

| Metodă | Endpoint                          | Descriere                        |
|--------|-----------------------------------|----------------------------------|
| GET    | `/`                               | Status API                       |
| GET    | `/api/rooms`                      | Lista camere                     |
| GET    | `/api/devices`                    | Lista dispozitive (cu filtre)    |
| GET    | `/api/devices/<id>`               | Detalii + consum lunar           |
| GET    | `/api/devices/<id>/readings`      | Citiri dispozitiv (`?hours=24`)  |
| GET    | `/api/readings`                   | Ultimele citiri globale          |
| POST   | `/api/readings`                   | Adaugă citire nouă               |
| GET    | `/api/summary`                    | Sumar 24h / 7 zile / lună        |
| GET    | `/api/summary/by-room`            | Consum agregat pe cameră         |
| GET    | `/api/summary/by-type`            | Consum agregat pe tip            |
| GET    | `/api/alerts`                     | Alerte active                    |
| POST   | `/api/alerts/<id>/resolve`        | Marchează alertă ca rezolvată    |

---

## Funcționalități implementate

- [x] Schema PostgreSQL completă cu constrângeri, indecși și coloane calculate
- [x] View-uri SQL pentru Grafana (consum orar, pe cameră)
- [x] Modele SQLAlchemy (ORM)
- [x] Flask REST API cu 11 endpoint-uri
- [x] Simulator date cu profiluri orare realiste per tip dispozitiv
- [x] Detecție automată consum anormal și generare alerte
- [x] Calcul cost automat (RON) prin coloană generată PostgreSQL
- [x] Calcul curent (A) prin coloană generată PostgreSQL

## În lucru / urmează

- [ ] Dashboard-uri Grafana (JSON exportat)
- [ ] Endpoint `/api/recommendations` — sugestii optimizare consum
- [ ] Autentificare JWT pentru API
- [ ] Grafic consum prognozat (trend analysis)

---

## Exemple cereri API

```bash
# Sumar general
curl http://localhost:5000/api/summary

# Consum pe camere, ultimele 48h
curl "http://localhost:5000/api/devices?room_id=1"

# Adaugă citire manuală
curl -X POST http://localhost:5000/api/readings \
  -H "Content-Type: application/json" \
  -d '{"device_id": 1, "power_watts": 95.5}'
```

---

## Licență

Proiect academic — Universitatea Politehnica București, 2025–2026