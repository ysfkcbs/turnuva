#!/usr/bin/env sh
set -e

echo "[start] running migrations..."
flask --app "app:create_app()" db upgrade

echo "[start] seeding..."
python -c "from app import create_app; app=create_app(); from seed import run_seed; \
from models import db; \
with app.app_context(): run_seed()"

echo "[start] starting gunicorn..."
exec gunicorn -w 1 -b 0.0.0.0:${PORT:-5000} "app:create_app()"