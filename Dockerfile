FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for sqlite and python packages
RUN apt-get update && apt-get install -y gcc sqlite3 libsqlite3-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose FastAPI port
EXPOSE 8000

CMD ["python", "-m", "app.main"]
