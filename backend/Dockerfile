FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 and healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080

EXPOSE ${PORT}

# Run migrations then start server
# Cloud Run sends SIGTERM for graceful shutdown; uvicorn handles it
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
