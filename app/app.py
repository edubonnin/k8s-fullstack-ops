from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix
import psycopg2
import redis
import os
import sys
import json
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)
# Aplicar ProxyFix para manejar correctamente las cabeceras del Load Balancer (Nginx)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')

# Configuración de variables de entorno
ENV = os.getenv('ENV', 'dev').lower()

try:
    DB_HOST = os.environ['DB_HOST']
    DB_USER = os.environ['DB_USER']
    DB_PASSWORD = os.environ['DB_PASSWORD']
    DB_NAME = os.environ['DB_NAME']
except KeyError as e:
    # Mensaje claro en los logs de Kubernetes antes de morir
    print(f"❌ ERROR DE CONFIGURACIÓN: Falta la variable de entorno obligatoria {e}")
    sys.exit(1)

# Variables no críticas (pueden tener fallback)
DB_PORT = os.getenv('DB_PORT', '5432')

if ENV == 'pro':
    REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
else:
    REDIS_HOST = None

REDIS_PORT = os.getenv('REDIS_PORT', '6379')
REDIS_MESSAGE_KEY = os.getenv('REDIS_MESSAGE_KEY', 'app:message')
CARS_CACHE_KEY = os.getenv('CARS_CACHE_KEY', 'app:cars')
CARS_CACHE_TTL = int(os.getenv('CARS_CACHE_TTL', '300'))
REDIS_ENABLED = REDIS_HOST is not None

# MinIO Config
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio-service:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'assets')

_redis_client = None


def get_redis_client():
    """Devuelve una instancia reutilizable de Redis cuando está habilitado."""
    global _redis_client

    if not REDIS_ENABLED:
        return None

    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=REDIS_HOST,
                port=int(REDIS_PORT),
                socket_connect_timeout=3,
                decode_responses=True
            )
        except Exception as exc:  # pragma: no cover - logging auxiliar
            print(f"No se pudo inicializar Redis: {exc}")
            _redis_client = None

    return _redis_client


def invalidate_cars_cache():
    """Elimina la caché de coches para forzar su recálculo."""
    if not REDIS_ENABLED:
        return

    client = get_redis_client()
    if not client:
        return

    try:
        client.delete(CARS_CACHE_KEY)
    except Exception as exc:  # pragma: no cover - logging auxiliar
        print(f"No se pudo invalidar la caché de coches: {exc}")

# Verifica conexión con Postgres


def check_database():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=3
        )
        conn.close()
        return {
            'status': 'connected',
            'message': 'PostgreSQL conectado correctamente',
            'healthy': True
        }
    except Exception as e:
        return {
            'status': 'disconnected',
            'message': f'Error: {str(e)}',
            'healthy': False
        }

# Verifica conexión con Redis


def check_redis():
    if not REDIS_ENABLED:
        return None

    client = get_redis_client()
    if not client:
        return {
            'status': 'disconnected',
            'message': 'No se pudo inicializar la conexión con Redis',
            'healthy': False
        }

    try:
        client.ping()
        return {
            'status': 'connected',
            'message': 'Redis conectado correctamente',
            'healthy': True
        }
    except Exception as exc:
        return {
            'status': 'disconnected',
            'message': f'Error: {str(exc)}',
            'healthy': False
        }

# Inicializa la base de datos con una tabla de ejemplo"""


def init_database():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()

        # Crear tabla si no existe
        cur.execute("""
            CREATE TABLE IF NOT EXISTS health_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                status VARCHAR(50)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS cars (
                id SERIAL PRIMARY KEY,
                brand VARCHAR(100) NOT NULL,
                model VARCHAR(100) NOT NULL,
                year INTEGER NOT NULL CHECK (year >= 1886),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cars_brand_model_year
            ON cars (brand, model, year)
        """)

        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error inicializando base de datos: {e}")
        return False

# Registra el healthcheck en la base de datos"""


def log_health_check():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO health_logs (timestamp, status) VALUES (%s, %s)",
            (datetime.now(), 'healthy')
        )

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error logging health check: {e}")

# Uso de caché con redis


def get_cached_data():
    if not REDIS_ENABLED:
        return None

    try:
        client = get_redis_client()
        if not client:
            return None

        # Intentar obtener datos de caché
        cached = client.get('health_count')

        if cached:
            count = int(cached)
        else:
            # Simular consulta a BD
            count = 1

        # Incrementar y guardar en caché
        count += 1
        client.setex('health_count', 300, count)  # 5 minutos de TTL

        return count
    except Exception as e:
        print(f"Error usando Redis: {e}")
        return None

