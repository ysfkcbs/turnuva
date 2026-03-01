#!/usr/bin/env sh
set -e

echo "[start] create tables (create_all)..."
python -c "from app import create_app; from models import db; app=create_app(); ctx=app.app_context(); ctx.push(); db.create_all(); print('[start] db.create_all OK')"

echo "[start] running migrations..."
flask --app "app:create_app()" db upgrade

echo "[start] seeding..."
python -c "from app import create_app; app=create_app(); ctx=app.app_context(); ctx.push(); from seed import run_seed; run_seed()"

echo "[start] starting gunicorn..."
exec gunicorn -w 1 -b 0.0.0.0:${PORT:-5000} "app:create_app()"