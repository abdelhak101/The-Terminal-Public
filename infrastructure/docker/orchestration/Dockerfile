FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Dagster and extras
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set $DAGSTER_HOME and copy configuration
ENV DAGSTER_HOME=/opt/dagster/dagster_home/
RUN mkdir -p $DAGSTER_HOME
WORKDIR /opt/dagster/app

# The compose file will mount dagster.yaml
