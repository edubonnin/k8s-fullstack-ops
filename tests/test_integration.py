import pytest
import requests
import os
import time

# URL base
BASE_URL = os.getenv('TEST_URL')

@pytest.fixture(scope="module")
# Realiza la petición una sola vez por sesión de prueba para eficiencia
def app_response():
    try:
        # Petición al endpoint de health que devuelve JSON
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        return response
    except requests.exceptions.ConnectionError:
        pytest.fail(f"❌ No se pudo conectar a {BASE_URL}")

# Verifica que el servidor responde con un 200
def test_endpoint_reachable(app_response):
    assert app_response.status_code == 200, f"Se esperaba 200, se recibió {app_response.status_code}"
    assert app_response.headers['Content-Type'] == 'application/json', "La respuesta debería ser JSON"

# Verifica la conexión a PostgreSQL
def test_database_healthy(app_response):
    data = app_response.json()
    
    assert 'services' in data, "La respuesta no contiene la clave 'services'"
    assert 'database' in data['services'], "No hay información de la base de datos"
    
    db_status = data['services']['database']
    assert db_status['healthy'] is True, f"La BD no está saludable: {db_status.get('error')}"

# Verifica Redis
def test_redis_status(app_response):
    data = app_response.json()
    env = data.get('environment', 'unknown')
    
    if env == 'prod':
        # En PROD debe existir y estar saludable
        assert 'cache' in data['services'], "Redis es OBLIGATORIO en Producción"
        redis_status = data['services']['cache']
        assert redis_status['healthy'] is True, f"Redis no está saludable: {redis_status.get('error')}"
    else:
        # En DEV validamos solo si está presente
        if 'cache' in data['services']:
             assert data['services']['cache']['healthy'] is True, "Redis aparece configurado pero con error"
        else:
            pytest.skip("⚠️ Redis no está activo en DEV (esperado)")
