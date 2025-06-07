FROM python:3.10-slim

WORKDIR /uploader_app

# Install system dependencies, including Node.js and npm
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js from NodeSource repository for latest version
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verify Node.js and npm installation
RUN node --version && npm --version

# Set npm global directory and update PATH
ENV NPM_CONFIG_PREFIX=/usr/local
ENV PATH=$PATH:/usr/local/bin

# Install ardrive-cli globally using npm with verbose output
RUN npm install -g ardrive-cli --verbose

# Debug: Check npm global bin directory and installed packages
RUN npm list -g --depth=0 && \
    npm bin -g && \
    ls -la $(npm bin -g) || echo "Could not list npm bin directory"

# Get the npm global bin directory and add it to PATH
RUN NPM_GLOBAL_BIN=$(npm bin -g) && \
    echo "export PATH=\$PATH:$NPM_GLOBAL_BIN" >> /etc/profile && \
    ln -sf $NPM_GLOBAL_BIN/ardrive-cli /usr/local/bin/ardrive-cli || echo "Could not create symlink"

# Verify ardrive-cli installation
RUN which ardrive-cli || echo "ardrive-cli not found in PATH" && \
    ls -la /usr/local/bin/ | grep -i ardrive || echo "No ardrive files in /usr/local/bin" && \
    ls -la /usr/local/lib/node_modules/ | grep -i ardrive || echo "No ardrive modules found" && \
    find /usr/local -name "*ardrive*" -type f 2>/dev/null || echo "No ardrive files found"

# Copy poetry configuration
COPY pyproject.toml poetry.lock* ./

# Install poetry
RUN pip install poetry>=1.2.0

# Configure poetry to not create virtual environment (since we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --only=main --no-interaction --no-ansi

# Copy the rest of the application code, including the new entrypoint script
COPY . .

# Ensure the entrypoint script is executable
RUN chmod +x ./entrypoint.sh

# Create data directory and set permissions
RUN mkdir -p /data && chmod 755 /data

# Expose port
EXPOSE 8001

# Health check with more appropriate timing for wallet initialization
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Set the entrypoint to our new script
ENTRYPOINT ["./entrypoint.sh"]

# The default command to run after the entrypoint script finishes
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
