# Big Data Entreprise — Ingestion données belges (BCE)

Pipeline d'ingestion et d'analyse de données d'entreprises belges : registre KBO, comptes annuels CBSO/NBB, publications eJustice et statuts notariaux Stapor.

## Architecture

```
KBO (CSV) ──► MongoDB ◄── Airflow DAG ──► HDFS (Bronze)
                    │
CBSO / eJustice ────┘              Stapor (script local) ──► HDFS
```

| Service | Port | URL |
|---------|------|-----|
| Airflow UI | 8080 | http://localhost:8080 |
| Mongo Express | 8081 | http://localhost:8081 |
| HDFS Namenode | 9870 | http://localhost:9870 |
| MongoDB | 27017 | `mongodb://localhost:27017` |
| Tor proxies | 9050–9055 | (interne Docker) |

Identifiants par défaut :
- **Airflow** : `admin` / `admin`
- **Mongo Express** : `admin` / `admin`

## Prérequis

1. **Docker Desktop**
2. **Python 3.10+**
3. **Données KBO Open Data**
   Extraire les CSV dans `data/kbo/` (voir structure ci-dessous)

```
data/kbo/
├── enterprise.csv
├── denomination.csv
├── address.csv
├── activity.csv
├── contact.csv
├── establishment.csv
└── code.csv
```

## Démarrage rapide (WSL)

> Prérequis WSL : Docker Desktop avec intégration WSL activée (Settings → Resources → WSL Integration).

```bash
# 1. Aller dans le projet (chemin Windows monté sous /mnt/c/)
cd /mnt/c/Users/33650/Downloads/ipssi_big_data_entreprise/big_data_entreprise

# 2. Environnement Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 3. Placer les CSV KBO
mkdir -p data/kbo
# cp /chemin/vers/KboOpenData_*/enterprise.csv data/kbo/
# ... (tous les CSV listés ci-dessus)

# 4. Lancer l'infrastructure Docker
docker compose up -d
docker compose ps   # attendre que les services soient Up

# 5. Peupler MongoDB
cd dags
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DB="belgique"
python init_mongodb.py --kbo-path "../data/kbo"
cd ..

# 6. Tester un script standalone
python consult.py

# 7. Airflow → http://localhost:8080 (admin / admin)
#    Activer le DAG enterprise_ingestion, Trigger avec enterprise_number = 0878.065.378
```

### Arrêter / redémarrer

```bash
docker compose down          # arrêt
docker compose down -v       # arrêt + suppression des volumes (données perdues)
docker compose up -d         # redémarrage
```

## Parcours de test complet

### Étape 1 — Peupler MongoDB avec les données KBO

```bash
cd dags
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DB="belgique"
python init_mongodb.py --kbo-path "../data/kbo"
```

Chemin personnalisé :

```bash
python init_mongodb.py --kbo-path "/home/user/data/KboOpenData_Full"
```

