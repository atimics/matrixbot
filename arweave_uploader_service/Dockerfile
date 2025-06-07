# =========================================================================
# Multi-stage build for arweave uploader service
# =========================================================================
FROM python:3.10-slim AS final

WORKDIR /uploader_app

# Create a non-root user and group
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

# Install system dependencies for Node.js and build tools
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js from NodeSource repository
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get update && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install ardrive-cli globally
RUN npm install -g ardrive-cli

# Verify ardrive-cli installation
RUN ardrive --version

# Copy poetry configuration first for layer caching
COPY pyproject.toml poetry.lock* ./

# Install poetry and python dependencies
# Using --no-cache-dir reduces image size
RUN pip install --no-cache-dir poetry>=1.2.0 \
    && poetry config virtualenvs.create false \
    && poetry install --only=main --no-interaction --no-ansi

# Copy the rest of the application code
COPY . .

# Create data directory and set permissions for the new user
RUN mkdir -p /data && chown -R appuser:appgroup /data
# Ensure the entrypoint script is executable
RUN chmod +x ./entrypoint.sh

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appgroup /uploader_app

# Switch to the non-root user
USER appuser

# Expose port
EXPOSE 8001

# Health check (remains the same)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Set the entrypoint to our script
ENTRYPOINT ["./entrypoint.sh"]

# The default command to run after the entrypoint script finishes
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
