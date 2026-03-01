FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render $PORT verir, gunicorn o portta dinlemeli
CMD ["sh", "-c", "flask --app 'app:create_app()' db upgrade && python -c \"from app import create_app; app=create_app(); from seed import run_seed; from models import db;  \nwith app.app_context(): run_seed()\" && gunicorn -w 1 -b 0.0.0.0:${PORT:-5000} 'app:create_app()'"]