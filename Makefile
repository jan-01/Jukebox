.PHONY: install install-dev lint css-build css-watch dev db stop \
        up down minikube-start pull-image generate-certs create-namespace enable-ingress \
        load-image apply-secrets apply-manifests wait-healthy port-forward k8s-status k8s-logs

IMAGE := ghcr.io/jukebox-final/jukeboxischmoxi:latest

# Einmalig: Virtualenv + Abhängigkeiten installieren
install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r backend/requirements.txt
	npm install
	@[ -f .env ] || cp .env.example .env
	@echo ""
	@echo "Fertig. CSS bauen mit: make css-build  |  Starten mit: make dev"

# CSS kompilieren (einmalig, minifiziert)
css-build:
	npm run css:build

# CSS im Watch-Modus (während der Entwicklung)
css-watch:
	npm run css:watch

# Dev-Abhängigkeiten installieren (Linting, Type-Checking)
install-dev:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

# Linting + Type-Checking
lint:
	.venv/bin/ruff check backend/
	.venv/bin/mypy backend/app.py

# Datenbank + Backend + CSS-Watcher starten (alles in einem)
dev: css-build
	docker-compose up -d db
	@echo "Warte auf Postgres..."
	@until docker exec jukebox_db pg_isready -U jukebox > /dev/null 2>&1; do sleep 1; done
	@echo "Postgres bereit."
	@npm run css:watch & CSS_PID=$$!; \
	trap "kill $$CSS_PID 2>/dev/null" EXIT INT TERM; \
	.venv/bin/python backend/app.py

# Nur Datenbank stoppen
stop:
	docker-compose down

# ===========================================================================
# Kubernetes / Minikube targets
# ===========================================================================

# Pull the Docker image from the registry
pull-image:
	docker pull $(IMAGE)

# Full automated deployment — runs all steps in order
up: minikube-start pull-image generate-certs create-namespace enable-ingress load-image apply-secrets apply-manifests wait-healthy port-forward
	@echo ""
	@echo "=== Ready ==="
	@echo "App : http://localhost:8080"

# Start port-forwarding in the background (idempotent — skips if already running)
port-forward:
	@if ss -tlnp 2>/dev/null | grep -q ':8080 '; then \
		echo "Port forwarding already active on localhost:8080."; \
	else \
		echo "Starting port forwarding on localhost:8080..."; \
		nohup kubectl port-forward -n jukebox service/jukebox-service 8080:80 > /tmp/kubectl-pf.log 2>&1 & \
		sleep 2; \
		if ss -tlnp 2>/dev/null | grep -q ':8080 '; then \
			echo "Port forwarding started — http://localhost:8080"; \
		else \
			echo "ERROR: Port forwarding failed. Check /tmp/kubectl-pf.log"; \
			cat /tmp/kubectl-pf.log; \
		fi \
	fi

# Start Minikube if it is not already running
minikube-start:
	@if ! minikube status --format='{{.Host}}' 2>/dev/null | grep -q Running; then \
		echo "Starting Minikube..."; \
		minikube start --driver=docker --extra-config=apiserver.audit-log-path=""; \
	else \
		echo "Minikube already running."; \
	fi
	@echo "Waiting for Kubernetes API server..."
	@until kubectl cluster-info > /dev/null 2>&1; do sleep 2; done
	@echo "API server ready."

# Generate self-signed CA + leaf cert for jukebox.local (idempotent)
generate-certs:
	@mkdir -p infrastructure/certs
	@if [ ! -f infrastructure/certs/rootCA.pem ]; then \
		echo "Generating CA..."; \
		openssl genrsa -out infrastructure/certs/rootCA.key 4096; \
		openssl req -x509 -new -nodes \
			-key infrastructure/certs/rootCA.key \
			-sha256 -days 825 \
			-subj "/CN=Jukebox Local CA" \
			-out infrastructure/certs/rootCA.pem; \
	else \
		echo "CA already exists, skipping."; \
	fi
	@if [ ! -f infrastructure/certs/tls.crt ]; then \
		echo "Generating leaf certificate..."; \
		openssl genrsa -out infrastructure/certs/tls.key 2048; \
		printf '[req]\ndistinguished_name=req\n[SAN]\nsubjectAltName=DNS:jukebox.local\n' \
			> infrastructure/certs/san.cnf; \
		openssl req -new \
			-key infrastructure/certs/tls.key \
			-subj "/CN=jukebox.local" \
			-reqexts SAN \
			-config infrastructure/certs/san.cnf \
			-out infrastructure/certs/tls.csr; \
		openssl x509 -req -in infrastructure/certs/tls.csr \
			-CA infrastructure/certs/rootCA.pem \
			-CAkey infrastructure/certs/rootCA.key \
			-CAcreateserial \
			-days 825 -sha256 \
			-extfile infrastructure/certs/san.cnf \
			-extensions SAN \
			-out infrastructure/certs/tls.crt; \
	else \
		echo "Leaf cert already exists, skipping."; \
	fi

