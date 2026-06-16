# ==============================================================================
# Stage 1: Build Dependencies
# ==============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build tools required for compiling binary dependencies if necessary
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install target python packages directly to the user directory
# TODO: Pin versions in a requirements.txt file for production
RUN pip install --no-cache-dir --user \
    dnspython \
    httpx \
    pandas \
    numpy \
    fastapi \
    uvicorn \
    python-dotenv \
    prometheus-client \
    psycopg2-binary \
    sqlalchemy

# ==============================================================================
# Stage 2: Final Runtime Image
# ==============================================================================
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/chronos/.local/bin:${PATH}"

# Install essential runtime libraries (e.g., libpq for database connection)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root system group and user
RUN groupadd -g 10001 chronos && \
    useradd -u 10001 -g chronos -m -s /bin/bash chronos

# Copy installed Python packages from the builder stage
COPY --from=builder --chown=chronos:chronos /root/.local /home/chronos/.local

# Copy application code with appropriate ownership
COPY --chown=chronos:chronos . /app/

# Expose the port the FastAPI application runs on
EXPOSE 8000

# Create data directory with correct ownership before switching to non-root user
RUN mkdir -p /app/data && chown chronos:chronos /app/data

# Switch to the non-root runner user
USER chronos

# Execute the probe application
CMD ["uvicorn", "probe:app", "--host", "0.0.0.0", "--port", "8000"]
