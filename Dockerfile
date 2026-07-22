# Backend Dockerfile for Render deployment
FROM python:3.12-slim

WORKDIR /app

# Install system deps needed by some libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY api/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the backend code
COPY backend/ /app/

# Expose port
EXPOSE 8000

# Start the server
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
