#!/bin/sh
# Passe UN appel vers Asterisk et relève les paquets de son reçus.
#
#   appeler.sh <extension> <mesure> [durée en ms] [numéro de l'appelant]
#
# Écrit dans /resultats : <mesure>.pcap (paquets reçus), <mesure>.sip.log
# (messages SIP échangés), <mesure>.sipp.log (sortie de SIPp).
set -eu

extension="${1:?extension à appeler}"
mesure="${2:?nom de la mesure}"
duree="${3:-12000}"
appelant="${4:-0100000000}"
sortie=/resultats

mkdir -p "$sortie"
rm -f "$sortie/$mesure.pcap" "$sortie/$mesure.sip.log" "$sortie/$mesure.sipp.log"

# Tout l'UDP hors signalisation SIP : c'est le son.
tcpdump -i eth0 -U -n -s 0 -w "$sortie/$mesure.pcap" 'udp and not port 5060' \
    > /dev/null 2>&1 &
capture=$!
sleep 0.5

code=0
sipp asterisk:5060 \
    -sf /banc/scenarios/appel.xml \
    -s "$extension" \
    -key mesure "$mesure" -key appelant "$appelant" \
    -d "$duree" \
    -m 1 -l 1 -r 1 \
    -mp 6000 \
    -timeout "$(( duree / 1000 + 20 ))" -timeout_error \
    -trace_msg -message_file "$sortie/$mesure.sip.log" \
    -nostdin \
    > "$sortie/$mesure.sipp.log" 2>&1 || code=$?

sleep 0.5
kill "$capture" 2>/dev/null || true
wait "$capture" 2>/dev/null || true

# Une ligne lisible : la première réponse finale d'Asterisk, et qui a raccroché.
reponse="$(grep -E '^SIP/2.0 [2-6][0-9][0-9]' "$sortie/$mesure.sip.log" 2>/dev/null | grep -v ' 200 OK' | head -n 1 || true)"
decroche="$(grep -c -E '^SIP/2.0 200 ' "$sortie/$mesure.sip.log" 2>/dev/null || true)"
raccroche_par_asterisk="$(grep -c -E '^BYE .* SIP/2.0' "$sortie/$mesure.sip.log" 2>/dev/null || true)"
echo "mesure=$mesure extension=$extension code_sipp=$code reponses_200=$decroche refus='${reponse}' lignes_bye=$raccroche_par_asterisk"
exit 0
