#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
git pull --ff-only
docker compose up -d --build
docker compose ps
