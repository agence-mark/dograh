"""[.mark] Chantier Partie 1, lot 7 : la lecture des cases d'une fiche dans les textes versés du gabarit, en une seule copie (S11 de l'audit des rustines).

La commande (lot 2) et la réservation (lot 7) déclarent leurs cases de la même façon : le schéma complet est celui du contrat des outils (l'union
des états, sans carte de test, dérivée des rendus du banc, une par version du gabarit), puis chaque case devient un ``Parametre``. Ce module ne sait aucun métier : l'étape, la liste des listes fermées du contexte et les textes d'état sont des paramètres.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from api.services.integrations.connectors.catalogue import Parametre


def schema_complet(etape: str, version: str | None = None) -> dict[str, Any]:
    """Toutes les cases de la fiche de l'étape avec leur texte de base, lues dans le contrat des outils (``contrats/<n>.json``, sans carte). Les textes
    qui changent avec l'état sont dans ``variantes`` : le texte de base n'est jamais l'un d'eux quand un autre existe."""
    from api.services.gabarits.restauration.textes import TEMOIN, cases_de_la_fiche

    return cases_de_la_fiche(etape, version or TEMOIN)


def parametre_de_la_case(nom: str, s: dict[str, Any], chemin: str, listes: Mapping[str, str] | None = None) -> Parametre:
    """Une case du schéma versé devenue ``Parametre`` ; ``listes`` : chemin de case -> nom de la liste fermée du contexte (construite au décroché)."""
    elements = None
    if s.get("type") == "array" and isinstance(s.get("items"), dict):
        elements = parametre_de_la_case("", s["items"], chemin + "[]", listes)
    proprietes = tuple(parametre_de_la_case(k, v, f"{chemin}.{k}", listes) for k, v in (s.get("properties") or {}).items())
    liste = (listes or {}).get(chemin)
    return Parametre(
        nom=nom, type=s.get("type", "string"), description=s.get("description", ""), obligatoire=False,
        choix=() if liste else tuple(s.get("enum") or ()), liste_du_contexte=liste, minimum=s.get("minimum"), elements=elements,
        proprietes=proprietes, obligatoires=tuple(s.get("required") or ()), min_elements=s.get("minItems"), max_elements=s.get("maxItems"),
    )


def parametres_de_la_fiche(etape: str, listes: Mapping[str, str] | None = None, version: str | None = None) -> tuple[Parametre, ...]:
    """Les cases de la fiche d'une étape, toutes facultatives sauf ``a_dire``."""
    sortie = []
    for nom, s in schema_complet(etape, version).items():
        p = parametre_de_la_case(nom, s, nom, listes)
        sortie.append(replace(p, obligatoire=True) if nom == "a_dire" else p)
    return tuple(sortie)


def parametres_de_la_lecture(etape: str, version: str | None = None) -> tuple[Parametre, ...]:
    """Les cases de l'outil ``lire`` d'une étape (``sujet`` et ses sœurs), ``sujet`` obligatoire."""
    from api.services.gabarits.restauration.textes import TEMOIN, outil

    s = outil(etape, "lire", version or TEMOIN)["parameters"]
    requis = set(s.get("required") or ())
    return tuple(replace(parametre_de_la_case(k, v, "lire." + k), obligatoire=k in requis) for k, v in s["properties"].items())
