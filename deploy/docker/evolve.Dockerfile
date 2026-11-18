# syntax=docker/dockerfile:1
#
# Image de travail du modèle de code (libs/evolve/sandbox.py) : Python + dépendances de Rosalie,
# Node (site web), git, et l'agent opencode. Construite toute seule au premier besoin ; à la main :
#   docker build -t rosalie-evolve:latest -f deploy/docker/evolve.Dockerfile .
# Elle ne contient ni le code ni les données de Rosalie : le clone de travail y est monté.
FROM python:3.13-slim-bookworm
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates ripgrep procps \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g --no-audit --no-fund opencode-ai \
    && npm cache clean --force
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
WORKDIR /workspace
