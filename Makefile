# Makefile: Gestión de K8s multi-cluster (Dev/Pro)
# Variables Globales
DEV=k3d-dev-cluster
PRO=k3d-prod-cluster
IMG ?= app-image:v1

.PHONY: clusters clean switch-dev switch-pro import deploy-dev deploy-pro \
        grafana-dev grafana-pro prometheus-dev prometheus-pro \
        test-dev test-pro stop-db-dev start-db-dev stop-db-pro start-db-pro \
        stop-minio-dev start-minio-dev stop-minio-pro start-minio-pro \
        trigger-alert-dev resolve-alert-dev trigger-alert-pro resolve-alert-pro

# ==============================================================================
# 🛠️ GESTIÓN DE CLUSTERS (Setup Inicial)
# ==============================================================================

clusters: ## 1. Crea ambos clusters (dev:8081, pro:8080)
	k3d cluster create dev-cluster --port "8081:80@loadbalancer" --servers 1 --agents 0 --wait
	k3d cluster create prod-cluster --port "8080:80@loadbalancer" --servers 1 --agents 1 --wait
	@echo "✅ Clusters listos."

clean: ## Borra todo (Clusters y Datos)
	k3d cluster delete dev-cluster prod-cluster

switch-dev: ## 🔄 Cambia contexto local a DEV
	kubectl config use-context $(DEV)
	kubectl config set-context --current --namespace=dev
	@echo "🔄 Estás en DEV"

switch-pro: ## 🔄 Cambia contexto local a PRO
	kubectl config use-context $(PRO)
	kubectl config set-context --current --namespace=pro
	@echo "🔄 Estás en PRO"

current-context: ## Muestra contexto actual
	kubectl config current-context

import: ## Construye e importa imagen Docker a k3d
	docker build -t $(IMG) ./app
	k3d image import $(IMG) -c dev-cluster -c prod-cluster

# ==============================================================================
# 🚀 DESPLIEGUES (APP + INFRA)
# ==============================================================================

deploy-dev: import ## 2. Despliega DEV (sin Redis, 2 réplicas)
	kubectl config use-context $(DEV)
	# Namespace y Config
	kubectl create ns dev --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n dev -f k8s/environments/dev/config.yaml -f k8s/environments/dev/secrets.yaml
	# Plataforma Base
	kubectl apply -n dev -f k8s/base/platform/postgres.yaml -f k8s/base/platform/db-init.yaml -f k8s/base/platform/minio.yaml -f k8s/base/platform/minio-init.yaml
	# App y Red
	kubectl apply -n dev -f k8s/base/app/deployment.yaml -f k8s/base/app/service.yaml -f k8s/environments/dev/ingress.yaml
	kubectl set image deployment/app-deployment app-container=$(IMG) -n dev
	kubectl scale deployment app-deployment --replicas=2 -n dev
	# Monitorización
	$(MAKE) deploy-monitoring-dev
	@echo "✅ DEV listo. 🌐 URL: http://app.dev.localhost:8081"

deploy-pro: import ## 2. Despliega PRO (con Redis, 4 réplicas)
	kubectl config use-context $(PRO)
	# Namespace y Config
	kubectl create ns pro --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n pro -f k8s/environments/pro/config.yaml -f k8s/environments/pro/secrets.yaml
	# Plataforma Base
	kubectl apply -n pro -f k8s/base/platform/postgres.yaml -f k8s/base/platform/db-init.yaml -f k8s/base/platform/redis.yaml -f k8s/base/platform/minio.yaml -f k8s/base/platform/minio-init.yaml
	# App y Red
	kubectl apply -n pro -f k8s/base/app/deployment.yaml -f k8s/base/app/service.yaml -f k8s/environments/pro/ingress.yaml
	kubectl set image deployment/app-deployment app-container=$(IMG) -n pro
	kubectl scale deployment app-deployment --replicas=4 -n pro
	# Monitorización
	$(MAKE) deploy-monitoring-pro
	@echo "✅ PRO listo. 🌐 URL: http://app.pro.localhost:8080"

# --- Subtareas de Monitorización ---

deploy-monitoring-dev:
	kubectl config use-context $(DEV)
	kubectl create ns monitoring --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s/environments/dev/monitoring/secrets.yaml
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
		--namespace monitoring \
		--set grafana.admin.existingSecret=grafana-admin-credentials \
		--set grafana.admin.userKey=admin-user \
		--set grafana.admin.passwordKey=admin-password
	kubectl apply -f k8s/environments/dev/monitoring/service-monitor.yaml
	kubectl apply -f k8s/environments/dev/monitoring/alert-rules.yaml

