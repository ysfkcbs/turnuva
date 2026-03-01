FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY render_start.sh /app/render_start.sh
RUN chmod +x /app/render_start.sh
CMD ["sh", "/app/render_start.sh"]