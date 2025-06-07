FROM python:3.10-slim

WORKDIR /uploader_app

# Install system dependencies that might be needed
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy poetry configuration
COPY pyproject.toml poetry.lock* ./

# Install poetry
RUN pip install poetry>=1.2.0

# Configure poetry to not create virtual environment (since we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --only=main --no-interaction --no-ansi

# Copy application code
COPY . .

# Create data directory and set permissions
RUN mkdir -p /data && chmod 755 /data

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the application
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
