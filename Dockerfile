# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt /build/requirements.txt
RUN pip install -r /build/requirements.txt

# Site web (React + Tailwind, Vite) : construit ici, seul le résultat (webui/dist) est copié
FROM node:22-bookworm-slim AS webui
WORKDIR /webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webui/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    STORAGE_DIR=/app/storages \
    LOG_FILE=/app/storages/log.txt \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    WEB_UI_HOST=0.0.0.0
RUN groupadd --gid 10001 rosalie \
    && useradd --uid 10001 --gid rosalie --no-create-home rosalie
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
# Navigateur virtuel (Chromium headless) + ses bibliothèques système, pour les sites en JavaScript
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*
COPY bot.py requirements.txt ./
COPY commands/ commands/
COPY interfaces/ interfaces/
COPY libs/ libs/
COPY migrations/ migrations/
COPY personas/ personas/
COPY tests/ tests/
COPY --from=webui /webui/dist webui/dist
RUN mkdir -p storages \
    && chown -R rosalie:rosalie storages
USER rosalie
EXPOSE 8765
ENTRYPOINT ["python3", "bot.py"]
CMD ["rosalie"]
