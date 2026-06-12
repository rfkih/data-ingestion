FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY README.md .
COPY src/ ./src/

# libsnappy is required by python-snappy (used by aiokafka to decompress
# market.bars messages published with compression.type=snappy).
RUN apt-get update && apt-get install -y --no-install-recommends libsnappy1v5 && \
    rm -rf /var/lib/apt/lists/*

# Install with Kafka support for event-driven pipeline
RUN pip install --no-cache-dir ".[kafka]"

# In-image defaults keep the container self-consistent with the
# EXPOSE/HEALTHCHECK below even when ingest.env omits them (M10).
ENV INGEST_SERVER_HOST=0.0.0.0 \n    INGEST_SERVER_PORT=8001
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health').read()" || exit 1

CMD ["blackheart-ingest-server"]