Vérifier dans Mongo Express (http://localhost:8081) → base `belgique` → collection `enterprises`.

### Étape 2 — Lancer l'ingestion via Airflow

1. Ouvrir http://localhost:8080 (login `admin` / `admin`)
2. Activer le DAG **`enterprise_ingestion`** (toggle à gauche)
3. Cliquer sur **Trigger DAG** (▶) avec les paramètres :

| Paramètre | Valeur de test | Description |
|-----------|----------------|-------------|
| `enterprise_number` | `0878.065.378` | Google Belgium (vide = batch MongoDB) |
| `start_year` | `2020` | Année minimale pour CBSO |
| `sources` | `["cbso", "ejustice"]` | Sources à ingérer |
| `batch_size` | `10` | Taille du batch (mode bulk) |

4. Suivre l'exécution dans l'onglet **Graph** ou **Logs**

Les fichiers ingérés sont stockés dans HDFS sous `/data/bronze/{numero_bce}/`.

### Étape 3 — Vérifier HDFS

Ouvrir http://localhost:9870 → **Utilities** → **Browse the file system** → `/data/bronze/`.

## Scripts standalone (sans Airflow)

Ces scripts tournent sur la machine hôte. HDFS doit être démarré (`docker compose up -d`).

### CBSO — KPIs financiers (`consult.py`)

Récupère les comptes annuels CBSO et calcule des KPIs pour une entreprise.

```bash
# Modifier enterprise_number en bas du fichier si besoin
python consult.py
```

### Stapor — statuts notariaux en local (`strapor.py`)

Télécharge les statuts notariaux en PDF local (`tmp/notaire/`). Ouvre Chrome via Playwright pour passer le challenge F5.

```bash
python strapor.py
```

### Stapor — statuts vers HDFS (`stapor_scraper.py`)

Même source, mais stocke les PDFs dans HDFS.

```bash
export HDFS_URL="http://localhost:9870"
export HDFS_USER="hdfs"
python -c "from stapor_scraper import run; run(['0878.065.378'])"
```

## Notebook Jupyter (`BCE.ipynb`)

Notebook principal du projet (exploration KBO, CBSO, eJustice, visualisations).

```bash
jupyter notebook BCE.ipynb
# ou
jupyter lab
```

Configurer le chemin KBO dans la première cellule de code :

```python
KBO_PATH = "./data/kbo"
```

Les cellules HDFS utilisent `http://localhost:9870` avec l'utilisateur `hdfs`.

## Variables d'environnement

| Variable | Défaut | Usage |
|----------|--------|-------|
| `KBO_PATH` | `./data/kbo` | Chemin vers les CSV KBO |
| `MONGO_URI` | `mongodb://localhost:27017` | Connexion MongoDB |
| `MONGO_DB` | `belgique` | Nom de la base |
| `HDFS_URL` | `http://localhost:9870` | WebHDFS (scripts locaux) |
| `HDFS_USER` | `hdfs` | Utilisateur HDFS (scripts locaux) |

Dans Docker, Airflow utilise `http://namenode:9870` et l'utilisateur `airflow` (configuré dans `dags/ingestion_dag.py`).

## Structure du projet

```
big_data_entreprise/
├── docker-compose.yml           # Infrastructure (Airflow, HDFS, MongoDB, Tor)
├── dags/
│   ├── ingestion_dag.py         # DAG Airflow principal
│   ├── init_mongodb.py          # Chargement KBO → MongoDB (enterprises)
│   ├── build_enterprise_finale.py  # Bronze nested → enterprise_finale
│   ├── build_silver.py          # Silver → enterprise_silver
│   ├── seed_hotel_state.py      # StateDB pending hôtellerie
│   ├── scrape_hotel_cbso.py     # Scraping CBSO hôtellerie 2021+
│   ├── silver/                  # Transformations Silver
│   ├── filters/                 # Filtres sectoriels (hôtellerie)
│   ├── db/                      # Clients MongoDB & State DB
│   └── scrapers/                # CBSO, eJustice, Tor
├── hadoop-config/               # Configuration HDFS
├── BCE.ipynb                    # Notebook d'analyse
├── consult.py                   # Script CBSO standalone
├── strapor.py                   # Stapor → fichiers locaux
├── stapor_scraper.py            # Stapor → HDFS
├── data/kbo/                    # CSV KBO (à fournir)
└── requirements.txt
```

## Jour 2 — Silver + Hôtellerie

### 1. Bronze nested (si `enterprise_finale` absente)

```bash
cd dags
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DB="belgique"
python build_enterprise_finale.py --kbo-path "../data/kbo"
# Test : python build_enterprise_finale.py --limit 1000
```

### 2. Couche Silver

```bash
python build_silver.py
# Source explicite : python build_silver.py --source enterprise_finale
```

Vérifier dans Mongo Express : collection `enterprise_silver` (dates ISO, labels, 1 adresse REGO).

### 3. Filtre hôtellerie + StateDB

```bash
python seed_hotel_state.py
```

### 4. Scraping CBSO hôtellerie (CSV 2021–2025)

```bash
export HDFS_URL="http://localhost:9870"
export HDFS_USER="root"

# Test sur 5 entreprises
python scrape_hotel_cbso.py --limit 5

# Run complet
python scrape_hotel_cbso.py

# Reprise après 429
python scrape_hotel_cbso.py --resume
```

Fichiers HDFS : `/data/bronze/{bce}/nbb/{year}/{reference}.csv`

### 5. Via Airflow (alternative)

Trigger DAG `enterprise_ingestion` avec :

```json
{
  "sector": "hotel",
  "sources": ["cbso"],
  "csv_start_year": 2021,
  "batch_size": 50
}
```

## Dépannage

**Airflow ne démarre pas**
```bash
docker compose logs airflow-scheduler
docker compose logs airflow-webserver
```

**MongoDB vide après init**
- Vérifier que les CSV sont bien dans `data/kbo/`
- Relancer `python init_mongodb.py` depuis le dossier `dags/`

**Playwright / Chrome (Stapor)**
```bash
playwright install chromium
```
Le script ouvre une fenêtre Chrome visible pour contourner le challenge F5 de notaire.be.

**HDFS inaccessible depuis l'hôte**
- Vérifier que le namenode tourne : http://localhost:9870
- Utiliser `HDFS_URL=http://localhost:9870` (pas `namenode:9870` depuis l'hôte)

**Tor / rate limiting CBSO**
Les proxies Tor (ports 9050–9055) sont utilisés automatiquement par le DAG Airflow pour éviter les blocages 429.

## Jour 3 — Gold Layer + API + Frontend

### 1. Construire la couche Gold

Lit les CSV PCMN depuis HDFS (`/data/bronze/{bce}/nbb/{year}/`) et peuple `hotel_gold` :

```bash
cd dags && source ../.venv/bin/activate
export MONGO_URI="mongodb://localhost:27017" MONGO_DB="belgique"
export HDFS_URL="http://localhost:9870" HDFS_USER="root"

# Test sur 10 entreprises
python build_gold.py --limit 10

# Run complet (4908 hôtels done CBSO)
python build_gold.py
```

### 2. Lancer l'API FastAPI

```bash
# Depuis la racine du projet
source .venv/bin/activate
pip install fastapi uvicorn
uvicorn api.main:app --reload --port 8000
```

Ou via Docker : `docker compose up api -d` → http://localhost:8000/docs

Endpoints :
- `GET /api/search?q=hotel`
- `GET /api/enterprise/{bce}`
- `GET /api/enterprise/{bce}/dirigeants`
- `GET /api/enterprise/{bce}/statuts/stream` (SSE)

### 3. Lancer le frontend React

```bash
cd frontend
npm install
npm run dev
```

→ http://localhost:5173 (proxy API vers :8000)

### 4. DAG recalcul Gold

DAG Airflow `gold_recalculation` — schedule annuel, relance `build_gold.py` sur les entreprises CBSO done.

## Entreprises de test

| Entreprise | Numéro BCE |
|------------|------------|
| Google Belgium | `0878.065.378` |
| Apple Retail Belgium | `0836.157.420` |
| SNCB | `0203.430.576` |
