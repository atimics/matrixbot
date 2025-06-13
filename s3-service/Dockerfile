# Use a lean, official Python base image
FROM python:3.10-slim

WORKDIR /app

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install poetry
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir poetry==1.7.1

# Configure poetry to not create virtual environment
RUN poetry config virtualenvs.create false

# Copy pyproject.toml and poetry.lock for dependency installation
COPY pyproject.toml poetry.lock* ./

# Install dependencies using poetry
RUN poetry install --no-dev --no-interaction --no-ansi

# Copy the application source code
COPY . .

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
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
