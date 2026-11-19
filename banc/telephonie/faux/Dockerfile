# Image des faux fournisseurs du banc (transcription, modèle, voix).
FROM python:3.13-slim

# openssl : le certificat du banc pour la vérification de clé de Soniox.
RUN apt-get update && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

# Même version d'aiohttp que l'API (api/constraints.txt).
RUN pip install --no-cache-dir aiohttp==3.14.3

RUN useradd --system --no-log-init --home-dir /banc faux \
    && mkdir /certificats && chown faux:faux /certificats
WORKDIR /banc
COPY --chown=faux:faux *.py ./

USER faux
VOLUME /certificats
EXPOSE 8080 443
CMD ["python", "serveur.py"]
