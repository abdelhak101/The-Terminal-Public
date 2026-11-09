FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/streaming-monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/streaming-monitor/src/ /app/src/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "src/main.py"]
