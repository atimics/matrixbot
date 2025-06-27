FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including build tools
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create secure storage directory
RUN mkdir -p /secure_storage && chmod 700 /secure_storage

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application with restricted permissions
RUN useradd -m -u 1000 signeruser && chown -R signeruser:signeruser /app /secure_storage
USER signeruser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
