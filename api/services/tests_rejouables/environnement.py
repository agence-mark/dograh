"""[.mark] Builder partie 3, sous-lot 5 (SE-11, C-3) : l'ENVIRONNEMENT d'un test, ce que le test fixe autour de la conversation.

Quatre choses, toutes facultatives, rien n'est réellement appelé :

* **la date et l'heure de l'appel** (heure de Paris) : l'agent croit être à ce moment (horaires, fermetures, « demain »). Posées
  comme horloge simulée (``utils.template_renderer.HORLOGE_SIMULEE``) le temps d'un tour joué ; vides, la vraie horloge ;
* **le numéro de l'appelant** (ou « masqué » : aucun numéro présenté) : ``caller_number`` de l'appel ;
* **les variables de l'appel** : valeurs de départ (comme celles que pose la téléphonie ou le widget) ;
* **les réponses d'outils simulées** : pour un outil (ou « * » : tout outil simulé qui n'a pas la sienne), ses appels dans l'ordre (« en panne au premier appel, puis la réponse ») ;
  au-delà du dernier, le dernier se répète. Un outil sans simulation garde la réponse neutre de ``simulation.py``.

Une forme, validée ici, partagée par le rejeu d'une réplique (``rejeu.py``) et la conversation libre (``tests_agent.jeu``).
⛔ Zéro vocabulaire métier. ⛔ Aucun appel réel : une réponse simulée est une donnée du test.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from api.services.tests_rejouables.modele import ErreurTestRejouable, normaliser

# Posée dans la fiche du run d'essai, à côté de ``CLE_REJEU`` (et nulle part ailleurs).
CLE_ENVIRONNEMENT = "rejeu_environnement"
CLE_COMPTEURS = "rejeu_appels_simules"

TOUT_OUTIL = "*"
SORTES = ("reponse", "erreur", "delai", "refus")
OUTILS_MAX = 10
APPELS_MAX = 8
VARIABLES_MAX = 20
CORPS_MAX = 4000
FUSEAU = ZoneInfo("Europe/Paris")
# Les noms que le moteur lit : un test ne les écrase pas par une « variable ».
_NOM_DE_VARIABLE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_RESERVES = frozenset({"caller_number", "called_number", "provider", "direction"})

# Ce que l'outil rend au modèle pour chaque sorte d'échec : la forme d'un vrai échec (``enveloppe_des_actions.est_un_echec``).
_ECHECS = {
    "erreur": {"status": "error", "error": "The service returned an error."},
    "delai": {"status": "error", "error": "The service did not answer in time."},
    "refus": {"status": "error", "error": "The service refused the request."},
}


def _texte(brut: Any, nom: str, maxi: int) -> str:
    if brut is None:
        return ""
    if not isinstance(brut, str):
        raise ErreurTestRejouable(f"environment: « {nom} » must be text")
    return brut.strip()[:maxi]


def valider(brut: Any) -> dict[str, Any] | None:
    """L'environnement tel que le code le garde, ou ``None`` s'il est vide. ``ErreurTestRejouable`` avec la raison."""
    if brut in (None, {}, ""):
        return None
    if not isinstance(brut, dict):
        raise ErreurTestRejouable("environment: an object is expected")
    date = _texte(brut.get("date"), "date", 10)
    heure = _texte(brut.get("heure"), "heure", 5)
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ErreurTestRejouable("environment: « date » must be YYYY-MM-DD") from None
    if heure:
        try:
            datetime.strptime(heure, "%H:%M")
        except ValueError:
            raise ErreurTestRejouable("environment: « heure » must be HH:MM") from None
    if heure and not date:
        raise ErreurTestRejouable("environment: a time needs its date")
    masque = bool(brut.get("masque"))
    numero = "" if masque else _texte(brut.get("numero"), "numero", 30)
    variables_brutes = brut.get("variables") or {}
    if not isinstance(variables_brutes, dict) or len(variables_brutes) > VARIABLES_MAX:
        raise ErreurTestRejouable(f"environment: « variables » is an object of {VARIABLES_MAX} entries at most")
    variables: dict[str, str] = {}
    for nom, valeur in variables_brutes.items():
        nom = str(nom).strip()
        if not _NOM_DE_VARIABLE.match(nom) or nom in _RESERVES or nom.startswith("rejeu_"):
            raise ErreurTestRejouable(f"environment: variable name « {nom} » is not allowed (lowercase letters, digits, underscore)")
        variables[nom] = _texte(str(valeur) if valeur is not None else "", nom, 200)
    simulations = _valider_les_simulations(brut.get("simulations") or [])
    propre = {"date": date, "heure": heure, "numero": numero, "masque": masque, "variables": variables, "simulations": simulations}
    return propre if (date or numero or masque or variables or simulations) else None


def _valider_les_simulations(brutes: Any) -> list[dict[str, Any]]:
    if not isinstance(brutes, list) or len(brutes) > OUTILS_MAX:
        raise ErreurTestRejouable(f"environment: « simulations » is a list of {OUTILS_MAX} tools at most")
    propres: list[dict[str, Any]] = []
    vus: set[str] = set()
    for sim in brutes:
        if not isinstance(sim, dict) or not str(sim.get("outil") or "").strip():
            raise ErreurTestRejouable("environment: each simulation names its tool (« outil »)")
        outil = str(sim["outil"]).strip()[:120]
        if normaliser(outil) in vus:
            raise ErreurTestRejouable(f"environment: tool « {outil} » is simulated twice")
        vus.add(normaliser(outil))
        appels = sim.get("appels")
        if not isinstance(appels, list) or not appels or len(appels) > APPELS_MAX:
            raise ErreurTestRejouable(f"environment: « {outil} » needs 1 to {APPELS_MAX} calls")
        propres_appels = []
        for appel in appels:
            sorte = appel.get("sorte") if isinstance(appel, dict) else None
            if sorte not in SORTES:
                raise ErreurTestRejouable(f"environment: unknown kind of answer {sorte!r} (expected: {', '.join(SORTES)})")
            corps = None
            if sorte == "reponse":
                brut = appel.get("corps")
                if isinstance(brut, str):
                    if len(brut) > CORPS_MAX:
                        raise ErreurTestRejouable(f"environment: an answer is {CORPS_MAX} characters at most")
                    try:
                        corps = json.loads(brut) if brut.strip() else {}
                    except json.JSONDecodeError:
                        raise ErreurTestRejouable(f"environment: the answer of « {outil} » is not valid JSON") from None
                elif brut is None:
                    corps = {}
                else:
                    corps = brut
                if not isinstance(corps, (dict, list)) or len(json.dumps(corps, ensure_ascii=False)) > CORPS_MAX:
                    raise ErreurTestRejouable(f"environment: the answer of « {outil} » is a JSON object or list of {CORPS_MAX} characters at most")
            propres_appels.append({"sorte": sorte, "corps": corps})
        propres.append({"outil": outil, "appels": propres_appels})
    return propres


# --- l'appliquer au run d'essai ---------------------------------------------------------------------------------------


def contexte_initial(env: dict[str, Any] | None) -> dict[str, Any]:
    """Ce que l'environnement ajoute au contexte de départ de l'appel : variables et numéro. Masqué : aucun numéro."""
    if not env:
        return {}
    contexte: dict[str, Any] = dict(env.get("variables") or {})
    if env.get("numero") and not env.get("masque"):
        contexte["caller_number"] = env["numero"]
    return contexte


def fiche_du_rejeu(env: dict[str, Any] | None) -> dict[str, Any]:
    """Ce que l'environnement ajoute à la fiche du run d'essai : de quoi simuler les outils, rien d'autre."""
    return {CLE_ENVIRONNEMENT: env} if env and env.get("simulations") else {}


