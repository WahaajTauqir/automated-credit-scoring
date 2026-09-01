# Backend Dockerfile for Google Cloud Run
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Create necessary directories
RUN mkdir -p uploads artifacts logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV ENVIRONMENT=production

# Expose port
EXPOSE 8080

# Health check (using curl for better reliability)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application with gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 3600 --access-logfile - --error-logfile - app:app

