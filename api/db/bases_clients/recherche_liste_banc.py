"""[.mark] Mécanisme commun : le BANC DE DICTÉES d'une liste fermée (module Restauration, lot 4).

Un banc = une liste de dictées (``Dictee``) : ce qui est dit (formulations réelles, erreurs de transcription) et la réponse
attendue. Il rejoue le moteur de ``recherche_liste_moteur`` sur un index et rend trois mesures :

- ``bon``    : l'élément attendu est RETENU (ou, quand rien n'est attendu, la réponse est la bonne : AMBIGU / INTROUVABLE) ;
- ``ambigu`` : le moteur pose une question là où une réponse sûre était attendue (coûte un tour, ne trompe personne) ;
- ``faux_sur`` : le moteur RETIENT un autre élément, ou retient là où rien de sûr n'était attendu. **Zéro exigé.**

Réponse attendue (``attendu``) : l'identifiant d'un élément ; ``AMBIGU`` (plusieurs éléments disent la même chose) ; ou
``INTROUVABLE`` (rien dans la liste ne correspond). Un échec n'est jamais « presque bon » : un faux sûr est un faux sûr.

Rejoué à chaque changement de code et à chaque nouvelle liste (``recherche_liste_index.py``) ; une liste qui fait monter le faux
sûr n'est pas activée, et le contrôle de publication la refuse (``controle_de_publication``).
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from api.db.bases_clients.recherche_liste import Element, normaliser
from api.db.bases_clients.recherche_liste_moteur import Index, Reglages, chercher_dans_l_index

AMBIGU = "AMBIGU"
INTROUVABLE = "INTROUVABLE"


@dataclass(frozen=True)
class Dictee:
    dit: str
    attendu: str  # un identifiant, ``AMBIGU`` ou ``INTROUVABLE``
    origine: str = ""  # d'où vient la formulation (run, liste, essai) : pour retrouver la source d'un échec


@dataclass
class Bilan:
    total: int = 0
    bon: int = 0
    ambigu: int = 0
    introuvable: int = 0
    faux_surs: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)

    @property
    def faux_sur(self) -> int:
        return len(self.faux_surs)

    @property
    def sur(self) -> bool:
        """Zéro faux sûr : seul critère de sortie."""
        return not self.faux_surs

    def resume(self) -> dict:
        return {"total": self.total, "bon": self.bon, "ambigu": self.ambigu, "introuvable": self.introuvable, "faux_sur": self.faux_sur}


def mesurer(index: Index, dictees: Iterable[Dictee], reglages: Reglages = Reglages(), *, exclus: frozenset[str] = frozenset()) -> Bilan:
    bilan = Bilan()
    for d in dictees:
        bilan.total += 1
        r = chercher_dans_l_index(index, d.dit, reglages, exclus=exclus)
        statut, retenu = r["statut"], r["retenu"]
        detail = {"dit": d.dit, "attendu": d.attendu, "obtenu": statut, "retenu": retenu, "origine": d.origine}
        if statut == "RETENU":
            if d.attendu == retenu:
                bilan.bon += 1
            else:
                bilan.faux_surs.append(detail)  # un autre élément, ou rien de sûr n'était attendu
        elif statut == "AMBIGU":
            if d.attendu == AMBIGU:
                bilan.bon += 1
            else:
                bilan.ambigu += 1
                bilan.questions.append(detail)
        else:
            if d.attendu == INTROUVABLE:
                bilan.bon += 1
            else:
                bilan.introuvable += 1
    return bilan


def _sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def dictees_synthetiques(elements: Sequence[Element]) -> list[Dictee]:
    """Un banc tiré de la liste ELLE-MÊME, sans rien d'inventé : chaque nom dit tel quel, sans accent ni majuscule, avec une
    formule de politesse. Un nom porté par deux éléments est attendu ``AMBIGU``. C'est le banc de garde de l'activation d'un
    index quand la liste n'a pas de banc écrit à la main ; les formulations réelles (``charger_un_banc``) le complètent."""
    parnom: dict[str, list[Element]] = {}
    for e in elements:
        parnom.setdefault(normaliser(e.libelle), []).append(e)
    dictees = []
    for nom, porteurs in parnom.items():
        if not nom:
            continue
        attendu = porteurs[0].id if len(porteurs) == 1 else AMBIGU
        e = porteurs[0]
        dictees.append(Dictee(_sans_accent(e.libelle).lower(), attendu, "synthetique:sans_accent"))
        dictees.append(Dictee(f"je voudrais un {e.libelle} s'il vous plaît", attendu, "synthetique:politesse"))
    return dictees


def charger_un_banc(chemin: Path) -> tuple[str, list[Dictee]]:
    """Un banc écrit à la main : ``{"liste": nom, "dictees": [{"dit", "attendu", "origine"?}]}``."""
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    return donnees["liste"], [Dictee(d["dit"], d["attendu"], d.get("origine", "")) for d in donnees["dictees"]]


@dataclass(frozen=True)
class Controle:
    ok: bool
    bilan: Bilan
    raison: str = ""


def controle_de_publication(index: Index, dictees: Iterable[Dictee], reglages: Reglages = Reglages()) -> Controle:
    """Le contrôle de publication d'une liste : refusée dès qu'un seul faux sûr est mesuré. La raison dit les premières dictées."""
    bilan = mesurer(index, dictees, reglages)
    if bilan.sur:
        return Controle(True, bilan)
    exemples = "; ".join(f"« {f['dit']} » retient {f['retenu']} (attendu {f['attendu']})" for f in bilan.faux_surs[:3])
    return Controle(False, bilan, f"{bilan.faux_sur} faux sûr sur {bilan.total} dictées : {exemples}")
