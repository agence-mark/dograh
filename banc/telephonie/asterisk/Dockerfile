# syntax=docker/dockerfile:1
# Asterisk du banc de téléphonie, construit depuis les sources officielles.
#
# Pourquoi une construction et pas une image existante : il n'existe pas d'image
# officielle d'Asterisk, et le fork exige une version précise (22.8.0 au minimum,
# pour `transport_data` sur externalMedia) avec les modules chan_websocket et
# res_websocket_client. L'archive vient de downloads.asterisk.org et son empreinte
# est contrôlée avant toute compilation.

FROM debian:bookworm-slim AS construction

ARG ASTERISK_VERSION=22.12.0
# Empreinte publiée à côté de l'archive (asterisk-<version>.sha256).
ARG ASTERISK_SHA256=f8b2ba98aac6c4ff3376bc0a2868bea6ed577ca684efb7ec739ae6e8ce6e35e2

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential bzip2 ca-certificates curl patch pkg-config \
        libedit-dev libjansson-dev libsqlite3-dev libssl-dev libxml2-dev uuid-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src
RUN curl -fsSL --retry 3 -o asterisk.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/asterisk/releases/asterisk-${ASTERISK_VERSION}.tar.gz" \
    && echo "${ASTERISK_SHA256}  asterisk.tar.gz" | sha256sum -c - \
    && mkdir asterisk && tar -xzf asterisk.tar.gz -C asterisk --strip-components=1 \
    && rm asterisk.tar.gz

WORKDIR /usr/src/asterisk
# pjproject est celui livré avec Asterisk : c'est la combinaison que l'éditeur teste.
RUN ./configure --with-pjproject-bundled --with-jansson --without-dahdi --without-pri \
        --without-ss7 --without-mfcr2 --without-x11 > /tmp/configure.log 2>&1 \
    || (tail -n 40 /tmp/configure.log && exit 1)

# Ni sons ni musique d'attente (le banc n'en joue pas), et pas d'optimisation
# propre au processeur de construction.
RUN make menuselect.makeopts > /dev/null \
    && menuselect/menuselect \
        --disable-category MENUSELECT_CORE_SOUNDS \
        --disable-category MENUSELECT_EXTRA_SOUNDS \
        --disable-category MENUSELECT_MOH \
        --disable-category MENUSELECT_ADDONS \
        --disable BUILD_NATIVE \
        --enable chan_websocket --enable res_websocket_client \
        menuselect.makeopts \
    && if grep -E '^MENUSELECT_(CHANNELS|RES)=' menuselect.makeopts | tr ' =' '\n\n' \
        | grep -E -x 'chan_websocket|res_websocket_client|res_ari|chan_pjsip' ; then \
        echo "Un module requis par le banc est désactivé par menuselect" ; exit 1 ; fi

RUN make -j"$(nproc)" > /tmp/make.log 2>&1 || (tail -n 60 /tmp/make.log && exit 1)
RUN make install DESTDIR=/sortie > /tmp/install.log 2>&1 || (tail -n 40 /tmp/install.log && exit 1)

# Les deux modules sans lesquels le fork n'a pas de son doivent exister.
# /var/run est un lien vers /run dans Debian : le dossier installé ne peut pas
# être copié par-dessus, il est recréé dans l'image d'exécution.
RUN test -f /sortie/usr/lib/asterisk/modules/chan_websocket.so \
    && test -f /sortie/usr/lib/asterisk/modules/res_websocket_client.so \
    && rm -rf /sortie/var/run


FROM debian:bookworm-slim AS execution

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates libedit2 libjansson4 libsqlite3-0 libssl3 libxml2 libuuid1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=construction /sortie/ /

# Une bibliothèque manquante se voit ici, à la construction, pas au premier appel.
RUN ldconfig \
    && ! (ldd /usr/sbin/asterisk /usr/lib/asterisk/modules/*.so 2>/dev/null | grep "not found")

RUN groupadd --system asterisk \
    && useradd --system --gid asterisk --no-log-init --home-dir /var/lib/asterisk asterisk \
    && mkdir -p /etc/asterisk /var/run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/asterisk \
    && chown -R asterisk:asterisk /etc/asterisk /var/run/asterisk /var/log/asterisk \
        /var/spool/asterisk /var/lib/asterisk

COPY --chown=asterisk:asterisk conf/ /etc/asterisk/
COPY --chown=asterisk:asterisk demarrer.sh /usr/local/bin/demarrer.sh
RUN chmod 0755 /usr/local/bin/demarrer.sh

USER asterisk
EXPOSE 5060/udp 8088/tcp
CMD ["/usr/local/bin/demarrer.sh"]
