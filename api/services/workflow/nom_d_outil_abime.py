"""[.mark] Module Restauration, lot 24 : le NOM D'OUTIL ABÎMÉ (« ajoute » pour ``ajouter``, ``functions.ajouter``, ``Ajouter_``).

Un modèle écrit parfois le nom d'un outil de travers. Sans réponse du fork, l'appel d'outil tombe dans le vide (Pipecat journalise et ne fait rien). Ici, au
niveau du FORK (jamais dans Pipecat : R9), un gestionnaire « attrape-tout » (``register_function(None, …)``, prévu par Pipecat pour cela) est posé après les
outils de l'étape :

- un nom qui est déjà celui d'un outil n'arrive jamais ici (Pipecat l'adresse à son gestionnaire) ;
- un nom ABÎMÉ mais SANS AMBIGUÏTÉ (même nom à la casse, aux accents, aux séparateurs ou à un préfixe ``functions.`` près ; ou assez proche d'un seul outil avec un
  écart net sur le suivant) est RATTACHÉ à cet outil, qui s'exécute avec les arguments donnés ;
- sinon : REFUS FERMÉ (``outil_inconnu``, la liste des outils de l'étape en clair), jamais un outil deviné au hasard.

Éteint par défaut (``garde_nom_d_outil``) : sans la clé, rien n'est posé et le comportement est celui d'avant. ⛔ Ne lève jamais.
"""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
from typing import Any

from loguru import logger

CLE = "garde_nom_d_outil"
RATIO_MINI = 0.85       # assez proche pour être rattaché
ECART_MINI = 0.08       # et nettement plus proche que le deuxième


def allumee(reglages: Any) -> bool:
    """Éteinte par défaut : seul ``True`` allume."""
    return isinstance(reglages, Mapping) and reglages.get(CLE) is True


def _normaliser(nom: str) -> str:
    sans_prefixe = re.split(r"[.:/]", str(nom))[-1]
    sans_accent = "".join(c for c in unicodedata.normalize("NFD", sans_prefixe) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", sans_accent.casefold())


def rattacher(nom: str | None, connus: Iterable[str]) -> str | None:
    """Le nom de l'outil que ``nom`` abîmé désigne SANS AMBIGUÏTÉ, ``None`` sinon. Un nom exact est rendu tel quel."""
    try:
        outils = [c for c in connus if c]
        if not nom or not outils:
            return None
        if nom in outils:
            return nom
        voulu = _normaliser(nom)
        if not voulu:
            return None
        egaux = [c for c in outils if _normaliser(c) == voulu]
        if egaux:
            return egaux[0] if len(egaux) == 1 else None             # deux outils s'écrivent pareil : ambigu
        notes = sorted(((SequenceMatcher(None, voulu, _normaliser(c)).ratio(), c) for c in outils), reverse=True)
        if notes[0][0] < RATIO_MINI:
            return None
        if len(notes) > 1 and notes[0][0] - notes[1][0] < ECART_MINI:
            return None
        return notes[0][1]
    except Exception:  # noqa: BLE001
        return None


def _refus(connus: list[str]) -> dict[str, Any]:
    return {
        "status": "outil_inconnu",
        "error": "unknown tool",
        "outils": connus,
        "a_dire_au_client": "",
        "consigne": "Ce nom n'est pas un de tes outils. Utilise exactement l'un de ces noms : " + ", ".join(connus) + ".",
    }


def installer(moteur: Any, llm: Any) -> bool:
    """Pose le gestionnaire attrape-tout sur ``llm`` si le réglage est allumé. ``False`` : rien posé. ⛔ Ne lève jamais."""
    try:
        if not allumee(getattr(moteur, "reglages_appel", None)):
            return False

        async def attrape_tout(params: Any) -> None:
            registre = getattr(llm, "_functions", {}) or {}
            connus = [n for n in registre if isinstance(n, str)]
            cible = rattacher(getattr(params, "function_name", None), connus)
            fiche = getattr(moteur, "_gathered_context", None)
            from api.services.integrations.connectors import mesures

            if cible is None:
                logger.warning(f"[outil] nom d'outil inconnu refusé : {getattr(params, 'function_name', None)!r}")
                mesures.ecrire(fiche, "outil.nom_refuse", "inconnu")
                await params.result_callback(_refus(sorted(connus)))
                return
            logger.info(f"[outil] nom d'outil abîmé {getattr(params, 'function_name', None)!r} rattaché à {cible!r}")
            mesures.ecrire(fiche, "outil.nom_rattache", cible)
            await registre[cible].handler(dataclasses.replace(params, function_name=cible))

        llm.register_function(None, attrape_tout)
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[outil] attrape-tout non posé : {erreur!r}")
        return False
