FROM python:3.11-slim

# Install Docker CLI and Git
RUN apt-get update && apt-get install -y \
    docker.io \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy runner code
COPY . .

# Create workspace directory
RUN mkdir -p /workspace

EXPOSE 8001

CMD ["python", "runner_service.py"]