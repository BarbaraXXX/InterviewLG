#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env not found at $ENV_FILE"
    echo "Copy .env.example to .env and fill in your configuration."
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

APP_UID="${APP_UID:-10001}"
APP_GID="${APP_GID:-10001}"

if [ -z "${SSL_DOMAIN:-}" ]; then
    echo "Error: SSL_DOMAIN not set in .env"
    exit 1
fi

if [ -z "${AUTH_SECRET_KEY:-}" ] || [ "$AUTH_SECRET_KEY" = "change-me-in-production" ]; then
    echo "Error: AUTH_SECRET_KEY must be changed from default in .env"
    exit 1
fi

if [ -z "${AUTH_INVITE_CODE:-}" ]; then
    echo "Error: AUTH_INVITE_CODE must be set in .env (comma-separated invite codes)"
    exit 1
fi

if [ -z "${VECTORDB_ADMIN_TOKEN:-}" ]; then
    echo "Error: VECTORDB_ADMIN_TOKEN must be set in .env"
    exit 1
fi

if [ -z "${EMBEDDING_PROVIDER:-}" ]; then
    echo "Error: EMBEDDING_PROVIDER must be set in .env and match the deployed VectorDB index"
    exit 1
fi

case "${EMBEDDING_PROVIDER,,}" in
    deterministic|fake|local)
        ;;
    *)
        if [ -z "${EMBEDDING_API_KEY:-}" ] || [ "$EMBEDDING_API_KEY" = "your-dashscope-key" ]; then
            echo "Error: EMBEDDING_API_KEY must be configured for provider $EMBEDDING_PROVIDER"
            exit 1
        fi
        ;;
esac

NGINX_CONF="$SCRIPT_DIR/nginx/nginx.conf"
NGINX_RESOLVED="$SCRIPT_DIR/nginx/nginx.resolved.conf"

# 确保证书目录存在（bind mount 需要宿主目录已存在）
mkdir -p "$PROJECT_DIR/data/certbot/www" "$PROJECT_DIR/data/certbot/conf" "$PROJECT_DIR/../data/vectordb"
mkdir -p "$PROJECT_DIR/../data/vectordb/profiles" "$PROJECT_DIR/../data/vectordb/experiences"
chown -R "$APP_UID:$APP_GID" "$PROJECT_DIR/../data"

envsubst '$SSL_DOMAIN' < "$NGINX_CONF" > "$NGINX_RESOLVED"

CERT_DIR="$PROJECT_DIR/data/certbot/conf/live/$SSL_DOMAIN"
FIRST_TIME=false

if [ ! -d "$CERT_DIR" ]; then
    FIRST_TIME=true
    echo "=== First-time setup: obtaining SSL certificate ==="
    echo "Domain: $SSL_DOMAIN"
    echo ""

    # Use HTTP-only config first to get cert
    cat > "$NGINX_RESOLVED" << 'NGINX_HTTP'
events {
    worker_connections 1024;
}

http {
    resolver 127.0.0.11 valid=10s ipv6=off;

    server {
        listen 80;
        server_name _;
        set $app_upstream app:8000;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            proxy_pass http://$app_upstream;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
NGINX_HTTP

    cd "$SCRIPT_DIR"
    docker compose build vectordb
    docker compose build app
    docker compose up -d vectordb app nginx
    sleep 5

    docker compose run --rm certbot certbot certonly \
        --webroot \
        --webroot-path /var/www/certbot \
        -d "$SSL_DOMAIN" \
        --email "${SSL_EMAIL:-admin@${SSL_DOMAIN}}" \
        --agree-tos \
        --no-eff-email

    # Now regenerate the full HTTPS config
    envsubst '$SSL_DOMAIN' < "$NGINX_CONF" > "$NGINX_RESOLVED"
fi

echo "=== Starting services ==="
cd "$SCRIPT_DIR"
docker compose build vectordb
docker compose build app
docker compose up -d

echo ""
echo "=== Done ==="
echo "App is running at https://$SSL_DOMAIN"
echo ""
echo "Useful commands:"
echo "  docker compose -f $SCRIPT_DIR/docker-compose.yml logs -f app    # View logs"
echo "  docker compose -f $SCRIPT_DIR/docker-compose.yml down           # Stop"
echo "  bash $SCRIPT_DIR/deploy.sh                                      # Rebuild & restart"
