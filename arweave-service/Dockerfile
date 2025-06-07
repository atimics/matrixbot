# Use a lean, official Python base image
FROM python:3.10-slim

WORKDIR /app

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy only necessary files for dependency installation
COPY pyproject.toml poetry.lock* ./

# Install poetry and dependencies in a single layer
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir poetry>=1.2.0 \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main

# Copy the application source code
COPY . .

# Create the data directory for the wallet file
# Set ownership to the non-root user
RUN mkdir -p /data && chown -R appuser:appuser /data

# Change ownership of the entire app to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the service port
EXPOSE 8001

# Healthcheck to verify the service is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Default command to run the application
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
