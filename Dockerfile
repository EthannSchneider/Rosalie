# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt /build/requirements.txt
RUN pip install -r /build/requirements.txt

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    STORAGE_DIR=/app/storages \
    LOG_FILE=/app/storages/log.txt \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
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
COPY cogs/ cogs/
COPY libs/ libs/
COPY personas/ personas/
COPY tests/ tests/
RUN mkdir -p storages \
    && chown -R rosalie:rosalie storages
USER rosalie
ENTRYPOINT ["python3", "bot.py"]
CMD ["rosalie"]
