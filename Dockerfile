# Multi-stage build for Python chatbot
FROM python:3.11-slim-bookworm as builder

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
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Create and set work directory
WORKDIR /app

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Install dependencies using Poetry
RUN poetry install --no-dev --no-interaction --no-ansi && rm -rf $POETRY_CACHE_DIR

# Copy source code
COPY chatbot/ ./chatbot/
COPY scripts/ ./scripts/
COPY README.md ./

# Copy control panel from scripts to root for Docker service
COPY scripts/control_panel.py ./control_panel.py

# Production stage
FROM python:3.11-slim-bookworm as production

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

# Copy installed packages from builder (Poetry venv)
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY --from=builder /app /app

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
