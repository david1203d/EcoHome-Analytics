# Sistem de Evidenta si Analiza a Consumului de Energie intr-o Locuinta Inteligenta

**Lucrare de licenta** | Autor: Dobrinoiu David | Grupa 341C5  
Facultatea de Automatica si Calculatoare — Universitatea Politehnica Bucuresti 

---

## Descriere

Aplicatia colecteaza (sau simuleaza) date despre consumul de energie al dispozitivelor
dintr-o locuinta inteligenta. Datele sunt stocate intr-o baza de date relationala PostgreSQL,
analizate prin interogari SQL optimizate si vizualizate in Grafana prin dashboard-uri interactive.

Accentul este pus pe:
- Modelarea corecta a datelor (ER diagram, constrangeri, view-uri)
- Performanta interogarilor (indecsi pe coloane temporale)
- Generarea realista de date prin simulare (profiluri orare + zgomot gaussian)
- API REST curat pentru integrarea cu Grafana

---

## Arhitectura

```
+---------------------+     INSERT      +----------------------+
|  Simulator Python   | --------------> |   PostgreSQL         |
|  (profiluri orare)  |                 |   smart_home DB      |
+---------------------+                 +----------+-----------+
                                                   |
+---------------------+   SQLAlchemy               |
|  Flask REST API     | <--------------------------+
|  /api/*             |
+----------+----------+
           |  JSON
+----------v----------+   PostgreSQL   +----------------------+
|  Grafana            | <------------- |   PostgreSQL         |
|  Dashboards         |   datasource   |   (aceeasi instanta) |
+---------------------+                +----------------------+
```

---

## Tehnologii

| Componenta       | Tehnologie              | Versiune |
|------------------|-------------------------|----------|
| Backend API      | Python Flask            | 3.0.3    |
| ORM              | SQLAlchemy              | 2.0.30   |
| Baza de date     | PostgreSQL              | 16+      |
| Vizualizare      | Grafana                 | 11+      |
| Simulare date    | Python (psycopg2)       | 3.11+    |
| Driver BD        | psycopg2-binary         | 2.9.9    |

---

## Structura proiectului

```
EcoHome-Analytics/
|-- app.py              # Flask app principal - toate endpoint-urile REST
|-- models.py           # Modele SQLAlchemy (Room, Device, EnergyReading, Alert)
|-- config.py           # Configuratie (DB, cheie secreta)
|-- requirements.txt    # Dependente Python
|-- .env.example        # Template variabile de mediu
|
|-- sql/
|   `-- schema.sql      # Schema completa PostgreSQL (tabele, indecsi, view-uri, seed)
|
`-- scripts/
    `-- simulator.py    # Script simulare date (mod istoric + mod live)
```

---

## Model de date (ER)

```
rooms ---------------------- devices ---------------- energy_readings
  id PK                       id PK                    id PK
  name                        room_id FK               device_id FK
  floor                       name                     recorded_at
  area_sqm                    type                     power_watts
  created_at                  brand                    energy_kwh
                              power_rating_watts       cost_ron (generat)
                              is_active                voltage_v
                              installed_at             current_a (generat)
                              created_at
                                  |
                                  +---------------- alerts
                                                     id PK
                                                     device_id FK
                                                     alert_type
                                                     severity
                                                     message
                                                     resolved
```

**Indecsi de performanta:**
```sql
CREATE INDEX idx_readings_device_time ON energy_readings (device_id, recorded_at DESC);
CREATE INDEX idx_readings_time        ON energy_readings (recorded_at DESC);
```

---

## Instalare si rulare

### 1. Cerinte prealabile
- Python 3.11+
- PostgreSQL 16+
- Grafana 11+ (optional, pentru vizualizare)

### 2. Clonare si setup Python

```bash
git clone https://github.com/david1203d/EcoHome-Analytics.git
cd EcoHome-Analytics

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Editeaza .env cu datele tale PostgreSQL
```

### 3. Initializare baza de date

```bash
psql -U postgres -c "CREATE DATABASE smart_home;"
psql -U postgres -d smart_home -f sql/schema.sql
```

### 4. Generare date simulate (30 zile)

```bash
# Date istorice - ultimele 30 zile, citire la 5 minute
python scripts/simulator.py --days 30 --interval 5

# Mod live (o citire la fiecare 5 min, ruleaza continuu)
python scripts/simulator.py --live --interval 5
```

### 5. Pornire Flask API

```bash
python app.py
# API disponibil la http://localhost:5000
```

### 6. Configurare Grafana

1. Adauga datasource: **PostgreSQL** -> `localhost:5432 / smart_home`
2. Interogare exemplu pentru consum orar:
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

| Metoda | Endpoint                          | Descriere                        |
|--------|-----------------------------------|----------------------------------|
| GET    | `/`                               | Status API                       |
| GET    | `/api/rooms`                      | Lista camere                     |
| GET    | `/api/devices`                    | Lista dispozitive (cu filtre)    |
| GET    | `/api/devices/<id>`               | Detalii + consum lunar           |
| GET    | `/api/devices/<id>/readings`      | Citiri dispozitiv (?hours=24)    |
| GET    | `/api/readings`                   | Ultimele citiri globale          |
| POST   | `/api/readings`                   | Adauga citire noua               |
| GET    | `/api/summary`                    | Sumar 24h / 7 zile / luna        |
| GET    | `/api/summary/by-room`            | Consum agregat pe camera         |
| GET    | `/api/summary/by-type`            | Consum agregat pe tip            |
| GET    | `/api/alerts`                     | Alerte active                    |
| POST   | `/api/alerts/<id>/resolve`        | Marcheaza alerta ca rezolvata    |

---

## Functionalitati implementate

- [x] Schema PostgreSQL completa cu constrangeri, indecsi si coloane calculate
- [x] View-uri SQL pentru Grafana (consum orar, pe camera)
- [x] Modele SQLAlchemy (ORM)
- [x] Flask REST API cu 11 endpoint-uri
- [x] Simulator date cu profiluri orare realiste per tip dispozitiv
- [x] Detectie automata consum anormal si generare alerte
- [x] Calcul cost automat (RON) prin coloana generata PostgreSQL
- [x] Calcul curent (A) prin coloana generata PostgreSQL

## In lucru / urmeaza

- [ ] Dashboard-uri Grafana (JSON exportat)
- [ ] Endpoint /api/recommendations - sugestii optimizare consum
- [ ] Autentificare JWT pentru API
- [ ] Grafic consum prognozat (trend analysis)

---

## Exemple cereri API

```bash
# Sumar general
curl http://localhost:5000/api/summary

# Dispozitive dintr-o camera
curl "http://localhost:5000/api/devices?room_id=1"

# Adauga citire manuala
curl -X POST http://localhost:5000/api/readings \
  -H "Content-Type: application/json" \
  -d '{"device_id": 1, "power_watts": 95.5}'
```

---

## Licenta

<<<<<<< HEAD
Proiect academic — Universitatea Politehnica Bucuresti, 2024-2025
=======
Proiect academic — Universitatea Politehnica București, 2025–2026
>>>>>>> 46b3dd621702f5c9459ed6213c8bdc8b33dca64b
