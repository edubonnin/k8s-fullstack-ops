# K8s Fullstack Ops 🚀

Este proyecto implementa una arquitectura completa de despliegue de una aplicación Fullstack en Kubernetes (usando **k3d**), simulando un ciclo de vida real de DevOps con entornos de **Desarrollo (Dev)** y **Producción (Pro)**, Integración Continua (CI), Monitorización avanzada y pruebas automatizadas.

---

## 🏗️ Partes del Proyecto y Arquitectura

El sistema simula dos clusters físicos independientes aislando cargas de trabajo y datos.

### Componentes Principales
*   **Aplicación**: Python Flask API con soporte de métricas (Prometheus Client).
*   **Datos**:
    *   **PostgreSQL**: Base de datos relacional principal.
    *   **Redis** (Solo PRO): Caché para optimización de endpoints.
    *   **MinIO**: Almacenamiento de objetos S3-compatible.
*   **Plataforma**: 
    *   **K3d**: Orquestador Kubernetes ligero (Docker-in-Docker).
    *   **Ingress**: Traefik (nativo de K3d) para enrutamiento HTTP.
*   **Observabilidad**:
    *   **Prometheus Operator**: Recolección de métricas.
    *   **Grafana**: Visualización de dashboards.
    *   **AlertManager**: Reglas de alerta (ej. Baja disponibilidad).

### Diagrama de Arquitectura

```mermaid
graph TD
    User((Usuario)) --> Ingress
    
    subgraph "K3d Cluster PRO"
        Ingress[Traefik Ingress]
        
        subgraph "Monitoring Stack"
            Prom[Prometheus]
            Graf[Grafana]
        end
        
        subgraph "App Layer"
            App1[Pod App v1]
            App2[Pod App v2]
            Service[ClusterIP Service]
        end
        
        subgraph "Data Layer"
            PG[(PostgreSQL)]
            Redis[(Redis Cache)]
            Minio[(MinIO S3)]
        end
        
        Ingress --> Service
        Service --> App1 & App2
        App1 --> PG & Redis & Minio
        
        Prom -- "Scrapes /metrics" --> Service
    end
```

---

## 🛠️ Guía de Setup y Pruebas

### Prerequisitos
*   Docker
*   K3d
*   Kubectl & Helm
*   Make
*   Python 3.10+ (para correr tests locales)

### Pasos de Instalación

1.  **Levantar Infraestructura Virtual**:
    ```bash
    make clusters
    # Crea 2 clusters: dev-cluster (puerto 8081) y prod-cluster (puerto 8080)
    ```

    > ⚠️ **Nota DNS**: Para que las URLs funcionen, asegúrate de añadir las siguientes entradas a tu fichero `/etc/hosts`:
    > ```text
    > 127.0.0.1 app.dev.localhost
    > 127.0.0.1 app.pro.localhost
    > ```

2.  **Desplegar Entorno DEV**:
    ```bash
    make deploy-dev
    # Despliega App + BD + MinIO + Monitorización  (HA: 2 réplicas)
    ```
    *   🌐 **URL**: `http://app.dev.localhost:8081`

3.  **Desplegar Entorno PRO**:
    ```bash
    make deploy-pro
    # Despliega App + BD + Redis + MinIO + Monitorización (HA: 4 réplicas)
    ```
    *   🌐 **URL**: `http://app.pro.localhost:8080`

Para probar la persistencia o el cambio entre entornos, usa los comandos de contexto:
```bash
make switch-dev  # Cambia tu kubectl a DEV
make switch-pro  # Cambia tu kubectl a PRO
```

---

## 🧪 Tests Utilizados

El proyecto incluye una suite de **tests de integración** (ubicados en `tests/`) que validan la salud de la aplicación desde fuera del cluster, asegurando que todos los componentes (BD, Redis, API) responden correctamente.

### Ejecución
```bash
make test-dev  # Lanza pytest contra http://app.dev.localhost:8081
make test-pro  # Lanza pytest contra http://app.pro.localhost:8080
```

### Output Esperado
```text
🧪 Ejecutando tests contra entorno PRO...
============================= test session starts ==============================
platform darwin -- Python 3.10.12, pytest-7.4.0, pluggy-1.2.0
rootdir: /k8s-fullstack-ops
collected 4 items

tests/test_integration.py::test_health_check PASSED                    [ 25%]
tests/test_integration.py::test_database_connection PASSED             [ 50%]
tests/test_integration.py::test_redis_cache_hit PASSED                 [ 75%]
tests/test_integration.py::test_metrics_endpoint PASSED                [100%]

============================== 4 passed in 1.42s ===============================
```

---

## ️ Comandos Operativos (Entorno Producción)

Aquí se listan los comandos principales enfocados en **Producción** (existen equivalentes para Dev terminados en `-dev`).

### 🛠️ Gestión y Accesos
| Comando | Descripción |
| :--- | :--- |
| `make switch-pro` | Cambia tu contexto de kubectl a PRO. |
| `make logs-pro` | Muestra logs de la aplicación en tiempo real. |
| `make tunnel-pro` | Abre un túnel directo al servicio (Puerto 9002). |

### 📊 Observabilidad
| Comando | Descripción |
| :--- | :--- |
| `make grafana-pro` | Abre Grafana (User: `admin`). |
| `make prometheus-pro` | Abre Prometheus para consultar métricas. |

### 🧪 Tests & Chaos Engineering (Simulacros)
| Comando | Descripción |
| :--- | :--- |
| `make test-pro` | Ejecuta tests de integración contra el entorno. |
| `make stop-db-pro` | 🛑 Detiene la Base de Datos (Simula caída). |
| `make start-db-pro` | ▶️ Recupera la Base de Datos. |
| `make stop-minio-pro` | 🛑 Detiene MinIO (Comprueba fallo de assets). |
| `make start-minio-pro` | ▶️ Recupera MinIO. |
| `make trigger-alert-pro` | ⚠️ Provoca alerta de "Baja Disponibilidad" (1 réplica). |
| `make resolve-alert-pro` | ✅ Resuelve la alerta (Vuelve a 4 réplicas). |
