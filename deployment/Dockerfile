# Multi-stage production Dockerfile for Cloud Run
# Stage 1: Build dependencies in isolated environment
FROM python:3.11-slim as builder

WORKDIR /app

# Install build-essential if needed for native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Minimal hardened runtime image
FROM python:3.11-slim as runner

WORKDIR /app

# Create dedicated non-root application user and group (POLP compliance)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Copy installed Python packages from builder to non-root user directory
COPY --from=builder /root/.local /home/appuser/.local

# Set environment variables for runtime
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Copy application source code with correct non-root ownership
COPY --chown=appuser:appgroup backend/src /app/src

# Switch to non-root user
USER appuser

EXPOSE 8080

# Container liveness health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
