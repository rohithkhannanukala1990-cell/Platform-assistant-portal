FROM python:3.12-slim

# System deps for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Symlink lets ``import backend.*`` work in this image (Celery include=backend.tasks).
RUN ln -sfn /app /app/backend

EXPOSE 8000

# Use exec form so signals (SIGTERM) are forwarded correctly
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
