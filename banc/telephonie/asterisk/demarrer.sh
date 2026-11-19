#!/bin/sh
# Écrit ari.conf depuis l'environnement, puis lance Asterisk au premier plan.
# Le mot de passe ARI ne vit donc dans aucun fichier du dépôt.
set -eu

: "${BANC_ARI_UTILISATEUR:?BANC_ARI_UTILISATEUR manquant (voir .env.example)}"
: "${BANC_ARI_MOT_DE_PASSE:?BANC_ARI_MOT_DE_PASSE manquant (voir .env.example)}"

umask 077
cat > /etc/asterisk/ari.conf <<EOF
[general]
enabled = yes

[${BANC_ARI_UTILISATEUR}]
type = user
read_only = no
password = ${BANC_ARI_MOT_DE_PASSE}
EOF

exec asterisk -f -vvv
