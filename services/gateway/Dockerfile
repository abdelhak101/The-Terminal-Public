FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules and adapters
COPY shared/ /app/shared/
COPY adapters/ /app/adapters/
# Copy service source
COPY services/gateway/src/ /app/src/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "src/main.py"]
