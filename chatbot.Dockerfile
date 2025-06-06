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
    && rm -rf /var/lib/apt/lists/*

# Copy poetry files first for better Docker layer caching
COPY pyproject.toml poetry.lock* ./

# Install poetry
RUN pip install poetry

# Configure poetry: don't create a virtual environment
RUN poetry config virtualenvs.create false

# Export dependencies to requirements.txt
# Ensure --without dev is used here to exclude development packages
RUN poetry export --without dev --format requirements.txt --output requirements.txt

# Install dependencies using pip from the exported requirements.txt
# --no-cache-dir is a good practice for Docker images to keep them small
# --prefer-binary can speed up installations for packages with binary distributions
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Create necessary directories
RUN mkdir -p /app/context_storage /app/matrix_store

# Expose the API server port
EXPOSE 8000

# Command to run the application with the management UI
CMD ["poetry", "run", "python", "-m", "chatbot.main_with_ui"]
