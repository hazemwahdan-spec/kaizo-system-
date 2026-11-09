FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Build context is the repository root. The backend imports the shared
# productization package from the repository root at runtime.
WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY productization/ /app/productization/

# Cloud Run supplies PORT (normally 8080). Run as an unprivileged user.
RUN addgroup --system --gid 10001 kaizo \
    && adduser --system --uid 10001 --ingroup kaizo --no-create-home kaizo \
    && chown -R kaizo:kaizo /app
USER 10001:10001

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