def instant(env: dict[str, Any] | None) -> datetime | None:
    if not env or not env.get("date"):
        return None
    return datetime.strptime(f"{env['date']} {env.get('heure') or '12:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=FUSEAU)


@contextmanager
def horloge(env: dict[str, Any] | None) -> Iterator[None]:
    """L'horloge de l'appel pendant un tour joué. Sans date : la vraie horloge, rien n'est posé."""
    fixe = instant(env)
    if fixe is None:
        yield
        return
    from api.utils.template_renderer import HORLOGE_SIMULEE

    jeton = HORLOGE_SIMULEE.set(fixe)
    try:
        yield
    finally:
        HORLOGE_SIMULEE.reset(jeton)


def reponse_simulee(moteur: Any, nom: str) -> tuple[Any, str] | None:
    """La réponse du N-ième appel de l'outil ``nom`` selon l'environnement du run, avec sa sorte ; ``None`` si l'outil n'est pas
    simulé (la réponse neutre s'applique). Le compte des appels vit dans la fiche du run. ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        env = fiche.get(CLE_ENVIRONNEMENT) if isinstance(fiche, dict) else None
        if not isinstance(env, dict):
            return None
        simulations = env.get("simulations") or []
        sim = next((s for s in simulations if normaliser(s.get("outil")) == normaliser(nom)), None)
        if sim is None:
            sim = next((s for s in simulations if s.get("outil") == TOUT_OUTIL), None)  # « * » : la réponse de tout autre outil simulé
        if sim is None or not sim.get("appels"):
            return None
        compteurs = fiche.setdefault(CLE_COMPTEURS, {})
        cle = normaliser(nom)  # le compte est PAR OUTIL, même quand la réponse écrite est celle de « * »
        rang = int(compteurs.get(cle, 0))
        compteurs[cle] = rang + 1
        appel = sim["appels"][min(rang, len(sim["appels"]) - 1)]
        if appel["sorte"] == "reponse":
            return appel.get("corps") if appel.get("corps") is not None else {}, "reponse"
        return dict(_ECHECS[appel["sorte"]]), appel["sorte"]
    except Exception:  # noqa: BLE001
        return None
