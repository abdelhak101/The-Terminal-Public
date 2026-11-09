FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/streaming_analytics/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared/ /app/shared/
# Copy service source
COPY services/streaming_analytics/src/ /app/src/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV REDIS_HOST=redis

# Bytewax uses its own CLI to run flows
CMD ["python", "-m", "bytewax.run", "src.streaming_flow:flow"]
