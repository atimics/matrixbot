# chatbot.Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libolm-dev \
    pkg-config \
    libssl-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy poetry files first for better Docker layer caching
COPY pyproject.toml poetry.lock* ./

# Install a specific, modern version of Poetry
RUN pip install poetry>=1.2.0

# Configure poetry: don't create a virtual environment and install in system site-packages
RUN poetry config virtualenvs.create false
RUN poetry config virtualenvs.in-project false

# Install dependencies using poetry BEFORE copying application code
# --without dev ensures development packages are excluded
# --no-interaction, --no-ansi are good for CI/Docker
# --no-root prevents installation of the current package (since we haven't copied the code yet)
RUN poetry install --without dev --no-interaction --no-ansi --no-root

# Copy the rest of the application's code into the container AFTER dependencies
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/matrix_store

# Expose the API server port
EXPOSE 8000

# Command to run the application with the management UI
CMD ["poetry", "run", "python", "-m", "chatbot.main_with_ui"]