# Apply namespace manifest if the namespace does not exist yet
create-namespace:
	@if ! kubectl get namespace jukebox > /dev/null 2>&1; then \
		echo "Creating namespace jukebox..."; \
		kubectl apply -f infrastructure/k8s/namespace.yaml; \
	else \
		echo "Namespace jukebox already exists."; \
	fi

# Enable the ingress-nginx addon and wait for its controller pod to become ready
enable-ingress:
	@minikube addons enable ingress
	@echo "Waiting for ingress-nginx controller..."
	@kubectl rollout status deployment/ingress-nginx-controller \
		-n ingress-nginx --timeout=120s

# verify image
verify-image:
	@echo "Verifying image signature..."
	cosign verify --key cosign.pub $(IMAGE)
	@echo "Signature OK."

# Load the pulled image into Minikube
load-image: verify-image
	@echo "Loading $(IMAGE) into Minikube..."
	minikube image load $(IMAGE)

# Generate .secrets with secure random credentials on first run (gitignored via *.secrets).
# Delete .secrets to rotate credentials.
.secrets:
	@echo "Generating .secrets with secure random credentials..."
	@printf 'POSTGRES_DB=jukebox\nPOSTGRES_USER=jukebox\nPOSTGRES_PASSWORD=%s\n' \
		"$$(openssl rand -base64 32)" > .secrets
	@echo ".secrets created (gitignored). Delete it to regenerate credentials."

# Apply secrets — reads credentials from .secrets; env vars take precedence if explicitly set.
apply-secrets: .secrets
	@_db="$${POSTGRES_DB:-$$(grep ^POSTGRES_DB= .secrets | cut -d= -f2-)}"; \
	_user="$${POSTGRES_USER:-$$(grep ^POSTGRES_USER= .secrets | cut -d= -f2-)}"; \
	_pass="$${POSTGRES_PASSWORD:-$$(grep ^POSTGRES_PASSWORD= .secrets | cut -d= -f2-)}"; \
	kubectl create secret generic postgres-secret \
		--namespace jukebox \
		--from-literal=POSTGRES_DB="$$_db" \
		--from-literal=POSTGRES_USER="$$_user" \
		--from-literal=POSTGRES_PASSWORD="$$_pass" \
		--from-literal=DB_HOST="postgres-service" \
		--dry-run=client -o yaml | kubectl apply -f -
	@kubectl create secret generic app-secret \
		--namespace jukebox \
		--from-literal=SECRET_KEY="$$(openssl rand -base64 32)" \
		--dry-run=client -o yaml | kubectl apply -f -
	@kubectl create secret tls jukebox-tls \
		--namespace jukebox \
		--cert=infrastructure/certs/tls.crt \
		--key=infrastructure/certs/tls.key \
		--dry-run=client -o yaml | kubectl apply -f -

# Apply all remaining manifests in dependency order
apply-manifests:
	kubectl apply -f infrastructure/k8s/serviceaccount.yaml
	kubectl apply -f infrastructure/k8s/postgres-pvc.yaml
	kubectl apply -f infrastructure/k8s/postgres-deployment.yaml
	kubectl apply -f infrastructure/k8s/postgres-service.yaml
	kubectl apply -f infrastructure/k8s/networkpolicy.yaml
	kubectl apply -f infrastructure/k8s/deployment.yaml
	kubectl apply -f infrastructure/k8s/service.yaml
	kubectl apply -f infrastructure/k8s/ingress.yaml

# Wait for both deployments to roll out, then probe the app
wait-healthy:
	@echo "Waiting for postgres rollout..."
	@kubectl rollout status deployment/postgres -n jukebox --timeout=120s
	@echo "Waiting for jukebox rollout..."
	@kubectl rollout status deployment/jukebox -n jukebox --timeout=120s
	@echo "Probing app from inside the cluster..."
	@kubectl run probe --image=curlimages/curl:8.7.1 --restart=Never --rm -i \
		--namespace jukebox \
		-- curl -sf http://jukebox-service/ > /dev/null && echo "App responded OK."

# Tear down the entire Minikube cluster
down:
	minikube delete

# Show all resources in the jukebox namespace
k8s-status:
	kubectl get all,ingress,secret,networkpolicy -n jukebox

# Tail logs for the jukebox app pod
k8s-logs:
	kubectl logs -n jukebox -l app=jukebox --tail=100 -f
