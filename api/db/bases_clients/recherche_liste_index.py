"""[.mark] Mécanisme commun : l'INDEX VERSIONNÉ d'une liste (module Restauration, lot 4, D10).

Chaque processus tient, pour chaque liste, l'index qu'il a bâti et la version de la liste qui l'a produit. Dès que la version lue
en base change, le processus refait son index AVANT de chercher. Le nouvel index n'est actif QUE si le banc de dictées rend zéro
faux sûr ; sinon :

- l'ancien index reste actif (une liste poussée par sa source en plein service ne dégrade jamais la recherche) ;
- les éléments retirés de la liste sont marqués INDISPONIBLES (``exclus``) : ils ne sont plus jamais rendus ;
- une alerte part (``alerte``) : la liste a changé de façon à créer un faux sûr, un humain doit la relire.

Premier index d'une liste (rien d'actif avant) : il est activé même s'il n'est pas prouvé (sans index, rien ne se cherche), et
l'alerte part. Le banc est celui qu'on donne ; à défaut, un banc tiré de la liste elle-même (``dictees_synthetiques``).

Sans état partagé entre processus : chacun refait le même index depuis la même version (WorkerSyncManager inutile, la version
en base est la synchronisation).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass, field

from loguru import logger

from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_banc import Bilan, Dictee, dictees_synthetiques, mesurer
from api.db.bases_clients.recherche_liste_moteur import Index, Reglages, construire_index

Alerte = Callable[[Hashable, str, dict], None]


def alerte_au_journal(cle: Hashable, evenement: str, details: dict) -> None:
    logger.error(f"[.mark] Closed-list search: {evenement} for {cle!r}: {details}")


@dataclass
class Etat:
    version: int  # la version de la liste qui a produit l'index ACTIF
    index: Index
    exclus: frozenset[str] = frozenset()  # retirés de la liste, marqués indisponibles
    version_vue: int = 0  # la dernière version lue (activée ou refusée) : on ne refait pas le même travail deux fois
    bilan: Bilan | None = None
    prouve: bool = True  # le banc de CET index a rendu zéro faux sûr
    refusee: bool = False  # la dernière version vue a été refusée
    historique: list[tuple[int, str]] = field(default_factory=list)


class GestionnaireDIndex:
    def __init__(self, *, alerte: Alerte = alerte_au_journal, banc: Callable[[Index, Sequence[Element], Reglages], Bilan] | None = None):
        self._etats: dict[Hashable, Etat] = {}
        self._verrous: dict[Hashable, asyncio.Lock] = {}
        self._alerte = alerte
        self._banc = banc

    def etat(self, cle: Hashable) -> Etat | None:
        return self._etats.get(cle)

    def a_jour(self, cle: Hashable, version: int) -> bool:
        e = self._etats.get(cle)
        return e is not None and e.version_vue == version

    def _mesurer(self, index: Index, elements: Sequence[Element], dictees: Iterable[Dictee] | None, reglages: Reglages) -> Bilan:
        if self._banc is not None:
            return self._banc(index, elements, reglages)
        return mesurer(index, list(dictees) if dictees is not None else dictees_synthetiques(elements), reglages)

    def preparer(
        self, cle: Hashable, version: int, elements: Sequence[Element], mots_de_categorie: Sequence[str] = (),
        dictees: Iterable[Dictee] | None = None, reglages: Reglages = Reglages(),
    ) -> Etat:
        """Synchrone (du calcul pur). L'état de ``cle`` à cette ``version`` : activé, ou l'ancien conservé."""
        ancien = self._etats.get(cle)
        if ancien is not None and ancien.version_vue == version:
            return ancien
        index = construire_index(elements, mots_de_categorie)
        bilan = self._mesurer(index, elements, dictees, reglages)
        if bilan.sur:
            etat = Etat(version, index, frozenset(), version, bilan, True, False, (ancien.historique if ancien else []) + [(version, "active")])
            self._etats[cle] = etat
            return etat
        details = {"version": version, **bilan.resume(), "exemples": bilan.faux_surs[:3]}
        if ancien is None:
            etat = Etat(version, index, frozenset(), version, bilan, False, False, [(version, "active_non_prouvee")])
            self._etats[cle] = etat
            self._alerte(cle, "premier_index_non_prouve", details)
            return etat
        # L'ancien reste actif ; ce que la nouvelle liste a retiré n'est plus rendu.
        presents = {e.id for e in elements}
        retires = frozenset(en.element.id for en in ancien.index.entrees if en.element.id not in presents) | ancien.exclus
        ancien.exclus = retires
        ancien.version_vue = version
        ancien.refusee = True
        ancien.historique.append((version, "refusee"))
        self._alerte(cle, "index_refuse", {**details, "version_active": ancien.version, "indisponibles": len(retires)})
        return ancien

    async def preparer_async(self, cle: Hashable, version: int, elements: Sequence[Element], mots_de_categorie: Sequence[str] = (), dictees=None, reglages: Reglages = Reglages()) -> Etat:
        """Hors de la boucle d'événements : le banc d'une grande liste ne fige pas un appel en cours."""
        verrou = self._verrous.setdefault(cle, asyncio.Lock())
        async with verrou:
            if self.a_jour(cle, version):
                return self._etats[cle]
            return await asyncio.to_thread(self.preparer, cle, version, elements, mots_de_categorie, dictees, reglages)

    def oublier(self, cle: Hashable | None = None) -> None:
        if cle is None:
            self._etats.clear()
        else:
            self._etats.pop(cle, None)


# Le gestionnaire du processus (un par processus : chacun refait son index depuis la version en base).
GESTIONNAIRE = GestionnaireDIndex()
