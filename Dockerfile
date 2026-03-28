FROM node:24-alpine AS frontend-build

WORKDIR /app

COPY package.json package-lock.json /app/
RUN npm ci --no-audit --no-fund

COPY frontend /app/frontend
COPY scripts/build_frontend.mjs /app/scripts/build_frontend.mjs
COPY static /app/static
RUN npm run build:frontend


FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends catdoc antiword \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY --from=frontend-build /app/static /app/static

EXPOSE 8101

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8101"]
