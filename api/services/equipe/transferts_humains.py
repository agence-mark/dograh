"""[.mark] Le transfert vers un humain : l'issue de chaque tentative, le répondeur, la phrase du salarié.

Chantier agents-specialises, lot 5 (= lot 3 bis du plan fiche-etablissement, décision T d'Evan) :
« une fonctionnalité essentielle de notre produit, utile à plein de secteurs ».

Trois choses, aucune ne connaît un métier :

1. **L'issue** de chaque transfert, vers une personne OU vers le numéro de l'établissement, est
   écrite dans la fiche de l'appel sous la clé unique ``transferts_humains`` : une liste
   d'entrées ``{le, cible, issue}``, ``issue`` parmi ``decroche``, ``repondeur``, ``sans_reponse``,
   ``occupe``, ``echec``. Le lot 6 la lit (un seul renvoi vers un humain par appel). ``cible``
   ne porte jamais un numéro en clair : la clé de la personne, ou « numero:***1234 ».
2. **Le répondeur** : Twilio dit qui a décroché (``AnsweredBy``). Une machine ou un fax = le
   transfert a échoué (« répondeur »), l'appelant n'a jamais quitté l'agent. ``human`` et
   ``unknown`` comptent comme un humain : jamais d'appelant renvoyé à tort vers l'agent.
   Allumé sur TOUS les transferts ; un seul interrupteur de secours, la variable d'environnement
   ``DETECTION_REPONDEUR_TRANSFERT`` (« 0 », « false », « non » ou « off » l'éteint : le transfert
   redevient celui d'avant).
3. **La phrase du salarié** : ce que celui qui décroche entend avant d'être mis en relation,
   en français et réglable (variable de phrase ``phrase_salarie_transfert``).

Rien ici ne lève : une fiche illisible ou un numéro absent laissent l'appel continuer.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from xml.sax.saxutils import escape

from loguru import logger

CLE = "transferts_humains"
ISSUES = ("decroche", "repondeur", "sans_reponse", "occupe", "echec")

VARIABLE_PHRASE_SALARIE = "phrase_salarie_transfert"
PHRASE_SALARIE_DEFAUT = "Appel transmis par votre assistant vocal, je vous mets en relation."

# Les valeurs d'``AnsweredBy`` de Twilio qui disent « une machine » (le reste : un humain).
REPONDEURS = ("machine_start", "machine_end_beep", "machine_end_silence", "machine_end_other", "fax")

# Le temps que Twilio se donne pour trancher, en secondes (3 à 59) : passé ce délai, « unknown »,
# donc un humain. Il borne l'attente ajoutée au décroché ; à mesurer au banc réel.
DELAI_DETECTION_S = 8

_ETEINT = {"0", "false", "non", "off", "no"}


def detection_allumee() -> bool:
    """L'interrupteur de secours. Allumé par défaut."""
    return os.getenv("DETECTION_REPONDEUR_TRANSFERT", "true").strip().lower() not in _ETEINT


def est_un_repondeur(repondu_par) -> bool:
    return isinstance(repondu_par, str) and repondu_par.strip().lower() in REPONDEURS


def masquer(numero) -> str:
    """« numero:***1234 » : jamais un numéro en clair dans la fiche."""
    chiffres = re.sub(r"\D", "", str(numero or ""))
    return f"numero:***{chiffres[-4:]}" if len(chiffres) >= 4 else "numero:***"


def issue_du_resultat(resultat: dict | None) -> str:
    """L'issue d'un résultat de transfert (celui que le moteur traite pour tout fournisseur)."""
    resultat = resultat or {}
    if resultat.get("action") == "destination_answered" or resultat.get("status") in ("success", "transfer_success"):
        return "decroche"
    raison = str(resultat.get("reason") or "").strip().lower()
    return {
        "voicemail": "repondeur",
        "no_answer": "sans_reponse",
        "timeout": "sans_reponse",
        "busy": "occupe",
    }.get(raison, "echec")


def noter(fiche, cible: str, issue: str) -> None:
    """Écrit l'issue dans la fiche de l'appel. Ne lève jamais."""
    try:
        if not isinstance(fiche, dict):
            return
        fiche.setdefault(CLE, []).append(
            {"le": datetime.now(UTC).isoformat(), "cible": cible, "issue": issue if issue in ISSUES else "echec"}
        )
    except Exception as erreur:  # noqa: BLE001 -- une trace n'est jamais une raison de couper l'appel
        logger.warning(f"[.mark] Transfer outcome not written to the call's record: {erreur!r}")


def phrase_du_salarie(contexte: dict | None) -> str:
    """La phrase du catalogue quand l'organisation en a écrit une, sinon le texte par défaut."""
    brut = (contexte or {}).get(VARIABLE_PHRASE_SALARIE)
    texte = brut if isinstance(brut, str) and brut.strip() else PHRASE_SALARIE_DEFAUT
    return " ".join(texte.split())[:300]


def twiml_conference(nom_conference: str, phrase: str | None = None) -> str:
    """Ce que le salarié entend, puis la mise en conférence. Le texte est protégé (XML)."""
    dit = " ".join((phrase or PHRASE_SALARIE_DEFAUT).split())[:300]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'    <Say language="fr-FR">{escape(dit)}</Say>\n'
        "    <Dial>\n"
        f'        <Conference endConferenceOnExit="true">{escape(nom_conference)}</Conference>\n'
        "    </Dial>\n"
        "</Response>"
    )


TWIML_RACCROCHER = '<?xml version="1.0" encoding="UTF-8"?>\n<Response><Hangup/></Response>'
