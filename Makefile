# Makefile: Gestión de K8s multi-cluster (Dev/Pro)
DEV=k3d-dev-cluster
PRO=k3d-prod-cluster
IMG=app-image:v1

.PHONY: clusters clean switch-dev switch-pro stop-dev start-dev deploy-dev deploy-pro tunnel-dev tunnel-pro

clusters: ## 1. Crea ambos clusters
	k3d cluster create dev-cluster --port "8081:80@loadbalancer" --servers 1 --agents 0 --wait
	k3d cluster create prod-cluster --port "8080:80@loadbalancer" --servers 1 --agents 1 --wait
	@echo "✅ Clusters listos."

clean: ## Borra todo
	k3d cluster delete dev-cluster prod-cluster

switch-dev: ## Cambia al contexto del cluster de desarrollo
	kubectl config use-context $(DEV)
	kubectl config set-context --current --namespace=dev
	@echo "🔄 Estás en DEV"

switch-pro: ## Cambia al contexto del cluster de producción
	kubectl config use-context $(PRO)
	kubectl config set-context --current --namespace=pro
	@echo "🔄 Estás en PRO"

import: ## Construye e importa imagen
	docker build -t $(IMG) ./app
	k3d image import $(IMG) -c dev-cluster -c prod-cluster

deploy-dev: import ## 2. Despliega DEV (sin Redis)
	kubectl config use-context $(DEV)
	kubectl create ns dev --dry-run=client -o yaml | kubectl apply -f -
	# Entorno
	kubectl apply -n dev -f k8s/environments/dev/config.yaml -f k8s/environments/dev/secrets.yaml
	# Plataforma Base
	kubectl apply -n dev -f k8s/base/platform/postgres.yaml -f k8s/base/platform/db-init.yaml -f k8s/base/platform/minio.yaml -f k8s/base/platform/minio-init.yaml
	# App Base + Ingress Específico
	kubectl apply -n dev -f k8s/base/app/deployment.yaml -f k8s/base/app/service.yaml -f k8s/environments/dev/ingress.yaml
	# Escalar a 2 réplicas para HA en Dev
	kubectl scale deployment app-deployment --replicas=2 -n dev
	@echo "✅ DEV listo (2 Replicas). Accede vía http://app.dev.localhost:8081"

deploy-pro: import ## 2. Despliega PRO (con Redis)
	kubectl config use-context $(PRO)
	kubectl create ns pro --dry-run=client -o yaml | kubectl apply -f -
	kubectl create ns monitoring --dry-run=client -o yaml | kubectl apply -f -
	# Entorno
	kubectl apply -n pro -f k8s/environments/pro/config.yaml -f k8s/environments/pro/secrets.yaml
	# Plataforma Base (incluye Redis)
	kubectl apply -n pro -f k8s/base/platform/postgres.yaml -f k8s/base/platform/db-init.yaml -f k8s/base/platform/redis.yaml -f k8s/base/platform/minio.yaml -f k8s/base/platform/minio-init.yaml
	# App Base + Ingress Específico
	kubectl apply -n pro -f k8s/base/app/deployment.yaml -f k8s/base/app/service.yaml -f k8s/environments/pro/ingress.yaml
	# Escalar a 4 réplicas para HA en Pro
	kubectl scale deployment app-deployment --replicas=4 -n pro
	@echo "✅ PRO listo (4 Replicas). Accede vía http://app.pro.localhost:8080"



logs-dev: ## Muestra logs del pod de la app en DEV
	kubectl logs -n dev -l app=app

logs-pro: ## Muestra logs del pod de la app en PRO
	kubectl logs -n pro -l app=app

tunnel-dev:; kubectl port-forward --context $(DEV) -n dev svc/app-service 9001:80
tunnel-pro:; kubectl port-forward --context $(PRO) -n pro svc/app-service 9002:80

test-dev: ## Ejecuta tests contra DEV
	@echo "🧪 Ejecutando tests contra entorno DEV..."
	pip install -q -r tests/requirements.txt
	TEST_URL=http://app.dev.localhost:8081 pytest tests/ -v

test-pro: ## Ejecuta tests contra PRO
	@echo "🧪 Ejecutando tests contra entorno PRO..."
	pip install -q -r tests/requirements.txt
	TEST_URL=http://app.pro.localhost:8080 pytest tests/ -v
