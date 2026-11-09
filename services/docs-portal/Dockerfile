# Use Python for both building docs and running the portal
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY services/docs-portal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy documentation content and configuration
COPY docs/ /app/docs/
COPY mkdocs.yml /app/mkdocs.yml

# Build documentation site
RUN mkdocs build -d site

# Copy shared modules and service source
COPY shared/ /app/shared/
COPY adapters/ /app/adapters/
COPY services/docs-portal/src/ /app/src/

ENV PYTHONPATH=/app
ENV DOCS_ROOT=/app/docs
ENV STATIC_DIR=/app/site
ENV GATEWAY_URL=http://gateway:8000
ENV PORT=23002

CMD ["python", "src/main.py"]
