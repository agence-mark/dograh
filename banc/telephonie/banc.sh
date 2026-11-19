#!/usr/bin/env bash
# Commandes du banc de téléphonie. À lancer depuis n'importe où.
#
#   ./banc.sh preparer        écrit .env avec des valeurs tirées au hasard (une fois)
#   ./banc.sh demarrer        Asterisk, la sonde et SIPp
#   ./banc.sh demarrer-fork   en plus : l'API du dépôt, sa base et Redis
#   ./banc.sh preparer-fork   compte, configuration Asterisk, agent, extensions
#   ./banc.sh regler-plan     à refaire après un redémarrage d'Asterisk
#   ./banc.sh regler-faux ['<json>' | zero]   délais et textes des faux fournisseurs
#   ./banc.sh appeler-sortant [numéro]   appel sortant du fork vers SIPp en réception
#   ./banc.sh base "<SQL>"    une requête sur la base du fork
#   ./banc.sh forme           met en forme et contrôle le code Python du banc
#   ./banc.sh tester <arguments de pytest>   les tests Python du fork, depuis api/
#   ./banc.sh passage <nom> <commit> [base Redis]   la suite tests/mark sur un commit exporté
#   ./banc.sh comparer        les échecs de la branche comparés à ceux de la base
#   ./banc.sh mutation <fichier> <tests>   test de mutation d'un fichier, dans une copie jetable
#   ./banc.sh mutants-lot1    les mutants écrits à la main du lot 1
#   ./banc.sh etat            conteneurs, version et modules d'Asterisk
#   ./banc.sh appeler <extension> <mesure> [durée ms] [appelant]
#   ./banc.sh voix <nom> <plan>   fabrique une voix d'appelant (ton et silences)
#   ./banc.sh appeler-en-parlant <extension> <mesure> <voix> [durée ms]
#   ./banc.sh sonder <extension> <répétitions>
#   ./banc.sh analyser        tableau des mesures de la sonde
#   ./banc.sh analyse-run <mesure> [run]   l'analyse d'un run du fork (chronomètre, M2)
#   ./banc.sh latence <mesure>   latence côté appelant, tour par tour
#   ./banc.sh coupures <mesure>  coupures de parole : son après la coupure, file d'Asterisk
#   ./banc.sh construire-sans <commit> <nom>   image de l'API sans un commit, depuis une copie exportée
#   ./banc.sh api-image <nom>    fait tourner l'API du banc sur une image (local, ou une variante)
#   ./banc.sh asterisk <commande>   une commande dans la console d'Asterisk
#   ./banc.sh relais on|off   fait passer le flux audio par le relais qui lit la file d'Asterisk
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
    poser BANC_CLE_FACTICE "$(hasard 32)"
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
      -e BANC_COMPTE_COURRIEL -e BANC_COMPTE_MOT_DE_PASSE -e BANC_CLE_FACTICE \
      sonde python - < fork/preparer_donnees.py
    regler_plan
    ;;
  regler-faux)
    # Règle les faux fournisseurs (délais en millisecondes, textes), sans les
    # redémarrer. Sans argument : affiche les réglages. « zero » : les défauts.
    #   ./banc.sh regler-faux '{"delai_modele_ms": 400, "delai_voix_ms": 90}'
    case "${2:-}" in
      "") methode=GET; corps="" ;;
      zero) methode=DELETE; corps="" ;;
      *) methode=PUT; corps="$2" ;;
    esac
    docker compose exec -T -e METHODE="$methode" -e CORPS="$corps" sonde python -c '
import os, urllib.request
corps = os.environ["CORPS"].encode() or None
requete = urllib.request.Request("http://faux:8080/reglages", method=os.environ["METHODE"], data=corps)
try:
    print(urllib.request.urlopen(requete, timeout=10).read().decode())
except urllib.error.HTTPError as refus:
    raise SystemExit(f"{refus.code} : {refus.read().decode()}")