deploy-monitoring-pro:
	kubectl config use-context $(PRO)
	kubectl create ns monitoring --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s/environments/pro/monitoring/secrets.yaml
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
		--namespace monitoring \
		--set grafana.admin.existingSecret=grafana-admin-credentials \
		--set grafana.admin.userKey=admin-user \
		--set grafana.admin.passwordKey=admin-password
	kubectl apply -f k8s/environments/pro/monitoring/service-monitor.yaml
	kubectl apply -f k8s/environments/pro/monitoring/alert-rules.yaml

# ==============================================================================
# 🔍 ACCEOS Y LOGS
# ==============================================================================

logs-dev: ## Logs de la App en DEV
	kubectl logs -n dev -l app=app --context $(DEV)

logs-pro: ## Logs de la App en PRO
	kubectl logs -n pro -l app=app --context $(PRO)

grafana-dev: ## 📊 Acceso Grafana DEV (http://localhost:3001)
	@echo "📊 Abriendo Grafana DEV (User: admin)..."
	kubectl --context $(DEV) -n monitoring port-forward svc/kube-prometheus-stack-grafana 3001:80

grafana-pro: ## 📊 Acceso Grafana PRO (http://localhost:3000)
	@echo "📊 Abriendo Grafana PRO (User: admin)..."
	kubectl --context $(PRO) -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80

prometheus-dev: ## 📈 Acceso Prometheus DEV (http://localhost:9091)
	kubectl --context $(DEV) -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9091:9090

prometheus-pro: ## 📈 Acceso Prometheus PRO (http://localhost:9090)
	kubectl --context $(PRO) -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090

tunnel-dev:; kubectl port-forward --context $(DEV) -n dev svc/app-service 9001:80
tunnel-pro:; kubectl port-forward --context $(PRO) -n pro svc/app-service 9002:80

# ==============================================================================
# 🧪 TESTS INTEGRACIÓN
# ==============================================================================

test-dev: ## Ejecuta tests contra entorno DEV
	@echo "🧪 Testeando DEV..."
	pip install -q -r tests/requirements.txt
	TEST_URL=http://app.dev.localhost:8081 pytest tests/ -v

test-pro: ## Ejecuta tests contra entorno PRO
	@echo "🧪 Testeando PRO..."
	pip install -q -r tests/requirements.txt
	TEST_URL=http://app.pro.localhost:8080 pytest tests/ -v

# ==============================================================================
# 💥 CHAOS ENGINEERING (Simulación de Fallos)
# ==============================================================================

# --- Database Chaos ---
stop-db-dev: ## 🛑 Detiene BD en DEV
	kubectl scale deployment postgres-deployment --replicas=0 -n dev --context $(DEV)

start-db-dev: ## ▶️ Inicia BD en DEV
	kubectl scale deployment postgres-deployment --replicas=1 -n dev --context $(DEV)

stop-db-pro: ## 🛑 Detiene BD en PRO
	kubectl scale deployment postgres-deployment --replicas=0 -n pro --context $(PRO)

start-db-pro: ## ▶️ Inicia BD en PRO
	kubectl scale deployment postgres-deployment --replicas=1 -n pro --context $(PRO)

# --- MinIO Chaos ---
stop-minio-dev: ## 🛑 Detiene MinIO en DEV (Favicon error)
	kubectl scale deployment minio-deployment --replicas=0 -n dev --context $(DEV)

start-minio-dev: ## ▶️ Inicia MinIO en DEV
	kubectl scale deployment minio-deployment --replicas=1 -n dev --context $(DEV)

stop-minio-pro: ## 🛑 Detiene MinIO en PRO
	kubectl scale deployment minio-deployment --replicas=0 -n pro --context $(PRO)

start-minio-pro: ## ▶️ Inicia MinIO en PRO
	kubectl scale deployment minio-deployment --replicas=1 -n pro --context $(PRO)

# --- App Scalability Chaos ---
trigger-alert-dev: ## ⚠️  Provoca alerta (1 Réplica) en DEV
	kubectl scale deployment app-deployment --replicas=1 -n dev --context $(DEV)

resolve-alert-dev: ## ✅ Resuelve alerta (2 Réplicas) en DEV
	kubectl scale deployment app-deployment --replicas=2 -n dev --context $(DEV)

trigger-alert-pro: ## ⚠️  Provoca alerta (1 Réplica) en PRO
	kubectl scale deployment app-deployment --replicas=1 -n pro --context $(PRO)

resolve-alert-pro: ## ✅ Resuelve alerta (4 Réplicas) en PRO
	kubectl scale deployment app-deployment --replicas=4 -n pro --context $(PRO)
