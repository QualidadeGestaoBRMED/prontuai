#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/back-end"

cd "$BACKEND_DIR"

if docker compose version >/dev/null 2>&1; then
  docker compose up -d
else
  sudo docker compose up -d
fi

if docker compose version >/dev/null 2>&1; then
  docker compose ps
else
  sudo docker compose ps
fi
