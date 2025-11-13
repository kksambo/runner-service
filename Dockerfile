# ===============================
# FastAPI Code Runner Dockerfile
# ===============================

FROM python:3.11-slim

# Install needed tools (docker-cli lets us call 'docker run' from inside container)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates bash curl gcc g++ make docker-cli \
 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy FastAPI app
COPY main.py .

# Expose FastAPI port
EXPOSE 8001

# Run FastAPI using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
