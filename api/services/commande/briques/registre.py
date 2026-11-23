"""[.mark] Le registre des briques de carte (chantier Partie 1, lot 8 ; E29, D9, D61 point 1, D66).

Distinct du registre des modules (``services/modules/registre.py``, qui tient les modules de l'agent : interrupteur, besoins, outils) : une brique n'a ni
outil ni interrupteur. Une entrée par brique :

- ``code`` (``ART1``...), ``famille``, ``niveau`` de formulaire (A, B ou C, D21) ;
- ``champs_de_la_carte`` : chaque champ de carte que la brique lit, ``(rubrique, champ)``. **Tous entrent dans le chargement de l'appel** (``charger_pour_l_appel``,
  lot 5, D61 point 1) : le test ``test_donnees_des_briques_dans_le_chargement`` les cherche dans la carte chargée ;
- ``regle`` : la fonction nommée ``brique_<code>_<verbe>`` (dans ``briques/<ce que fait la brique>.py``, le code de l'exigence en tête du module) ;
- ``alias_de`` : une brique qui se règle comme une autre (OPT9, OPT10, OPT11 comme OPT1), déclarée ici ;
- ``change_la_fiche_du_modele`` et ``vue_sur_carte`` (D66) : vrai quand, la carte de la brique chargée, le rendu de la fiche du modèle (cases visibles,
  question que la cuisine rend, lignes de l'état) diffère de celui de la même carte sans elle ; ``vue_sur_carte`` dit si la brique a été vue sur une des 44
  cartes lues (les briques jamais vues passent en dernier, côté code seulement) ;
- ``sans_la_brique`` : la fonction qui retire de la carte les données de la brique, le « sans » du test de rendu.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Brique:
    code: str
    famille: str
    niveau: str = "C"
    champs_de_la_carte: tuple[tuple[str, str], ...] = ()
    regle: Callable[..., Any] | None = None
    alias_de: str | None = None
    change_la_fiche_du_modele: bool | None = None  # ``None`` : pas encore déclarée (le test de rendu refuse)
    vue_sur_carte: bool | None = None
    sans_la_brique: Callable[[dict], dict] | None = None
    carte_d_essai: str | None = None
    phrase: str = field(default="", compare=False)  # ce que le retour porte pour le modèle (fait ou question numérotée), en une ligne


BRIQUES: dict[str, Brique] = {}


def enregistrer(brique: Brique) -> Brique:
    """Inscrit une brique ; un code déjà pris est une erreur de programmation (deux briques ne portent pas le même code)."""
    if brique.code in BRIQUES:
        raise ValueError(f"Brique déjà inscrite : {brique.code}")
    BRIQUES[brique.code] = brique
    return brique


def champs_declares() -> dict[str, tuple[tuple[str, str], ...]]:
    """Les champs de carte que chaque brique déclare, par code (le chargement de l'appel doit tous les porter)."""
    return {code: b.champs_de_la_carte for code, b in BRIQUES.items() if b.champs_de_la_carte}
