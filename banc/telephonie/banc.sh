#!/usr/bin/env bash
# Commandes du banc de téléphonie. À lancer depuis n'importe où.
#
#   ./banc.sh preparer        écrit .env avec des valeurs tirées au hasard (une fois)
#   ./banc.sh demarrer        Asterisk, la sonde et SIPp
#   ./banc.sh demarrer-fork   en plus : l'API du dépôt, sa base et Redis
#   ./banc.sh preparer-fork   compte, configuration Asterisk, agent, extensions
#   ./banc.sh regler-plan     à refaire après un redémarrage d'Asterisk
#   ./banc.sh base "<SQL>"    une requête sur la base du fork
#   ./banc.sh tester <arguments de pytest>   les tests Python du fork, depuis api/
#   ./banc.sh etat            conteneurs, version et modules d'Asterisk
#   ./banc.sh appeler <extension> <mesure> [durée ms] [appelant]
#   ./banc.sh sonder <extension> <répétitions>
#   ./banc.sh analyser        tableau des mesures de la sonde
#   ./banc.sh asterisk <commande>   une commande dans la console d'Asterisk
#   ./banc.sh arreter         arrête les conteneurs, garde les données
#   ./banc.sh supprimer       arrête et supprime conteneurs, volumes et réseau
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
compose=(docker compose --profile fork --profile essais)

hasard() { LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c "${1:-32}" || true; }

# Pose dans le plan d'appels d'Asterisk le nom de l'application Stasis que Dograh
# a généré. Le réglage vit en mémoire : il est à refaire après un redémarrage
# d'Asterisk.
regler_plan() {
  local application
  application="$(sed -n 's/.*"application_stasis": "\(.*\)".*/\1/p' resultats/fork.json 2>/dev/null || true)"
  if [[ -z "$application" ]]; then
    echo "Nom de l'application Stasis non lu : lancer ./banc.sh preparer-fork." >&2
    exit 1
  fi
  docker compose exec -T asterisk asterisk -rx "dialplan set global APP_FORK $application"
}

case "${1:-}" in
  preparer)
    # Chaque valeur absente de .env est tirée au hasard ; une valeur présente
    # n'est jamais réécrite.
    umask 077
    touch .env
    poser() { grep -q "^$1=" .env || echo "$1=$2" >> .env; }
    poser BANC_ARI_UTILISATEUR banc
    poser BANC_ARI_MOT_DE_PASSE "$(hasard 32)"
    poser BANC_POSTGRES_MOT_DE_PASSE "$(hasard 32)"
    poser BANC_REDIS_MOT_DE_PASSE "$(hasard 32)"
    poser BANC_JWT_SECRET "$(hasard 48)"
    poser BANC_COMPTE_COURRIEL banc@example.com
    poser BANC_COMPTE_MOT_DE_PASSE "$(hasard 24)"
    poser BANC_WS_TOKEN_SECRET ""
    poser BANC_WS_TOKEN_ENFORCE false
    poser BANC_LIMITE_APPELS 10
    mkdir -p resultats
    echo ".env à jour (valeurs locales, jamais commitées)."
    ;;
  demarrer)
    docker compose up -d --build asterisk sonde sipp
    ;;
  demarrer-fork)
    "${compose[@]}" up -d --build
    ;;
  preparer-fork)
    # Compte, configuration Asterisk, agent et extensions, par les routes de l'API.
    set -a && . ./.env && set +a
    docker compose exec -T \
      -e BANC_COMPTE_COURRIEL -e BANC_COMPTE_MOT_DE_PASSE \
      sonde python - < fork/preparer_donnees.py
    regler_plan
    ;;
  regler-plan)
    regler_plan
    ;;
  tester)
    # pytest dans le conteneur des tests, sur l'arbre de travail du dépôt.
    #   ./banc.sh tester tests/mark/test_x.py -q
    shift
    "${compose[@]}" run --rm -T essais pytest -p no:cacheprovider "$@"
    ;;
  base)
    # Une requête SQL en lecture sur la base du fork.
    shift
    "${compose[@]}" exec -T postgres psql -U postgres -P pager=off -c "$*"
    ;;
  etat)
    "${compose[@]}" ps
    docker compose exec -T asterisk asterisk -rx "core show version"
    docker compose exec -T asterisk asterisk -rx "module show like chan_websocket"
    docker compose exec -T asterisk asterisk -rx "module show like res_websocket_client"
    ;;
  appeler)
    shift
    docker compose exec -T sipp /banc/appeler.sh "$@"
    ;;
  sonder)
    extension="${2:?extension de la sonde (9100 à 9115)}"
    repetitions="${3:-1}"
    for ((i = 1; i <= repetitions; i++)); do
      docker compose exec -T sipp /banc/appeler.sh "$extension" "sonde-${extension}-$(printf '%02d' "$i")"
    done
    ;;
  analyser)
    docker compose exec -T sonde python analyser.py /resultats
    ;;
  asterisk)
    shift
    docker compose exec -T asterisk asterisk -rx "$*"
    ;;
  arreter)
    "${compose[@]}" stop
    ;;
  supprimer)
    "${compose[@]}" down --volumes --remove-orphans
    ;;
  *)
    sed -n '2,19p' "${BASH_SOURCE[0]}"
    exit 1
    ;;
esac
