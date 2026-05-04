FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# PORT env var is respected for cloud platforms (Railway, Render, Cloud Run, Heroku).
# Falls back to 8000 for plain Docker usage.
CMD python -m uvicorn run_local:app --host 0.0.0.0 --port ${PORT:-8000}
