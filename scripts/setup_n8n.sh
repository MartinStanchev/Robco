#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_ROOT/server"

echo "=== Robco n8n Server Setup ==="

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed."
    echo "Install Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check for Docker Compose (v2 plugin)
if ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose plugin is not installed."
    echo "Install it: https://docs.docker.com/compose/install/"
    exit 1
fi

# Check for .env file
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "No .env file found. Creating from .env.example..."
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    echo ">>> Please edit $PROJECT_ROOT/.env with your API keys before continuing."
    exit 1
fi

# Source .env so docker compose can use the variables
set -a
source "$PROJECT_ROOT/.env"
set +a

# Create personality-cache directory if it doesn't exist
mkdir -p "$SERVER_DIR/personality-cache"

# Start services
echo "Starting n8n + PostgreSQL..."
docker compose -f "$SERVER_DIR/docker-compose.yml" --env-file "$PROJECT_ROOT/.env" up -d

# Wait for n8n to be healthy
echo "Waiting for n8n to become healthy..."
MAX_WAIT=90
WAITED=0
until docker compose -f "$SERVER_DIR/docker-compose.yml" ps n8n | grep -q "healthy"; do
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "Error: n8n did not become healthy within ${MAX_WAIT}s"
        echo "Check logs: docker compose -f $SERVER_DIR/docker-compose.yml logs n8n"
        exit 1
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "  ...waiting (${WAITED}s)"
done

N8N_PORT="${N8N_PORT:-5678}"
echo ""
echo "=== n8n is running ==="
echo "URL: http://localhost:${N8N_PORT}"
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:${N8N_PORT} and complete the n8n setup wizard"
echo "  2. Import the workflow from server/workflows/voice-pipeline.json"
echo "  3. Activate the workflow"
