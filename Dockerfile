# Multi-stage build for Python chatbot
FROM python:3.11-slim-bookworm as builder

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create and set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy source code
COPY chatbot/ ./chatbot/
COPY src/ ./src/
COPY control_panel.py ./
COPY README.md ./

# Install the chatbot package in development mode
RUN pip install -e .

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

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app /app

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
