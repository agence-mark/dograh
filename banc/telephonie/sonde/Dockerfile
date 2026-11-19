# Image de la sonde et de l'analyseur du banc.
FROM python:3.13-slim

# Même version d'aiohttp que l'API (api/constraints.txt).
RUN pip install --no-cache-dir aiohttp==3.14.3

RUN useradd --system --no-log-init --home-dir /banc sonde
WORKDIR /banc
COPY --chown=sonde:sonde sonde.py analyser.py latence.py relais.py coupures.py ./

USER sonde
EXPOSE 8090
CMD ["python", "sonde.py"]
