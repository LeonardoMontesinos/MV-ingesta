# API de Ingesta de Datos — Cine MVCinema

Este microservicio realiza la **extracción (pull)** de datos desde múltiples bases de datos alojadas en otra máquina virtual (MV de datos) y los **sube a un bucket S3** en formato CSV.

Los orígenes son:

| Fuente        | Base de datos | Motor    | Descripción |
|----------------|---------------|-----------|--------------|
| Movies         | PostgreSQL     | `moviesdb` | Catálogo de películas y funciones |
| Users          | MySQL          | `usersdb`  | Información de usuarios |
| Bookings       | MongoDB        | `bookingsdb` | Reservas de entradas |
| Theaters       | SQLite (NFS)   | `theaters.db` | Cines y salas |

---

## Arquitectura General

```
+---------------------+       +-------------------------+       +----------------------+
|  MV Datos (RDS/EC2) | <---> |  MV Ingesta (FastAPI)   | --->  |  AWS S3 (Data Lake)  |
|  Postgres/MySQL/... |       |  Docker + Python + boto3|       |  /raw/movies/...     |
+---------------------+       +-------------------------+       +----------------------+
```

---

## 1. Configuración de AWS CLI

Para que el contenedor pueda subir datos al bucket, primero debes configurar las credenciales en tu máquina (no dentro del contenedor):

```bash
sudo apt-get update -y
sudo apt-get install -y unzip curl
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install --update
aws --version
```

Luego, ejecuta:

```bash
aws configure
```

Completa los campos así:

| Campo                     | Ejemplo (reemplazar con los tuyos)         | Descripción |
|----------------------------|--------------------------------------------|--------------|
| **AWS Access Key ID**      | `AKIAxxxxxxxxxxxxxxxx`                    | Tu clave de acceso AWS |
| **AWS Secret Access Key**  | `abcd1234xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`  | Tu clave secreta |
| **Default region name**    | `us-east-1`                               | Región del bucket |
| **Default output format**  | `json`                                    | Formato de salida por defecto |

Verifica que las credenciales funcionen:
```bash
aws sts get-caller-identity
```

Salida esperada:
```json
{
  "UserId": "AIDAEXAMPLE",
  "Account": "188118402639",
  "Arn": "arn:aws:sts::188118402639:assumed-role/..."
}
```

Y que tu bucket esté visible:
```bash
aws s3 ls
```

---

## 2. Archivo `.env` — Configuración del Microservicio

Crea un archivo `.env` dentro de la carpeta raíz (`~/api-ingesta/.env`):

```env
# AWS CONFIG
AWS_REGION=us-east-1
S3_BUCKET=ingestamvcinema
S3_BASE_PREFIX=raw/

# PostgreSQL (Movies)
POSTGRES_MOVIES_URL=postgresql://postgres:postgres@172.31.28.90:15432/moviesdb

# MySQL (Users)
MYSQL_USERS_URL=mysql://usersuser:userspass@172.31.28.90:3307/usersdb

# MongoDB (Bookings)
MONGO_URL=mongodb://172.31.28.90:27017/
MONGO_DB=bookingsdb
MONGO_COLLECTION=bookings

# SQLite (Theaters - NFS)
SQLITE_DB=/mnt/theaters/theaters.db

# API CONFIG
API_PORT=8000
LOG_LEVEL=INFO
UPLOAD_TIMEOUT=60
```

>  Asegúrate de usar las **IPs privadas correctas** de la MV donde están los contenedores de base de datos.

---

## 3. Levantar la API con Docker

Ejecuta desde la carpeta del proyecto:

```bash
docker compose up -d --build
```

Verifica que el contenedor esté activo:
```bash
docker ps
```

Deberías ver algo como:
```
CONTAINER ID   IMAGE                    COMMAND                  PORTS                    NAMES
e3a4fdb3f2a1   api-ingesta-ingest-api   "uvicorn app:app --h…"   0.0.0.0:8000->8000/tcp   ingest_api
```

---

## 4. Probar la API

Verifica que la API esté viva:
```bash
curl http://localhost:8000/health
```

Ejemplo de salida:
```json
{
  "status": "ok",
  "time": "2025-10-07T03:45:00Z",
  "bucket": "ingestamvcinema",
  "region": "us-east-1"
}
```

---

## 5. Ejecutar la ingesta completa

Ejecuta:
```bash
curl -X POST http://localhost:8000/upload/all
```

Salida esperada (resumen):
```json
{
  "status": "success",
  "timestamp": "2025-10-07T03:52:44.543642",
  "sources": [
    {"source":"movies","rows":500,"s3_uri":"s3://ingestamvcinema/raw/movies/..."},
    {"source":"users","rows":2000,"s3_uri":"s3://ingestamvcinema/raw/users/..."},
    {"source":"bookings","rows":20000,"s3_uri":"s3://ingestamvcinema/raw/bookings/..."},
    {"source":"theaters","rows":2234,"s3_uri":"s3://ingestamvcinema/raw/theaters/..."}
  ]
}
```

---

## 6. Estructura en AWS S3

Dentro del bucket `ingestamvcinema`, los datos se organizan así:

```
s3://ingestamvcinema/raw/
│
├── movies/
│   ├── date=2025-10-07/movies.csv
│   └── date=2025-10-07/showtimes.csv
│
├── users/
│   └── date=2025-10-07/users.csv
│
├── bookings/
│   └── date=2025-10-07/bookings.csv
│
└── theaters/
    ├── date=2025-10-07/cinemas.csv
    └── date=2025-10-07/salas.csv
```

---

## 7. Detener y limpiar contenedores

```bash
docker compose down -v
```

Esto detiene el contenedor y elimina volúmenes temporales.

---

## Resultado Final

- Todos los datos consolidados en tu bucket S3.
- API de ingesta lista para ejecutarse periódicamente (cronjob, Lambda o Airflow).
- Estructura escalable para más fuentes.

---
