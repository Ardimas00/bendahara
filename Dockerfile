# Use a small Python base image
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Install build deps only if needed (pymongo usually doesn't need heavy build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app

# Expose the port Koyeb expects by default
EXPOSE 8080

# Start using Gunicorn, binding to $PORT (default 8080)
CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:${PORT}", "--workers", "2"]
