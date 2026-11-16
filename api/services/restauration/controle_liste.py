"""[.mark] Module Restauration, lot 4 : le CONTRÔLE DE PUBLICATION de la recherche dans la carte.

Une carte qui fait monter le faux sûr bloque la publication : le banc de dictées (``recherche_liste_banc``) est rejoué sur la
carte de l'établissement, avec les dictées écrites à la main si on en a, plus celles que la carte fournit d'elle-même. Un seul faux
sûr refuse. Le défaut rendu est du même format que ceux du contrôle de prompt du builder (``Defaut``, gravité ``bloquant``) : le
service de contrôle de la publication n'a qu'à l'ajouter à sa liste (branchement fait avec les écrans, lots 11 et 12).
"""

from __future__ import annotations

from collections.abc import Iterable

from api.db.bases_clients import restauration
from api.db.bases_clients.recherche_liste_banc import (
    Controle,
    Dictee,
    controle_de_publication,
    dictees_synthetiques,
)
from api.db.bases_clients.recherche_liste_moteur import Reglages, construire_index
from api.db.bases_clients.restauration_client import elements_de_la_carte
from api.db.bases_clients.restauration_commun import Connexion
from api.services.builder.controle.regles import BLOQUANT, Defaut

CODE_DU_DEFAUT = "recherche_faux_sur"


def defaut_de_publication(controle: Controle, liste: str = "carte") -> Defaut | None:
    """``None`` si la liste est sûre ; sinon le défaut bloquant, avec les trois premières dictées en cause."""
    if controle.ok:
        return None
    exemples = [{"dit": f["dit"], "retenu": f["retenu"], "attendu": f["attendu"]} for f in controle.bilan.faux_surs[:3]]
    return Defaut(
        CODE_DU_DEFAUT, BLOQUANT,
        f"The {liste} search would pick the wrong item on {controle.bilan.faux_sur} of {controle.bilan.total} test sentences.",
        None, controle.raison[:120], {"liste": liste, "faux_sur": controle.bilan.faux_sur, "total": controle.bilan.total, "exemples": exemples},
    )


async def controler_la_carte(
    connexion: Connexion, etablissement_id: int, dictees: Iterable[Dictee] = (), reglages: Reglages = Reglages()
) -> Controle:
    """Le banc rejoué sur la carte COURANTE de l'établissement (les dictées données, plus celles tirées de la carte)."""
    carte = await restauration.carte_du_restaurant(connexion, etablissement_id)
    elements, categories = elements_de_la_carte(carte)
    index = construire_index(elements, categories)
    return controle_de_publication(index, [*dictees, *dictees_synthetiques(elements)], reglages)
