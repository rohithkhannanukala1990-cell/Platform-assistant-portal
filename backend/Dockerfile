FROM python:3.12-slim

# System deps for psycopg2-binary and python3-saml (xmlsec)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl libxmlsec1-dev libffi-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Symlink lets ``import backend.*`` work in this image (Celery include=backend.tasks).
RUN ln -sfn /app /app/backend \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Use exec form so signals (SIGTERM) are forwarded correctly.
# Do not use --reload here: the compose service is read_only and the
# reloader cannot write watch state, which prevents the process from becoming healthy.
# Run as the backend package so relative imports (from .middleware ...) work.
# The /app/backend symlink above makes ``backend.main`` resolve to this tree.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
