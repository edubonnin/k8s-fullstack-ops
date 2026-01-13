# k8s-fullstack-ops
Deployment of a full-stack app on Kubernetes with PostgreSQL & Redis, featuring a CI/CD pipeline (GitHub Actions), Canary/Blue-Green deployment strategies, and Prometheus/Grafana monitoring.

## 🚀 Guía Rápida (Makefile)

Este proyecto utiliza un `Makefile` para automatizar todo el ciclo de vida en **k3d**, separando los entornos en dos clusters físicos distintos.

### 1. Inicialización
Crear los clusters de Desarrollo y Producción:
```bash
make clusters
```

### 2. Entorno de Desarrollo (Dev)
Despliegue en dev para pruebas rápidas (**Sin Redis**).
```bash
make deploy-dev
make tunnel-dev   # -> Abre http://localhost:9001
```

### 3. Entorno de Producción (Prod)
Despliegue en prod completo (**Con Redis** y base de datos persistente).
```bash
make deploy-prod
make tunnel-prod  # -> Abre http://localhost:9002
```

### 4. Utilidades
Comandos extra para gestión de recursos.
```bash
make clean        # Borrar todo (clusters y datos)
```
