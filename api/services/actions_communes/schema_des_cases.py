"""[.mark] Chantier Partie 1, lot 7 : la lecture des cases d'une fiche dans les textes versés du gabarit, en une seule copie (S11 de l'audit des rustines).

La commande (lot 2) et la réservation (lot 7) déclarent leurs cases de la même façon : le schéma complet est l'UNION des rendus de la version finale
d'une étape, sur toutes les cartes et tous les états (une case n'y paraît que dans les états où elle a un objet), puis chaque case devient un
``Parametre``. Ce module ne sait aucun métier : l'étape, la liste des listes fermées du contexte et les textes d'état sont des paramètres.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from api.services.integrations.connectors.catalogue import Parametre


def union(a: dict, b: dict) -> dict:
    """Deux rendus d'une même case : les sous-cases des deux (un rendu d'état n'en montre qu'une partie)."""
    sortie = dict(a)
    for cle in ("properties",):
        if isinstance(b.get(cle), dict):
            sortie[cle] = {**{k: union(v, b[cle].get(k, {})) if k in b[cle] else v for k, v in (a.get(cle) or {}).items()},
                           **{k: v for k, v in b[cle].items() if k not in (a.get(cle) or {})}}
    if isinstance(a.get("items"), dict) and isinstance(b.get("items"), dict):
        sortie["items"] = union(a["items"], b["items"])
    return sortie


def schema_complet(etape: str, version: str | None = None, outil: str = "fiche") -> dict[str, Any]:
    """Toutes les cases de l'outil ``outil`` de l'étape ``etape`` avec leur texte de base : l'union des rendus versés. Les textes qui changent avec
    l'état sont dans ``variantes`` : le texte de base n'est jamais l'un d'eux quand un autre existe."""
    from api.services.gabarits.restauration.textes import TEMOIN, outils_verses, variantes

    textes_d_etat = set(variantes(version or TEMOIN).values())
    proprietes: dict[str, Any] = {}
    for etats in outils_verses(version or TEMOIN)["cartes"].values():
        for e in etats:
            if e["etape"] != etape:
                continue
            fiche = next(o["function"] for o in e["outils"] if o["function"]["name"] == outil)
            for nom, s in fiche["parameters"]["properties"].items():
                if nom not in proprietes:
                    proprietes[nom] = s
                elif proprietes[nom].get("description") in textes_d_etat and s.get("description") not in textes_d_etat:
                    proprietes[nom] = union(s, proprietes[nom])
                else:
                    proprietes[nom] = union(proprietes[nom], s)
    return proprietes


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
    from api.services.gabarits.restauration.textes import CARTE_TEMOIN, TEMOIN, rendu

    s = next(o["function"] for o in rendu(etape, "vide", CARTE_TEMOIN, version or TEMOIN) if o["function"]["name"] == "lire")["parameters"]
    requis = set(s.get("required") or ())
    return tuple(replace(parametre_de_la_case(k, v, "lire." + k), obligatoire=k in requis) for k, v in s["properties"].items())