'
    ;;
  appeler-sortant)
    # Appel sortant du fork vers SIPp en réception.
    set -a && . ./.env && set +a
    docker compose exec -T \
      -e BANC_COMPTE_COURRIEL -e BANC_COMPTE_MOT_DE_PASSE \
      sonde python - "${2:-1000}" < fork/appeler_sortant.py
    ;;
  regler-plan)
    regler_plan
    ;;
  forme)
    # Mise en forme et contrôle du code Python du banc. Les dossiers sont nommés
    # un à un : resultats/ contient des copies figées du dépôt qu'il ne faut
    # jamais réécrire pendant qu'une suite de tests tourne dessus (réflexe R8).
    docker run --rm -v "$PWD/sonde:/src/sonde" -v "$PWD/fork:/src/fork" \
      -v "$PWD/essais:/src/essais" -v "$PWD/faux:/src/faux" -v "$PWD/sipp:/src/sipp" \
      --entrypoint sh banc-telephonie-mark/essais:local \
      -c "cd /src && ruff format --no-cache sonde fork essais faux sipp && ruff check --no-cache sonde fork essais faux sipp"
    ;;
  tester)
    # pytest dans le conteneur des tests, sur l'arbre de travail du dépôt.
    #   ./banc.sh tester tests/mark/test_x.py -q
    shift
    "${compose[@]}" run --rm -T essais pytest -p no:cacheprovider "$@"
    ;;
  passage)
    # Joue la suite tests/mark sur un arbre FIGÉ (un commit exporté), comme la CI
    # comparée, et laisse ses trois fichiers dans resultats/rapports/<nom>/.
    #   ./banc.sh passage base d4990b89
    #   ./banc.sh passage branche HEAD 2     (2 : numéro de base Redis)
    # L'arbre de travail n'est pas lu : on peut continuer d'y travailler (réflexe R8).
    # Les copies n'ont pas les modules Node du validateur TypeScript : les tests qui
    # l'appellent (ts_validator) sont rouges des deux côtés, à l'identique.
    nom="${2:?nom du passage (base, branche)}"
    commit="${3:?commit à jouer}"
    # UN SEUL passage à la fois. Chaque passage a bien sa base de tests et son
    # numéro de base Redis, mais des tests créent des bases et des rôles sur le
    # serveur Postgres commun : deux suites en même temps se marchent dessus
    # (« tuple concurrently updated ») et faussent la comparaison.
    redis="${4:-0}"
    if docker ps --format '{{.Names}}' | grep -q '^banc-passage-'; then
      echo "Un passage tourne déjà : attendre sa fin (resultats/rapports/<nom>/code-sortie.txt)." >&2
      exit 1
    fi
    docker rm "banc-passage-$nom" > /dev/null 2>&1 || true
    arbre="resultats/arbres/$nom"
    rapports="resultats/rapports/$nom"
    rm -rf "$arbre" "$rapports"
    mkdir -p "$arbre" "$rapports" resultats/outils-mark
    git -C ../.. archive "$commit" | tar -x -C "$arbre"
    git -C ../.. rev-parse "$commit" > "$rapports/commit.txt"
    # La sonde mémoire vient de la branche, seule dans son dossier, comme en CI.
    cp ../../api/tests/mark/sonde_memoire.py resultats/outils-mark/
    BANC_ARBRE="$PWD/$arbre" "${compose[@]}" run -d --name "banc-passage-$nom" \
      -e PYTHONPATH=/app/pipecat/src:/app:/outils-mark \
      -e MARK_SONDE_FICHIER=/rapports/sonde-memoire.json \
      -e DATABASE_URL="postgresql+asyncpg://postgres:$(sed -n 's/^BANC_POSTGRES_MOT_DE_PASSE=//p' .env)@postgres:5432/test_db_$nom" \
      -e REDIS_URL="redis://:$(sed -n 's/^BANC_REDIS_MOT_DE_PASSE=//p' .env)@redis:6379/$redis" \
      -v "$PWD/resultats/outils-mark:/outils-mark:ro" \
      -v "$PWD/$rapports:/rapports" \
      essais sh -c 'pytest tests/mark -p sonde_memoire -p no:cacheprovider \
        --continue-on-collection-errors -o faulthandler_timeout=120 --durations=25 \
        --timeout=600 --timeout-method=signal --junitxml=/rapports/junit.xml \
        > /rapports/pytest.log 2>&1 < /dev/null; echo $? > /rapports/code-sortie.txt'
    echo "Passage $nom lancé (conteneur banc-passage-$nom). Fin : resultats/rapports/$nom/code-sortie.txt"
    ;;
  mutation)
    # Test de mutation (mutmut) d'UN fichier par UN fichier de tests, dans une
    # copie jetable : l'arbre de travail n'est ni muté ni encombré.
    #   ./banc.sh mutation api/services/x.py api/tests/mark/test_x.py
    source="${2:?fichier à muter, depuis la racine du dépôt}"
    essai="${3:?fichier de tests, depuis la racine du dépôt}"
    mkdir -p resultats/mutation
    "${compose[@]}" run --rm -T \
      -e PYTHONPATH=/app/pipecat/src \
      -e DATABASE_URL="postgresql+asyncpg://postgres:$(sed -n 's/^BANC_POSTGRES_MOT_DE_PASSE=//p' .env)@postgres:5432/test_db_mutation" \
      -e REDIS_URL="redis://:$(sed -n 's/^BANC_REDIS_MOT_DE_PASSE=//p' .env)@redis:6379/3" \
      -e BANC_SOURCE="$source" -e BANC_ESSAI="$essai" \
      -v "$PWD/resultats/mutation:/rapports" \
      -w /tmp essais sh -c '
        set -e
        mkdir -p /tmp/mutation && cd /tmp/mutation
        cp -r /app/api ./api
        printf "[mutmut]\nsource_paths=api\nonly_mutate=%s\npytest_add_cli_args_test_selection=%s\npytest_add_cli_args=-p no:cacheprovider --timeout=120\n" \
          "$BANC_SOURCE" "$BANC_ESSAI" > setup.cfg
        mutmut run > /rapports/mutmut-run.log 2>&1 || true
        tail -n 25 /rapports/mutmut-run.log
        mutmut results --all true > /rapports/mutmut-resultats.txt 2>&1 || mutmut results > /rapports/mutmut-resultats.txt 2>&1 || true
        cat /rapports/mutmut-resultats.txt
        : > /rapports/mutmut-mutants.txt
        for nom in $(grep -o "^ *[A-Za-z0-9_.ǁ]*__mutmut_[0-9]*" /rapports/mutmut-resultats.txt | tr -d " "); do
          { echo "=== $nom"; mutmut show "$nom" 2>&1; } >> /rapports/mutmut-mutants.txt
        done
        cp setup.cfg /rapports/setup.cfg'
    ;;
  mutants-lot1)
    # Les mutants écrits à la main du lot 1, dans une copie jetable.
    "${compose[@]}" run --rm -T \
      -e DATABASE_URL="postgresql+asyncpg://postgres:$(sed -n 's/^BANC_POSTGRES_MOT_DE_PASSE=//p' .env)@postgres:5432/test_db_mutation" \
      -e REDIS_URL="redis://:$(sed -n 's/^BANC_REDIS_MOT_DE_PASSE=//p' .env)@redis:6379/3" \
      -v "$PWD/essais/mutants_lot1.py:/outils/mutants_lot1.py:ro" \
      -w /tmp essais python /outils/mutants_lot1.py
    ;;
  comparer)
    # Verdict de la CI comparée sur les deux passages.
    "${compose[@]}" run --rm -T \
      -v "$PWD/resultats/rapports:/rapports:ro" \
      essais python /app/api/scripts/mark/comparer_echecs.py \
      --branche /rapports/branche --base /rapports/base
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
  voix)
    # Fabrique une voix d'appelant : voix de synthèse et silences à heures connues.
    #   ./banc.sh voix tours-3 s4000,v1000,s3000,v1000,s3000,v1000,s3000
    nom="${2:?nom de la voix}"
    plan="${3:?plan : s<ms> silence, v<ms> voix de synthèse, t<ms> ton pur, séparés par des virgules}"
    docker compose exec -T sonde python - "/resultats/voix/$nom.pcap" "$plan" < sipp/fabriquer_voix.py
    ;;
  appeler-en-parlant)
    # Un appel où l'appelant joue une voix fabriquée par « ./banc.sh voix ».
    #   ./banc.sh appeler-en-parlant 8000 essai tours-20 90000
    extension="${2:?extension}"
    mesure="${3:?nom de la mesure}"
    nom="${4:?nom de la voix}"
    duree="${5:-30000}"
    docker compose exec -T sipp /banc/appeler.sh "$extension" "$mesure" "$duree" 0100000000 "/resultats/voix/$nom.pcap"
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
  analyse-run)
    # Relève l'analyse d'un run du fork (chronomètre par tour, mesure M2).
    #   ./banc.sh analyse-run <mesure> [numéro du run]   (sans numéro : le dernier)
    shift
    set -a && . ./.env && set +a
    docker compose exec -T \
      -e BANC_COMPTE_COURRIEL -e BANC_COMPTE_MOT_DE_PASSE \
      sonde python /banc/fork/lire_analyse.py "$@"
    ;;
  coupures)
    # Les coupures de parole d'un appel : son après la coupure, file d'Asterisk.
    #   ./banc.sh coupures <mesure>
    docker compose exec -T sonde python coupures.py "${2:?nom de la mesure}"
    ;;
  construire-sans)
    # Construit une image de l'API SANS un commit donné, depuis une copie exportée
    # de la branche : l'arbre de travail et la branche ne bougent pas.
    #   ./banc.sh construire-sans db4b79af sans-lot1
    # Seul le code de api/services du commit est retiré de la copie.
    commit="${2:?commit à retirer}"
    nom="${3:?nom de la variante}"
    arbre="resultats/arbres/$nom"
    rm -rf "$arbre" && mkdir -p "$arbre"
    git -C ../.. archive HEAD | tar -x -C "$arbre"
    git -C ../.. diff "$commit^" "$commit" -- api/services > "resultats/arbres/$nom.patch"
    patch -R -p1 -s -d "$arbre" < "resultats/arbres/$nom.patch"
    git -C ../.. rev-parse HEAD > "$arbre/.banc-commit"
    docker build -q -f "$arbre/api/Dockerfile" -t "banc-telephonie-mark/api:$nom" "$arbre"
    echo "Image banc-telephonie-mark/api:$nom : la branche sans le code de $commit."
    ;;
  api-image)
    # Fait tourner l'API du banc sur une image donnée (« local » : l'arbre de travail).
    #   ./banc.sh api-image sans-lot1
    nom="${2:?image à utiliser (local, ou une variante de construire-sans)}"
    BANC_IMAGE_API="banc-telephonie-mark/api:$nom" "${compose[@]}" up -d --wait api > /dev/null 2>&1
    application="$(sed -n 's/.*"application_stasis": "\(.*\)".*/\1/p' resultats/fork.json)"
    for _ in $(seq 1 90); do
      if docker compose exec -T asterisk asterisk -rx "ari show apps" | grep -q "$application"; then
        break
      fi
      sleep 1
    done
    docker inspect --format 'API du banc : {{.Config.Image}}' banc-telephonie-mark-api-1
    ;;
  latence)
    # Latence côté appelant d'un appel, tour par tour, sur la capture de SIPp.
    #   ./banc.sh latence <mesure>
    docker compose exec -T sonde python latence.py "${2:?nom de la mesure}"
    ;;
  asterisk)
    shift
    docker compose exec -T asterisk asterisk -rx "$*"
    ;;
  relais)
    # Tourne le flux audio d'Asterisk vers le relais (on) ou vers le fork (off).
    # Le relais transmet tout au fork et lit la file d'Asterisk au passage.
    # Asterisk ne relit cette adresse qu'au démarrage : il est redémarré, puis le
    # plan d'appels est reposé et on attend que le fork se soit reconnecté.
    case "${2:?on ou off}" in
      on) cible="ws://relais:8091/api/v1/telephony/ws/ari" ;;
      off) cible="ws://api:8000/api/v1/telephony/ws/ari" ;;
      *) echo "on ou off" >&2; exit 1 ;;
    esac
    docker compose exec -T asterisk sed -i \
      "/^\[dograh\]/,/^\[sonde\]/ s#^uri = .*#uri = $cible#" /etc/asterisk/websocket_client.conf
    docker compose restart asterisk > /dev/null 2>&1
    docker compose up -d --wait asterisk > /dev/null 2>&1
    regler_plan > /dev/null
    application="$(sed -n 's/.*"application_stasis": "\(.*\)".*/\1/p' resultats/fork.json)"
    for _ in $(seq 1 60); do
      if docker compose exec -T asterisk asterisk -rx "ari show apps" | grep -q "$application"; then
        break
      fi
      sleep 1
    done
    docker compose exec -T asterisk asterisk -rx "ari show apps" | grep -q "$application" \
      || { echo "Le fork ne s'est pas reconnecté à Asterisk." >&2; exit 1; }
    docker compose exec -T asterisk sed -n \
      "/^\[dograh\]/,/^\[sonde\]/ s/^uri = /flux audio du fork : /p" /etc/asterisk/websocket_client.conf
    ;;
  arreter)
    "${compose[@]}" stop
    ;;
  supprimer)
    "${compose[@]}" down --volumes --remove-orphans
    ;;
  *)
    sed -n '2,25p' "${BASH_SOURCE[0]}"
    exit 1
    ;;
esac
