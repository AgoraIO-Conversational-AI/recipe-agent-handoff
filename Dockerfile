# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS runtime

# Run as a non-root user (created before any COPY so --chown can reference it).
RUN useradd --create-home --uid 10001 app
WORKDIR /app

# Dependencies for the FastAPI backend AND the bundled mock LLM endpoint.
COPY server/requirements.txt /tmp/server-req.txt
COPY llm/requirements.txt /tmp/llm-req.txt
RUN pip install --no-cache-dir -r /tmp/server-req.txt -r /tmp/llm-req.txt

# Sources + the supervising entrypoint, owned by the runtime user.
COPY --chown=app:app server/src /app/server/src
COPY --chown=app:app llm/src /app/llm/src
COPY --chown=app:app docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# The mock writes its SQLite log here (writable by the non-root user).
ENV MESSAGE_DB_PATH=/tmp/messages.db

USER app

# server.py binds :8000 ($PORT); the mock binds :8001 ($CUSTOM_LLM_PORT). Both 0.0.0.0.
EXPOSE 8000 8001
ENTRYPOINT ["/app/docker-entrypoint.sh"]
