FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDITOR_HOST=0.0.0.0 \
    EDITOR_PORT=5057 \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8765 \
    PYTHONPATH=/app/src:/app/scripts \
    CV_DATA_ROOT=/data \
    SNIPPETS_DB=/data/snippets.db \
    RESUME_IMPORTS_DIR=/data/imports

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-liberation \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Seed sources and application code for image-only runs. Compose also
# bind-mounts the repo at /app during local development.
COPY src /app/src
COPY scripts /app/scripts
COPY cv /app/cv
COPY content /app/content
COPY assets /app/assets
COPY README.md VERSION /app/

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /data/assets/images /data/imports/staging \
        /data/cv/variants /data/cv/current

VOLUME ["/data"]

EXPOSE 5057 8765

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "scripts/serve-editor.py"]
