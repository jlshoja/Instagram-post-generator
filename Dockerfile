FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    TZ=Asia/Tehran

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite (persisted) and temp media live on volumes; logs too
VOLUME ["/app/data", "/app/.media", "/app/logs"]

CMD ["python", "-m", "bazarkif.cli", "daemon"]