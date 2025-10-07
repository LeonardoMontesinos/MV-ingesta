# ---- Imagen base -----
FROM python:3.12-slim

# ---- Variables de entorno ----
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---- Directorio de trabajo ----
WORKDIR /app

# ---- Instalar dependencias del sistema ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# ---- Copiar archivos de la app ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# ---- Puerto expuesto ----
EXPOSE 8000

# ---- Comando por defecto ----
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
