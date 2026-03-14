# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .
RUN pip install --no-cache-dir ".[analysis]"

# Copy project
COPY . .

# Expose port
EXPOSE 9090

# Command to run the server
CMD ["python", "-m", "codeindex.cli", "serve", "--host", "0.0.0.0", "--port", "9090"]
