# Use a lean, official Python base image
FROM python:3.10-slim

WORKDIR /app

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install dependencies directly with pip (avoiding Poetry issues)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        fastapi==0.104.1 \
        uvicorn==0.24.0 \
        arweave-python-client==1.0.19 \
        python-multipart==0.0.6 \
        httpx==0.25.2 \
        pydantic==2.5.0

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
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
