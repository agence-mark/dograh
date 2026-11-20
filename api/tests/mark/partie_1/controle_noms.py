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

# C2 bis (lot 19 bis) : les deux moitiés d'UN même geste (le règlement partagé en deux moyens) se disent avec le même mot « moyen », voulu : elles s'ouvrent ensemble, leurs descriptions disent
# laquelle est laquelle. Seule paire exemptée de la règle 3 ; toute autre paire proche reste refusée.
PROCHES_VOULUS = frozenset({frozenset({"moyen_de_paiement", "moyen_reste"})})


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
                if com and frozenset({a, b}) not in PROCHES_VOULUS:
                    r3.append(f"{a} / {b} : « {', '.join(sorted(com))} » ({lec}, état {et})")
    return sorted(set(r1)), sorted(set(r2)), sorted(set(r3))


def _cases(vus: list[Occurrence], lecteur: str, etat: str, nom_outil: str, proprietes: dict) -> None:
    for k, v in proprietes.items():
        vus.append((lecteur, etat, "case", k, nom_outil))
        for e in v.get("enum") or []:
            vus.append((lecteur, etat, "valeur", e, k))
        sous = v.get("items", {}).get("properties") if v.get("type") == "array" else v.get("properties")
        for k2, v2 in (sous or {}).items():
            vus.append((lecteur, etat, "sous_case", k2, k))
            for e in v2.get("enum") or []:
                vus.append((lecteur, etat, "valeur", e, k2))


def inventaire_du_fork(connecteurs_lus: tuple[str, ...] = ("commande", "service", "reservation")) -> list[Occurrence]:
    """Le schéma réel que voit le modèle, lu dans le catalogue des connecteurs du fork (actions d'agent : commande, service, réservation).

    Lot 2 : un connecteur qui déclare ses cases selon l'état (``cases_visibles``) est lu DANS CHAQUE ÉTAT type de la version finale (les vues
    versées du gabarit, sur les cinq cartes : 21 états), cases et sous-cases, comme le contrôle du banc ; un connecteur sans état est lu d'un bloc."""
    from api.services.commande import contrat
    from api.services.reservation import contrat as reservation_contrat
    from api.services.gabarits.restauration.textes import outils_verses
    from api.services.integrations.connectors.catalogue import connecteurs
    from api.services.integrations.connectors.outil import _propriete
    from api.services.workflow.cases_selon_l_etat import schema_selon_l_etat

    vus: list[Occurrence] = []
    for c in connecteurs():
        if c.nom not in connecteurs_lus:
            continue
        lecteur = f"cerveau {c.nom}"
        if c.cases_visibles is None:
            for a in c.actions:
                vus.append((lecteur, "schema", "outil", a.nom, ""))
                _cases(vus, lecteur, "schema", a.nom, {p.nom: _propriete(p, None) for p in a.parametres})
            continue
        for carte, etats in outils_verses()["cartes"].items():
            for e in etats:
                if e["etape"] != c.nom:
                    continue
                module = reservation_contrat if c.nom == "reservation" else contrat
                vue = (reservation_contrat.VueDeLaReservation if c.nom == "reservation" else contrat.VueDeLaCommande).depuis_un_dict(e["vue"])
                etat = f"{carte} {e['etat']}"
                for a in c.actions:
                    vus.append((lecteur, etat, "outil", a.nom, ""))
                    proprietes = {p.nom: _propriete(p, None) for p in a.parametres}
                    if a.nom == "fiche":
                        proprietes, _ = schema_selon_l_etat(proprietes, [], module.cases_visibles_de_la_vue(vue), module.forme_de_la_vue(vue))
                    _cases(vus, lecteur, etat, a.nom, proprietes)
    return vus
