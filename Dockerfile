# WAKALA public judge demo: one service (FastAPI serves the built React app from the same origin).
# Fresh synthetic data and freshly generated development signing keys are created inside the container at start;
# no keys, passwords or databases from the repository are used (they are git-ignored).

FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty API base URL = same-origin relative requests (no localhost URLs in the bundle).
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY evidence /app/evidence
COPY --from=web /web/dist /app/frontend/dist
RUN useradd --create-home wakala && mkdir -p /data && chown wakala /data
USER wakala
ENV WAKALA_PUBLIC_DEMO=1 \
    WAKALA_DEV_MODE=0 \
    WAKALA_DB_PATH=/data/wakala.db \
    WAKALA_DEV_KEYS_DIR=/data/keys \
    WAKALA_DOCUMENTS_DIR=/data/documents \
    WAKALA_FRONTEND_DIST=/app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
