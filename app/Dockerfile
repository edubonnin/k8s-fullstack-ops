FROM python:3.12-slim

# Fuerza a que los logs salgan inmediatamente a la consola y evita que Python genere archivos compilados .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Crear un usuario no-root por seguridad
RUN adduser --disabled-password --gecos '' appuser

# Instalar dependencias
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY . .

# Cambiar al usuario seguro
USER appuser

EXPOSE 5000

# Comando por defecto
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:app"]