# Recupera la lista de coches registrados con soporte de caché


def get_cars(use_cache=True):
    cache_client = get_redis_client() if REDIS_ENABLED else None

    if use_cache and cache_client:
        try:
            cached_raw = cache_client.get(CARS_CACHE_KEY)
            if cached_raw:
                cached_data = json.loads(cached_raw)
                cars = []
                for item in cached_data:
                    created_at = item.get('created_at')
                    cars.append({
                        'id': item['id'],
                        'brand': item['brand'],
                        'model': item['model'],
                        'year': item['year'],
                        'created_at': datetime.fromisoformat(created_at) if created_at else None
                    })
                return cars, None, True
        except Exception as exc:  # pragma: no cover - logging auxiliar
            print(f"Error leyendo caché de coches: {exc}")

    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, brand, model, year, created_at
            FROM cars
            ORDER BY created_at DESC, id DESC
            """
        )
        rows = cur.fetchall()
        cur.close()

        cars = [
            {
                'id': row[0],
                'brand': row[1],
                'model': row[2],
                'year': row[3],
                'created_at': row[4]
            }
            for row in rows
        ]

        if cache_client and use_cache:
            try:
                cache_payload = [
                    {
                        'id': car['id'],
                        'brand': car['brand'],
                        'model': car['model'],
                        'year': car['year'],
                        'created_at': car['created_at'].isoformat() if car['created_at'] else None
                    }
                    for car in cars
                ]
                cache_client.setex(
                    CARS_CACHE_KEY, CARS_CACHE_TTL, json.dumps(cache_payload))
            except Exception as exc:  # pragma: no cover - logging auxiliar
                print(f"Error actualizando caché de coches: {exc}")

        return cars, None, False
    except Exception as exc:
        return [], str(exc), False
    finally:
        if conn:
            conn.close()

# Inserta un coche en la base de datos


def create_car(brand, model, year):
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cars (brand, model, year)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (brand, model, year)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        invalidate_cars_cache()
        return new_id, None
    except Exception as e:
        if conn:
            conn.rollback()
        return None, str(e)
    finally:
        if conn:
            conn.close()

# Obtención del mensaje almacenado en redis


def get_redis_message():
    if not REDIS_ENABLED:
        return None, None

    try:
        client = get_redis_client()
        if not client:
            return None, 'No se pudo inicializar la conexión con Redis'
        message = client.get(REDIS_MESSAGE_KEY)
        return message, None
    except Exception as exc:
        return None, str(exc)

# Eliminación de coche por ID


def delete_car(car_id):
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        cur.execute("DELETE FROM cars WHERE id = %s", (car_id,))
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        if deleted:
            invalidate_cars_cache()
            return True, None
        return False, 'Registro no encontrado'
    except Exception as e:
        if conn:
            conn.rollback()
        return False, str(e)
    finally:
        if conn:
            conn.close()


def get_minio_client():
    try:
        # Ensure endpoint starts with http protocol if not present
        endpoint = MINIO_ENDPOINT
        if not endpoint.startswith('http'):
            endpoint = f"http://{endpoint}"

        s3 = boto3.client('s3',
                          endpoint_url=endpoint,
                          aws_access_key_id=MINIO_ACCESS_KEY,
                          aws_secret_access_key=MINIO_SECRET_KEY,
                          config=boto3.session.Config(
                              signature_version='s3v4'),
                          region_name='us-east-1')
        return s3
    except Exception as e:
        print(f"Error connecting to MinIO: {e}")
        return None


@app.route('/favicon.ico')
def favicon():
    s3 = get_minio_client()
    if not s3:
        return "MinIO unavailable", 503

    try:
        # Fetch the file from MinIO and stream it to the user
        file_obj = s3.get_object(Bucket=MINIO_BUCKET, Key='favicon.ico')
        return file_obj['Body'].read(), 200, {'Content-Type': 'image/x-icon'}
    except ClientError as e:
        print(f"Error fetching favicon from MinIO: {e}")
        return "Favicon not found", 404
    except Exception as e:
        print(f"Error: {e}")
        return str(e), 500

# Endpoint raíz -> Página principal


@app.route('/')
def index():
    db_status = check_database()
    redis_status = check_redis()
    cars = []
    cars_error = None
    cars_from_cache = False
    redis_message = None
    redis_message_error = None

    # Intentar obtener datos (priorizando caché) independientemente del estado de la BD
    cars, cars_error, cars_from_cache = get_cars()

    # Si falló y la BD está caída, el error será el de conexión a BD
    if cars_error and not db_status['healthy']:
        cars_error = f'Base de datos no disponible: {cars_error}'

    if redis_status and redis_status['healthy'] and redis_status['status'] == 'connected':
        redis_message, redis_message_error = get_redis_message()
    elif redis_status and redis_status['status'] == 'disconnected':
        redis_message_error = redis_status['message']

    # Obtener el hostname del contenedor
    hostname = os.getenv('INSTANCE_NAME', os.getenv('HOSTNAME', 'unknown'))

    return render_template(
        'index.html',
        db_status=db_status,
        redis_status=redis_status,
        env=ENV,
        cars=cars,
        cars_error=cars_error,
        cars_from_cache=cars_from_cache,
        redis_message=redis_message,
        redis_message_error=redis_message_error,
        redis_message_key=REDIS_MESSAGE_KEY,
        hostname=hostname
    )

# Formulario para añadir coches


@app.route('/cars', methods=['POST'])
def add_car():
    brand = request.form.get('brand', '').strip()
    model = request.form.get('model', '').strip()
    year_raw = request.form.get('year', '').strip()

    if not brand or not model or not year_raw:
        flash('Todos los campos son obligatorios.', 'error')
        return redirect(url_for('index'))

    try:
        year = int(year_raw)
    except ValueError:
        flash('El año debe ser un número entero.', 'error')
        return redirect(url_for('index'))

    current_year = datetime.now().year
    if year < 1886 or year > current_year:
        flash(f'El año debe estar entre 1886 y {current_year}.', 'error')
        return redirect(url_for('index'))

    _, error = create_car(brand, model, year)
    if error:
        flash(f'No se pudo registrar el coche: {error}', 'error')
    else:
        flash('Coche añadido correctamente.', 'success')

    return redirect(url_for('index'))

# Eliminación de coches


@app.route('/cars/<int:car_id>/delete', methods=['POST'])
def remove_car(car_id):
    success, error = delete_car(car_id)
    if success:
        flash('Coche eliminado correctamente.', 'success')
    else:
        flash(f'No se pudo eliminar el coche: {error}', 'error')
    return redirect(url_for('index'))

# Registro de dos endpoints para healthcheck


@app.route('/status')
@app.route('/health')
def health():
    db_status = check_database()
    redis_status = check_redis()

    # Log del healthcheck en BD
    if db_status['healthy']:
        log_health_check()

    # Obtener contador de caché si está disponible
    cache_count = get_cached_data()
    cars_count = None
    cars_from_cache = False
    redis_message = None

    # Intentar obtener coches (priorizando caché)
    cars, error, cars_from_cache = get_cars()
    if not error:
        cars_count = len(cars)

    if redis_status and redis_status['healthy'] and redis_status['status'] == 'connected':
        redis_message, _ = get_redis_message()

    overall_healthy = db_status['healthy'] and (
        redis_status['healthy'] if redis_status else True)
    services = {
        'database': db_status
    }
    if redis_status:
        services['cache'] = redis_status

    response = {
        'status': 'healthy' if overall_healthy else 'unhealthy',
        'timestamp': datetime.now().isoformat(),
        'environment': ENV,
        'services': services
    }

    if cache_count:
        response['cache_requests'] = cache_count
    if cars_count is not None:
        response['data'] = {
            'cars_count': cars_count,
            'cars_source': 'cache' if cars_from_cache else 'database'
        }
    if redis_message:
        response.setdefault('data', {})['redis_message'] = redis_message

    status_code = 200 if overall_healthy else 503
    return jsonify(response), status_code

# Endpoint para testear persistencia


@app.route('/db-test')
def db_test():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()

        # Insertar un registro de prueba
        cur.execute(
            "INSERT INTO health_logs (timestamp, status) VALUES (%s, %s) RETURNING id",
            (datetime.now(), 'test')
        )
        new_id = cur.fetchone()[0]

        # Obtener todos los registros
        cur.execute("SELECT COUNT(*) FROM health_logs")
        count = cur.fetchone()[0]

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Registro creado con ID: {new_id}',
            'total_records': count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # Inicializar BD al arrancar
    print("Inicializando base de datos...")
    if init_database():
        print("Base de datos inicializada correctamente")
    else:
        print("Error inicializando base de datos")

    # Iniciar aplicación
    app.run(host='0.0.0.0', port=5000, debug=(ENV == 'dev'))
