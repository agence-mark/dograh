"""[.mark] Le contrôle des noms que lit le modèle (chantier Partie 1, lot 0, élément L00-07), porté du banc B12.

Trois règles (méthode, § 3, règle 2) :
  1. un nom lu par le modèle manque au glossaire ;
  2. un nom a deux sens : il paraît sous un genre que le glossaire ne lui donne pas, le glossaire consigne un double sens
     (« (Rouge »), ou il est à la fois outil et champ dans un même état sans être déclaré ainsi (D54) ;
  3. deux noms proches sont visibles dans le même état : deux outils ou cases de la fiche qui partagent un mot autre qu'un verbe
     ou un mot vide.
Une occurrence = (lecteur, état, genre, nom, parent). L'inventaire du fork lit le schéma réel des actions des connecteurs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from api.tests.mark.partie_1 import glossaire as GL

Occurrence = tuple[str, str, str, str, str]


def mots(nom: str) -> list[str]:
    return [m for m in re.split(r"[_\s]+", nom.lower()) if m and m not in GL.VIDES]


def controler(vus: Iterable[Occurrence], glossaire: dict | None = None) -> tuple[list[str], list[str], list[str]]:
    G = GL.GLOSSAIRE if glossaire is None else glossaire
    vus = [tuple(v) for v in vus]
    r1, r2, r3 = [], [], []
    for lec, et, g, nom, par in vus:
        if nom not in G:
            r1.append(f"{nom} ({g}, {lec}, {par or '-'})")
            continue
        genres, d = G[nom]
        if g not in genres:
            r2.append(f"{nom} : vu comme {g} ({lec}), le glossaire dit {sorted(genres)}")
        if "(Rouge" in d:
            r2.append(f"{nom} ({lec}) : {d[d.index('(Rouge') + 1:-1]}")
    par_etat: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for lec, et, g, nom, par in vus:
        par_etat.setdefault((lec, et), []).append((g, nom, par))
    for (lec, et), xs in par_etat.items():
        genres: dict[str, set[str]] = {}
        for g, nom, par in xs:
            if g in ("outil", "case", "champ_greffier"):
                genres.setdefault(nom, set()).add(g)
        for nom, gs in genres.items():
            if len(gs) > 1 and not gs <= set(G.get(nom, (frozenset(), ""))[0]):
                r2.append(f"{nom} : outil et champ à la fois ({lec}, {et})")
        haut = sorted({nom for g, nom, par in xs if g == "outil" or (g == "case" and par == "fiche")})
        for i, a in enumerate(haut):
            for b in haut[i + 1:]:
                com = (set(mots(a)) & set(mots(b))) - GL.VERBES
                if com:
                    r3.append(f"{a} / {b} : « {', '.join(sorted(com))} » ({lec}, état {et})")
    return sorted(set(r1)), sorted(set(r2)), sorted(set(r3))


def inventaire_du_fork() -> list[Occurrence]:
    """Le schéma réel que voit le modèle, lu dans le catalogue des connecteurs du fork (actions d'agent : commande, réservation, service).

    Avant le lot 2, ce sont les anciennes actions ; à partir du lot 2, la fiche et sa lecture : le test passe au vert."""
    from api.services.integrations.connectors.catalogue import connecteurs

    vus: list[Occurrence] = []
    for c in connecteurs():
        if c.nom not in ("commande", "reservation", "service"):
            continue
        for a in c.actions:
            vus.append((f"cerveau {c.nom}", "schema", "outil", a.nom, ""))
            for p in a.parametres:
                vus.append((f"cerveau {c.nom}", "schema", "case", p.nom, a.nom))
    return vus
