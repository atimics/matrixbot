# Multi-stage build for Python chatbot
FROM python:3.11-slim-bookworm AS builder

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies including Poetry
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry with export plugin
RUN pip install --upgrade pip
RUN pip install "poetry>=2.0.0"
RUN poetry self add poetry-plugin-export

# Configure Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Create and set work directory
WORKDIR /app

# Copy Poetry configuration files FIRST for better layer caching
COPY pyproject.toml poetry.lock ./

# Generate requirements.txt from Poetry for reliable dependency installation
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes --only=main

# Install dependencies using Poetry (no-root since package-mode is false)
# This happens BEFORE copying source code for better Docker layer caching
RUN poetry install --only=main --no-interaction --no-ansi --no-root && \
    rm -rf $POETRY_CACHE_DIR

# Copy source code AFTER dependencies are installed
COPY src/chatbot/ ./chatbot/


# Production stage
FROM python:3.11-slim-bookworm AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CHATBOT_ENV=production

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r chatbot && useradd -r -g chatbot chatbot

# Create application directory
WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy the generated requirements.txt as backup
COPY --from=builder /app/requirements.txt /app/requirements.txt

# Copy application code
COPY --from=builder /app/chatbot /app/chatbot
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# Add Poetry venv to PATH  
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Verify psycopg.pool is available - if not, install missing packages
RUN python -c "import psycopg.pool" || (echo "psycopg.pool not found, installing missing packages..." && pip install -r requirements.txt)

# Create directories for data persistence
RUN mkdir -p /app/data /app/logs /app/matrix_store /app/context_storage
RUN chown -R chatbot:chatbot /app

# Switch to non-root user
USER chatbot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('/app/data/chatbot.db').execute('SELECT 1')" || exit 1

# Expose port (if needed for web interface)
EXPOSE 8000

# Set default command to run chatbot with UI
CMD ["python", "-m", "chatbot.main_with_ui"]
