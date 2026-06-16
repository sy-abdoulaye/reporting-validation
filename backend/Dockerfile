FROM registry.example.com/dockerhub/library/python:3.10-slim

# Variables d'environnement Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG http_proxy
ARG https_proxy
ARG no_proxy
ENV http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy

# Installer les dépendances Python d'abord (cache Docker)
# Tous les paquets disposent de wheels manylinux → pas besoin de gcc
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copier le code de l'application
COPY . .

# Rendre l'entrypoint exécutable
RUN chmod +x /app/docker-entrypoint.sh

# Créer les dossiers de données
RUN mkdir -p /app/data/uploads /app/data/reports

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
