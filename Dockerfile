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
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --upgrade pip
RUN pip install poetry

# Configure Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    POETRY_VIRTUALENVS_PATH=/app

# Create and set work directory
WORKDIR /app

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Copy source code (needed for Poetry to install the current project)
COPY chatbot/ ./chatbot/
COPY scripts/ ./scripts/
COPY README.md ./

# Install dependencies using Poetry and locate venv
RUN poetry install --only=main --no-interaction --no-ansi && \
    rm -rf $POETRY_CACHE_DIR

# Create a simple script to find and copy the venv
RUN echo '#!/bin/bash\ncp -r /app/chatbot-*/ /app/.venv' > /app/copy_venv.sh && \
    chmod +x /app/copy_venv.sh && \
    /app/copy_venv.sh

# Copy control panel from scripts to root for Docker service
COPY control_panel.py ./control_panel.py

# Production stage
FROM python:3.11-slim-bookworm AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CHATBOT_ENV=production

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r chatbot && useradd -r -g chatbot chatbot

# Create application directory
WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY --from=builder /app/chatbot /app/chatbot
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/control_panel.py /app/control_panel.py
COPY --from=builder /app/README.md /app/README.md
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# Add Poetry venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

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

# Set default command
CMD ["python", "-m", "chatbot.main"]
