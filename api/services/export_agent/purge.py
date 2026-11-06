"""[.mark] Ce qui ne voyage jamais d'une organisation à l'autre : les secrets, et les identifiants de la source.

Fonctions pures. ``purger_les_secrets`` retire (jamais ne masque) toute valeur écrite sous un nom de secret, dans n'importe quelle
profondeur d'une définition, de réglages ou d'un outil ; ``references`` relève les identifiants de clé d'une structure.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Iterator

# Noms EXACTS (``max_tokens`` n'est pas un secret) : une valeur écrite dans un champ de ce nom est retirée.
_NOM_SECRET = re.compile(
    r"^(api[-_]?key|apikey|x-api-key|secret|client[-_]?secret|password|passwd|token|access[-_]?token|auth[-_]?token|"
    r"bearer[-_]?token|authorization|proxy-authorization|private[-_]?key|access[-_]?key|secret[-_]?key|webhook[-_]?secret)$",
    re.IGNORECASE,
)


# Revue serveur M5 : un en-tête libre d'outil (``config.en_tetes_ext``) s'écrit ``{nom, sorte, valeur | identifiant_uuid}``.
# Sa clé (sorte ``secret``) est un identifiant de clé comme ``…credential_uuid`` ; sa valeur en clair (sorte ``texte``) est un
# secret quand le NOM de l'en-tête est un nom de secret (``Authorization: Bearer …``).
_CLE_D_EN_TETE = "identifiant_uuid"


def _est_un_en_tete(v: dict) -> bool:
    return isinstance(v.get("nom"), str) and "sorte" in v


def _valeur_d_en_tete_secrete(v: dict) -> bool:
    """Un en-tête en clair (jamais une variable) dont le nom est un nom de secret, et qui porte une valeur."""
    return (
        _est_un_en_tete(v)
        and v.get("sorte") in (None, "texte")
        and bool(_NOM_SECRET.match(v["nom"]))
        and v.get("valeur") not in (None, "")
    )


def _cle_d_en_tete(v: dict, cle: Any, contenu: Any) -> bool:
    return cle == _CLE_D_EN_TETE and _est_un_en_tete(v) and v.get("sorte") == "secret" and isinstance(contenu, str) and bool(contenu)


def _est_une_cle(v: dict, cle: Any, contenu: Any) -> bool:
    """``…credential_uuid`` ou la clé d'un en-tête secret : relevée, reliée à la clé de la cible, ou retirée."""
    if isinstance(cle, str) and cle.endswith("credential_uuid") and isinstance(contenu, str) and contenu:
        return True
    return _cle_d_en_tete(v, cle, contenu)


def purger_les_secrets(valeur: Any) -> tuple[Any, int]:
    """Une copie sans aucune valeur sous un nom de secret, et combien en ont été retirées."""
    retires = 0

    def marcher(v: Any) -> Any:
        nonlocal retires
        if isinstance(v, dict):
            propre = {}
            en_tete_secret = _valeur_d_en_tete_secrete(v)
            for cle, contenu in v.items():
                if isinstance(cle, str) and _NOM_SECRET.match(cle) and contenu not in (None, "", {}, []):
                    retires += 1
                    continue
                if en_tete_secret and cle == "valeur":
                    retires += 1
                    continue
                propre[cle] = marcher(contenu)
            return propre
        if isinstance(v, list):
            return [marcher(x) for x in v]
        return v

    return marcher(copy.deepcopy(valeur)), retires


def reperer_les_cles(valeur: Any) -> Iterator[str]:
    """Les identifiants de clé (``…credential_uuid``, clé d'un en-tête secret) écrits dans une structure, à toute profondeur."""
    if isinstance(valeur, dict):
        for cle, contenu in valeur.items():
            if _est_une_cle(valeur, cle, contenu):
                yield contenu
            else:
                yield from reperer_les_cles(contenu)
    elif isinstance(valeur, list):
        for x in valeur:
            yield from reperer_les_cles(x)


def remplacer_les_cles(valeur: Any, correspondance: dict[str, str | None]) -> Any:
    """Une copie où chaque identifiant de clé est remplacé par la clé de la cible, ou retiré (``None``) ; inconnue = retirée."""
    if isinstance(valeur, dict):
        sortie = {}
        for cle, contenu in valeur.items():
            if _est_une_cle(valeur, cle, contenu):
                neuve = correspondance.get(contenu)
                if neuve:
                    sortie[cle] = neuve
                continue
            sortie[cle] = remplacer_les_cles(contenu, correspondance)
        return sortie
    if isinstance(valeur, list):
        return [remplacer_les_cles(x, correspondance) for x in valeur]
    return copy.deepcopy(valeur)


def regenerer_les_declencheurs(definition: dict) -> dict:
    """Un chemin de déclencheur neuf par nœud ``trigger`` : celui de la source ne vaut rien chez la cible."""
    neuve = copy.deepcopy(definition or {})
    for noeud in neuve.get("nodes") or []:
        if isinstance(noeud, dict) and noeud.get("type") == "trigger":
            noeud.setdefault("data", {})["trigger_path"] = str(uuid.uuid4())
    return neuve


_IDENTIFIANT_DE_SOURCE = frozenset({"organization_id", "organisation_id", "org_id", "selected_organization_id"})


def retirer_les_identifiants(valeur: Any) -> Any:
    """Une copie sans aucun champ qui nomme une organisation : l'identifiant de la source ne doit jamais rester dans la cible."""
    if isinstance(valeur, dict):
        return {k: retirer_les_identifiants(v) for k, v in valeur.items() if not (isinstance(k, str) and k in _IDENTIFIANT_DE_SOURCE)}
    if isinstance(valeur, list):
        return [retirer_les_identifiants(x) for x in valeur]
    return copy.deepcopy(valeur)
