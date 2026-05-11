# EcoHome Analytics — Sistem de Evidenta si Analiza a Consumului de Energie

**Lucrare de licenta** | Autor: Dobrinoiu David | Grupa 341C5
Facultatea de Automatica si Calculatoare — Universitatea Politehnica Bucuresti

---

## Descriere

EcoHome Analytics este o aplicatie web completa pentru monitorizarea, analiza si optimizarea consumului de energie intr-o locuinta inteligenta. Datele sunt simulate realist, stocate in PostgreSQL si prezentate printr-un dashboard web interactiv si dashboards Grafana.

Aplicatia nu se limiteaza la vizualizare — genereaza **recomandari personalizate**, detecteaza **anomalii de consum** direct in PostgreSQL, calculeaza **amprenta de carbon** si compara consumul saptamanal pentru a oferi utilizatorului informatii actionabile.

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
           |
    +------+-------+
    |              |
+---v----+   +-----v------+
|Dashboard|  |  Grafana   |
|Web      |  |  Dashboard |
|(port    |  |(port 3000) |
| 5000)   |  +------------+
+---------+
```

---

## Tehnologii

| Componenta       | Tehnologie          | Versiune |
|------------------|---------------------|----------|
| Backend API      | Python Flask        | 3.0.3    |
| ORM              | SQLAlchemy          | 2.0.30   |
| Baza de date     | PostgreSQL          | 16+      |
| Vizualizare web  | Chart.js            | 4.4.0    |
| Vizualizare BI   | Grafana             | 11+      |
| Simulare date    | Python (psycopg2)   | 3.11+    |

---

## Functionalitati implementate

### Core
- [x] Schema PostgreSQL completa: 4 tabele, indecsi compusi, coloane generate, view-uri
- [x] Flask REST API cu 17 endpoint-uri
- [x] Simulator date cu profiluri orare realiste per tip dispozitiv
- [x] Dashboard web interactiv (dark theme, Chart.js, auto-refresh 60s)
- [x] Dashboards Grafana conectate direct la PostgreSQL

### Analiza avansata (elemente de unicitate)
- [x] **Anomaly Detection** — detectie anomalii cu Z-score calculat in PostgreSQL
- [x] **Room Efficiency Score** — kWh/m² cu RANK() window function
- [x] **Carbon Footprint** — amprenta CO2 cu factor Romania (0.287 kg/kWh, ENTSO-E 2023)
- [x] **Smart Recommendations** — sfaturi personalizate generate din date reale
- [x] **Comparatie saptamanala** — CTE + FULL OUTER JOIN intre perioade

### Functionalitati PostgreSQL utilizate
- Generated Columns (cost_ron, current_a calculate automat)
- Window Functions (RANK, AVG OVER, moving average 7 zile)
- Composite Indexes (device_id, recorded_at DESC)
- CTEs — WITH daily AS (...)
- FULL OUTER JOIN pentru comparatii temporale
- Statistical functions (AVG, STDDEV pentru Z-score)
- date_trunc pentru agregari time-series
- ON CONFLICT DO NOTHING (upsert bulk)
- CHECK constraints pe toate tabelele
- Views (vw_room_consumption_24h, vw_hourly_consumption)

---

## Structura proiectului

```
EcoHome-Analytics/
|-- app.py               # Flask app — 17 endpoint-uri REST
|-- models.py            # Modele SQLAlchemy
|-- config.py            # Configuratie DB
|-- requirements.txt
|-- .env.example
|
|-- templates/
|   `-- index.html       # Dashboard web interactiv
|
|-- sql/
|   `-- schema.sql       # Schema PostgreSQL completa
|
|-- scripts/
|   `-- simulator.py     # Simulator date (mod istoric + live)
|
|-- diagrams/
|   |-- use_case.svg
|   |-- class_diagram.svg
|   |-- er_diagram.svg
|   |-- architecture.svg
|   `-- sequence.svg
|
`-- grafana-dashboards/
    `-- ecohome_dashboard.json
```

---

## Instalare si rulare

### 1. Cerinte
- Python 3.11+
- PostgreSQL 16+
- Grafana 11+ (optional)

### 2. Setup

```bash
git clone https://github.com/david1203d/EcoHome-Analytics.git
cd EcoHome-Analytics

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Editeaza .env cu parola ta PostgreSQL
```

### 3. Baza de date

```bash
psql -U postgres -c "CREATE DATABASE smart_home;"
psql -U postgres -d smart_home -f sql/schema.sql
```

### 4. Generare date simulate

```bash
python scripts/simulator.py --days 30 --interval 5
```

### 5. Pornire aplicatie

```bash
python app.py
```

Dashboard web: **http://localhost:5000**

### 6. Grafana (optional)

1. Instaleaza Grafana de la grafana.com
2. Adauga datasource PostgreSQL: `localhost:5432 / smart_home`
3. Importa `grafana-dashboards/ecohome_dashboard.json`

---

## API Endpoints

### Date de baza
| Metoda | Endpoint                     | Descriere                     |
|--------|------------------------------|-------------------------------|
| GET    | `/`                          | Dashboard web                 |
| GET    | `/api/rooms`                 | Lista camere                  |
| GET    | `/api/devices`               | Lista dispozitive             |
| GET    | `/api/devices/<id>`          | Detalii + consum lunar        |
| GET    | `/api/devices/<id>/readings` | Citiri dispozitiv             |
| GET    | `/api/readings`              | Ultimele citiri globale       |
| POST   | `/api/readings`              | Adauga citire noua            |

### Sumar si agregari
| Metoda | Endpoint                     | Descriere                     |
|--------|------------------------------|-------------------------------|
| GET    | `/api/summary`               | Sumar 24h / 7 zile / luna     |
| GET    | `/api/summary/by-room`       | Consum agregat pe camera      |
| GET    | `/api/summary/by-type`       | Consum agregat pe tip         |
| GET    | `/api/summary/by-device`     | Top dispozitive dupa consum   |
| GET    | `/api/consumption/hourly`    | Consum orar (time series)     |

### Analiza avansata
| Metoda | Endpoint                     | Descriere                     |
|--------|------------------------------|-------------------------------|
| GET    | `/api/anomalies`             | Detectie anomalii (Z-score)   |
| GET    | `/api/efficiency`            | Scor eficienta camere (kWh/m²)|
| GET    | `/api/carbon`                | Amprenta carbon (kg CO2)      |
| GET    | `/api/recommendations`       | Recomandari personalizate     |
| GET    | `/api/comparison`            | Comparatie saptamanala        |
| GET    | `/api/trends`                | Trend 30 zile + moving avg    |

### Alerte
| Metoda | Endpoint                          | Descriere              |
|--------|-----------------------------------|------------------------|
| GET    | `/api/alerts`                     | Alerte active          |
| POST   | `/api/alerts/<id>/resolve`        | Rezolva alerta         |

---

## Exemple cereri API

```bash
# Dashboard principal
curl http://localhost:5000/

# Anomalii detectate
curl http://localhost:5000/api/anomalies

# Eficienta camere
curl http://localhost:5000/api/efficiency

# Amprenta carbon
curl http://localhost:5000/api/carbon

# Recomandari personalizate
curl http://localhost:5000/api/recommendations

# Comparatie saptamanala
curl http://localhost:5000/api/comparison
```

---

## Licenta

Proiect academic — Universitatea Politehnica Bucuresti, 2025-2026