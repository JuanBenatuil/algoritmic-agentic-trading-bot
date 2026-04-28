# =============================================
# Dockerfile — Auto DayTrading Bot
# =============================================
# Imagen de producción: código baked-in, sin volúmenes de fuente.
# Para desarrollo local usa: docker compose up --build

FROM python:3.12-slim

# Evita que Python escriba .pyc y que bufferee stdout/stderr
# (importante para ver logs en tiempo real en el VPS)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero (capa cacheada por Docker)
# Solo se reconstruye si requirements.txt cambia
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente del bot
COPY main.py .
COPY src/ ./src/

# Crear carpeta de logs dentro del contenedor
RUN mkdir -p logs

# El bot corre como script continuo; el scheduler interno
# controlará el timing de las operaciones
CMD ["python", "main.py"]
