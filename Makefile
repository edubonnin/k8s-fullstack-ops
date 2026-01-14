# Makefile: Gestión de K8s multi-cluster (Dev/Prod)
DEV=k3d-dev-cluster
PROD=k3d-prod-cluster
IMG=app-image:v1

.PHONY: clusters clean stop-dev start-dev deploy-dev deploy-prod tunnel-dev tunnel-prod

clusters: ## 1. Crea ambos clusters
	k3d cluster create dev-cluster --port "8081:80@loadbalancer" --servers 1 --agents 0 --wait
	k3d cluster create prod-cluster --port "8080:80@loadbalancer" --servers 1 --agents 1 --wait
	@echo "✅ Clusters listos."

clean: ## Borra todo
	k3d cluster delete dev-cluster prod-cluster

import: ## Construye e importa imagen
	docker build -t $(IMG) ./app
	k3d image import $(IMG) -c dev-cluster -c prod-cluster

deploy-dev: import ## 2. Despliega DEV (sin Redis)
	kubectl config use-context $(DEV)
	kubectl create ns dev --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n dev -f k8s/infra/config-dev.yaml -f k8s/infra/secrets.yaml
	kubectl apply -n dev -f k8s/infra/postgres.yaml -f k8s/infra/init-db.yaml -f k8s/infra/minio.yaml -f k8s/infra/minio-init.yaml
	kubectl apply -n dev -f k8s/app/deployment.yaml -f k8s/app/service.yaml -f k8s/app/ingress.yaml
	# Escalar a 2 réplicas para HA en Dev
	kubectl scale deployment app-deployment --replicas=2 -n dev
	@echo "✅ DEV listo (2 Replicas). Accede vía http://localhost:8081"

deploy-prod: import ## 2. Despliega PROD (con Redis)
	kubectl config use-context $(PROD)
	kubectl create ns pro --dry-run=client -o yaml | kubectl apply -f -
	kubectl create ns monitoring --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n pro -f k8s/infra/config-prod.yaml -f k8s/infra/secrets.yaml
	kubectl apply -n pro -f k8s/infra/postgres.yaml -f k8s/infra/init-db.yaml -f k8s/infra/redis.yaml -f k8s/infra/minio.yaml -f k8s/infra/minio-init.yaml
	kubectl apply -n pro -f k8s/app/deployment.yaml -f k8s/app/service.yaml -f k8s/app/ingress.yaml
	# Escalar a 4 réplicas para HA en Prod
	kubectl scale deployment app-deployment --replicas=4 -n pro
	@echo "✅ PROD listo (4 Replicas). Accede vía http://localhost:8080"



logs-dev: ## Muestra logs del pod de la app en DEV
	kubectl logs -n dev -l app=app

logs-prod: ## Muestra logs del pod de la app en PROD
	kubectl logs -n pro -l app=app

tunnel-dev:; kubectl port-forward --context $(DEV) -n dev svc/app-service 9001:80
tunnel-prod:; kubectl port-forward --context $(PROD) -n pro svc/app-service 9002:80
