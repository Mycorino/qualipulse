FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2, healthcheck, and audio transcoding (ffmpeg
# converts participant webm/opus recordings to MP3 for cross-browser playback).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    ffmpeg \
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
