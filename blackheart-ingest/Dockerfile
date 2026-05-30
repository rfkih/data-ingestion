FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY README.md .
COPY src/ ./src/

# Install with Kafka support for event-driven pipeline
RUN pip install --no-cache-dir ".[kafka]"

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health').read()" || exit 1

CMD ["blackheart-ingest-server"]
