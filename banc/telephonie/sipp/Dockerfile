# Simulateur d'appels SIP du banc : SIPp, plus tcpdump pour relever sur le
# réseau les paquets de son reçus d'Asterisk.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        sip-tester tcpdump procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /banc
COPY scenarios/ /banc/scenarios/
COPY appeler.sh /banc/appeler.sh
RUN chmod 0755 /banc/appeler.sh

# Le conteneur reste en vie : chaque appel est lancé par « docker compose exec ».
CMD ["sleep", "infinity"]
