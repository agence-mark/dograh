"""Prépare dans le fork les données du banc, par les routes de l'API.

Tout passe par les mêmes routes que l'écran : inscription, configuration
téléphonique Asterisk, agent, numéros. Rien n'est écrit en base à la main, pour
que le banc prouve aussi ce trajet-là.

Rejouable : ce qui existe déjà est repris, pas recréé.

Lancé dans un conteneur du banc (aucune dépendance) :

    ./banc.sh preparer-fork
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("BANC_API_ADRESSE", "http://api:8000") + "/api/v1"
COURRIEL = os.environ["BANC_COMPTE_COURRIEL"]
MOT_DE_PASSE = os.environ["BANC_COMPTE_MOT_DE_PASSE"]
UTILISATEUR_ARI = os.environ["BANC_ARI_UTILISATEUR"]
MOT_DE_PASSE_ARI = os.environ["BANC_ARI_MOT_DE_PASSE"]
FICHIER_ETAT = Path(os.environ.get("BANC_FICHIER_FORK", "/resultats/fork.json"))
# Les faux fournisseurs du banc (banc/telephonie/faux/). La clé est une valeur
# tirée au hasard dans .env : le schéma du fork en exige une, les faux
# fournisseurs n'en lisent aucune.
ADRESSE_FAUX = os.environ.get("BANC_FAUX_ADRESSE", "faux:8080")
CLE_FACTICE = os.environ.get("BANC_CLE_FACTICE", "")

NOM_CONFIGURATION = "banc-asterisk"
NOM_AGENT = "agent-du-banc"
EXTENSION_AVEC_AGENT = "8000"
EXTENSION_SANS_AGENT = "8001"

# Le plus petit agent valide : un début, une fin, un lien. Même forme que la
# définition de api/tests/conftest.py.
DEFINITION_AGENT = {
    "nodes": [
        {
            "id": "1",
            "type": "startCall",
            "position": {"x": 0, "y": 0},
            "data": {
                "name": "Start",
                "prompt": "Greet the caller, then wait.",
                "is_start": True,
                "allow_interrupt": True,
                "add_global_prompt": False,
            },
        },
        {
            "id": "2",
            "type": "endCall",
            "position": {"x": 0, "y": 200},
            "data": {
                "name": "End",
                "prompt": "Say goodbye.",
                "is_end": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
            },
        },
    ],
    "edges": [
        {
            "id": "1-2",
            "source": "1",
            "target": "2",
            "data": {"label": "End", "condition": "End the call"},
        }
    ],
}


class RefusApi(Exception):
    def __init__(self, code: int, corps: str) -> None:
        super().__init__(f"{code} : {corps[:400]}")
        self.code = code


def appeler(
    methode: str, chemin: str, corps: dict | None = None, jeton: str = ""
) -> dict | list:
    requete = urllib.request.Request(
        API + chemin,
        method=methode,
        data=json.dumps(corps).encode() if corps is not None else None,
        headers={"Content-Type": "application/json"},
    )
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            texte = reponse.read().decode()
    except urllib.error.HTTPError as erreur:
        raise RefusApi(erreur.code, erreur.read().decode()) from erreur
    return json.loads(texte) if texte else {}


def ouvrir_session() -> str:
    identifiants = {"email": COURRIEL, "password": MOT_DE_PASSE}
    try:
        reponse = appeler("POST", "/auth/signup", {**identifiants, "name": "Banc"})
        print("Compte du banc créé (premier compte de l'installation).")
    except RefusApi as refus:
        if refus.code not in (403, 409):
            raise
        reponse = appeler("POST", "/auth/login", identifiants)
        print("Compte du banc déjà présent : connexion.")
    assert isinstance(reponse, dict)
    return reponse["token"]


def configuration_asterisk(jeton: str) -> dict:
    liste = appeler("GET", "/organizations/telephony-configs", jeton=jeton)
    assert isinstance(liste, dict)
    for existante in liste.get("configurations", []):
        if existante["name"] == NOM_CONFIGURATION:
            detail = appeler(
                "GET",
                f"/organizations/telephony-configs/{existante['id']}",
                jeton=jeton,
            )
            assert isinstance(detail, dict)
            return detail
    detail = appeler(
        "POST",
        "/organizations/telephony-configs",
        {
            "name": NOM_CONFIGURATION,
            "is_default_outbound": True,
            "config": {
                "provider": "ari",
                "ari_endpoint": "http://asterisk:8088",
                "app_name": UTILISATEUR_ARI,
                "app_password": MOT_DE_PASSE_ARI,
                "ws_client_name": "dograh",
                "dial_string_template": "PJSIP/{number}@sipp",
            },
        },
        jeton,
    )
    assert isinstance(detail, dict)
    print(f"Configuration Asterisk créée (id {detail['id']}).")
    return detail


def fournisseurs(jeton: str) -> None:
    """Règle la transcription, le modèle et la voix de l'organisation du banc sur
    les faux fournisseurs, par la route de l'écran « Modèles ».

    Trois fournisseurs dont le fork laisse régler l'adresse : Soniox pour la
    transcription, l'API compatible OpenAI pour le modèle, ElevenLabs pour la
    voix. Le fork vérifie les clés à l'enregistrement : celle du modèle sur
    l'adresse réglée, celle de Soniox sur une adresse fixe que le réseau du banc
    mène au faux fournisseur (compose.yaml), celle d'ElevenLabs n'est pas vérifiée.
    """
    if not CLE_FACTICE:
        print("BANC_CLE_FACTICE absente : lancer ./banc.sh preparer.", file=sys.stderr)
        raise SystemExit(1)
    appeler(
        "PUT",
        "/user/configurations/user",
        {
            "stt": {
                "provider": "soniox",
                "api_key": CLE_FACTICE,
                "model": "stt-rt-v5",
                "language": "fr",
                "base_url": f"ws://{ADRESSE_FAUX}/transcribe-websocket",
            },
            "llm": {
                "provider": "openai",
                "api_key": CLE_FACTICE,
                "model": "faux-modele",
                "base_url": f"http://{ADRESSE_FAUX}/v1",
            },
            "tts": {
                "provider": "elevenlabs",
                "api_key": CLE_FACTICE,
                "model": "eleven_flash_v2_5",
                "voice": "voix-du-banc",
                "base_url": f"http://{ADRESSE_FAUX}",
            },
        },
        jeton,
    )
    print(f"Fournisseurs de l'organisation réglés sur {ADRESSE_FAUX}.")


def agent(jeton: str, etat: dict) -> int:
    if etat.get("agent"):
        return int(etat["agent"])
    reponse = appeler(
        "POST",
        "/workflow/create/definition",
        {"name": NOM_AGENT, "workflow_definition": DEFINITION_AGENT},
        jeton,
    )
    assert isinstance(reponse, dict)
    print(f"Agent créé (id {reponse['id']}).")
    return int(reponse["id"])


def numero(
    jeton: str, configuration: int, extension: str, agent_rattache: int | None
) -> None:
    liste = appeler(
        "GET",
        f"/organizations/telephony-configs/{configuration}/phone-numbers",
        jeton=jeton,
    )
    assert isinstance(liste, dict)
    if any(n["address"] == extension for n in liste.get("phone_numbers", [])):
        return
    appeler(
        "POST",
        f"/organizations/telephony-configs/{configuration}/phone-numbers",
        {
            "address": extension,
            "label": f"banc {extension}",
            "inbound_workflow_id": agent_rattache,
        },
        jeton,
    )
    print(f"Extension {extension} créée, agent : {agent_rattache}.")


def principal() -> int:
    etat = json.loads(FICHIER_ETAT.read_text()) if FICHIER_ETAT.exists() else {}
    jeton = ouvrir_session()
    configuration = configuration_asterisk(jeton)
    fournisseurs(jeton)
    identifiant_agent = agent(jeton, etat)
    numero(jeton, configuration["id"], EXTENSION_AVEC_AGENT, identifiant_agent)
    numero(jeton, configuration["id"], EXTENSION_SANS_AGENT, None)

    etat = {
        "configuration": configuration["id"],
        "agent": identifiant_agent,
        "extension_avec_agent": EXTENSION_AVEC_AGENT,
        "extension_sans_agent": EXTENSION_SANS_AGENT,
        "application_stasis": configuration.get("credentials", {}).get(
            "stasis_app_name", ""
        ),
    }
    FICHIER_ETAT.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_ETAT.write_text(json.dumps(etat, indent=2) + "\n")
    print(json.dumps(etat, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
