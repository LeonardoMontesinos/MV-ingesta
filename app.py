import os
import csv
import io
import sys
import json
import time
import boto3
import sqlite3
import psycopg2
import mysql.connector
import pandas as pd
import requests
from pymongo import MongoClient
from datetime import datetime, date
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine

# =================================
# CONFIGURACIÓN GLOBAL
# =================================
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "ingestacinema")
S3_BASE_PREFIX = os.getenv("S3_PREFIX", "raw")

# --- Bases de datos ---
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")
PG_DB = os.getenv("PG_DB")

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB")

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "bookingsdb")

SQLITE_PATH = os.getenv("SQLITE_DB", "/mnt/theaters/theaters.db")

# --- Cliente AWS S3 ---
s3 = boto3.client("s3", region_name=AWS_REGION)

app = FastAPI(title="🎬 API Analítica de Ingesta")


# ===============================================================
# FUNCIONES AUXILIARES
# ===============================================================
def upload_to_s3(local_path, bucket, base_prefix, subfolder, filename):
    """Sube un archivo local a S3 en formato s3://bucket/prefix/..."""
    date_str = date.today().isoformat()
    key = f"{base_prefix}/{subfolder}/date={date_str}/{filename}"
    s3.upload_file(local_path, bucket, key)
    return f"s3://{bucket}/{key}"


def write_csv(df: pd.DataFrame, subfolder: str, out_dir="/data_ingesta"):
    """Guarda DataFrame localmente antes de subirlo."""
    today = date.today().isoformat()
    subdir = os.path.join(out_dir, subfolder, f"date={today}")
    os.makedirs(subdir, exist_ok=True)
    filename = f"{subfolder}.csv"
    path = os.path.join(subdir, filename)
    df.to_csv(path, index=False)
    return path, filename


# ===============================================================
# INGESTAS POR FUENTE
# ===============================================================
def ingest_postgres():
    """Extrae data de PostgreSQL (moviesdb)"""
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DB
        )
        print(f"[POSTGRES] Conectado a {PG_HOST}:{PG_PORT}")
        dfs = {
            "movies": pd.read_sql("SELECT * FROM movies;", conn),
            "showtimes": pd.read_sql("SELECT * FROM showtimes;", conn),
        }
        conn.close()

        uploaded = []
        for name, df in dfs.items():
            path, filename = write_csv(df, name)
            s3_uri = upload_to_s3(path, S3_BUCKET, S3_BASE_PREFIX, "movies", filename)
            uploaded.append({"source": name, "rows": len(df), "s3_uri": s3_uri})
        return uploaded

    except Exception as e:
        raise Exception(f"Error de conexión a PostgreSQL: {e}")


def ingest_mysql():
    """Extrae data de MySQL (usersdb)"""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB
        )
        print(f"[MYSQL] Conectado a {MYSQL_HOST}:{MYSQL_PORT}")
        df = pd.read_sql("SELECT * FROM users;", conn)
        conn.close()

        path, filename = write_csv(df, "users")
        s3_uri = upload_to_s3(path, S3_BUCKET, S3_BASE_PREFIX, "users", filename)
        return [{"source": "users", "rows": len(df), "s3_uri": s3_uri}]
    except Exception as e:
        raise Exception(f"Error de conexión a MySQL: {e}")


def ingest_mongo():
    """Extrae data de MongoDB (bookingsdb)"""
    try:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        docs = list(db.bookings.find())
        df = pd.DataFrame(docs)
        client.close()

        print(f"[MONGO] Conectado a {MONGO_URI}")
        path, filename = write_csv(df, "bookings")
        s3_uri = upload_to_s3(path, S3_BUCKET, S3_BASE_PREFIX, "bookings", filename)
        return [{"source": "bookings", "rows": len(df), "s3_uri": s3_uri}]
    except Exception as e:
        raise Exception(f"Error de conexión a MongoDB: {e}")


def ingest_sqlite():
    """Extrae data de SQLite (theaters.db vía NFS)"""
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        dfs = {
            "cinemas": pd.read_sql("SELECT * FROM cinemas;", conn),
            "salas": pd.read_sql("SELECT * FROM salas;", conn),
        }
        conn.close()
        print(f"[SQLITE] Leído desde {SQLITE_PATH}")

        uploaded = []
        for name, df in dfs.items():
            path, filename = write_csv(df, name)
            s3_uri = upload_to_s3(path, S3_BUCKET, S3_BASE_PREFIX, "theaters", filename)
            uploaded.append({"source": name, "rows": len(df), "s3_uri": s3_uri})
        return uploaded
    except Exception as e:
        raise Exception(f"Error de conexión a SQLite: {e}")


# ===============================================================
# ENDPOINTS
# ===============================================================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat(),
        "bucket": S3_BUCKET,
        "region": AWS_REGION,
    }


@app.post("/upload/all")
def upload_all():
    """Orquesta toda la ingesta"""
    try:
        uploaded = []
        print("🚀 Iniciando ingesta completa...")

        uploaded += ingest_postgres()
        uploaded += ingest_mysql()
        uploaded += ingest_mongo()
        uploaded += ingest_sqlite()

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "sources": uploaded
        }

    except Exception as e:
        print(f"Error general: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@app.post("/upload/{source}")
def upload_one(source: str):
    mapping = {
        "postgres": ingest_postgres,
        "mysql": ingest_mysql,
        "mongo": ingest_mongo,
        "sqlite": ingest_sqlite,
    }
    func = mapping.get(source)
    if not func:
        raise HTTPException(status_code=400, detail="Fuente no reconocida.")
    return func()
