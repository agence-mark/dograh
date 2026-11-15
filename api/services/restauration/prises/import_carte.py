"""[.mark] Module Restauration, lot 3 : la règle d'IMPORT d'une carte vers la portée (plan, lot 3).

Un catalogue lu chez la caisse d'UN établissement est importé :

- en carte PROPRE de l'établissement (``etablissement``) pour tout ce que l'enseigne ne connaît pas ;
- en EXCEPTION (``exception``) pour tout objet dont la ``ref`` existe déjà dans la carte d'enseigne : la ligne de l'établissement
  remplace celle de l'enseigne (la caisse est maître de ce qu'elle porte, une modification de l'enseigne ne l'écrase pas en silence) ;
- jamais en ``enseigne`` : la carte d'enseigne n'existe que si elle est DÉCLARÉE À LA MAIN (hors import). Un fichier qui se
  déclare ``enseigne`` est lu comme propre à l'établissement.

``marquer_la_portee`` est pure ; ``importer_selon_la_portee`` lit les ``ref`` de l'enseigne (par rubrique) et appelle ``importer_carte`` (qui
écrit en transaction, idempotent, sans écraser une surcouche ni une ligne qu'une personne a écrite).
"""

from __future__ import annotations

import copy

import asyncpg

from api.db.bases_clients import restauration
from api.db.bases_clients.restauration_carte import refs_d_enseigne

def _portee(objet: dict, rubrique: str, refs: dict[str, set[str]]) -> None:
    objet["portee"] = "exception" if objet.get("id") in refs.get(rubrique, set()) else "etablissement"


def marquer_la_portee(carte: dict, refs_enseigne: dict[str, set[str]] | None) -> dict:
    """Une COPIE de la carte, chaque objet marqué ``etablissement`` ou ``exception``. Sans enseigne : tout est propre."""
    refs = refs_enseigne or {}
    sortie = copy.deepcopy(carte)
    for c in sortie.get("categories", []):
        _portee(c, "categories", refs)
    for p in sortie.get("produits", []):
        _portee(p, "produits", refs)
        for d in p.get("declinaisons", []):
            _portee(d, "declinaisons", refs)
    for g in sortie.get("groupes", []):
        _portee(g, "groupes", refs)
        for o in g.get("options", []):
            _portee(o, "options", refs)
    for f in sortie.get("formules", []):
        _portee(f, "formules", refs)
    return sortie


async def importer_selon_la_portee(connexion: asyncpg.Connection, etablissement_id: int, carte: dict, source: str) -> dict:
    """Importe la carte d'un établissement avec la règle de portée ; rend le bilan d'``importer_carte``."""
    marquee = marquer_la_portee(carte, await refs_d_enseigne(connexion))
    return await restauration.importer_carte(connexion, etablissement_id, marquee, source)
