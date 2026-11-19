"""[.mark] Chantier Partie 1, lot 5 (E23, D13, D58, D61 point 3, S15) : l'INSTANTANÉ d'un appel, ce que la couche d'accès garde pour cet appel.

Une fiche exécutée en 50 ms au plus : le temps du code était de l'attente (75 requêtes en médiane pour ajouter un article, la carte relue à chaque
geste). Ce module tient, pour UN appel et UN établissement :

- les **lectures stables** (``stable``) : ce qui ne change pas pendant l'appel ou dont la règle veut qu'il ne change pas (la carte et ses prix,
  D61 point 3 : un prix changé en caisse pendant l'appel vaut à l'appel suivant ; zones, réglages, remises, horaires de la fiche, ruptures connues
  au décroché). Lues une fois (au décroché, par ``charger``, ou à leur premier usage si le chargement n'a pas fini), gardées pour l'appel seulement ;
- l'**état vivant** (``vivant``) : ce qui peut changer pendant l'appel et doit être vu à la fiche suivante (pause d'un type, forçage, fermeture
  exceptionnelle, état de la caisse). Lu en UNE requête, au plus une fois par geste (``nouveau_geste``).

Chaque lecture de la couche d'accès passe par ici : posé sur la connexion (``ConnexionDuClient.instantane``), l'instantané sert la mémoire ; absent
(portail, tâches de fond, essai sans appel), la lecture va à la base comme avant. Une seule règle par lecture, deux provenances de la donnée.
Les ruptures sont relues à l'enregistrement (``relire=True``) : une rupture posée pendant l'appel refuse toujours l'enregistrement.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass
class Vivant:
    """L'état vivant d'un établissement, lu en une requête : sa ligne (``site``), ses réglages par type (``types``, par nom), ses fermetures
    exceptionnelles pas encore finies (``fermetures``), l'état que sa caisse porte (``caisse``, ``None`` sans caisse)."""

    site: Any
    types: dict[str, Any]
    fermetures: list[Any]
    caisse: Any
    # Lot des manques (E5) : les minutes ajoutées EN CE MOMENT au délai de chaque zone de livraison (``{id de la zone: minutes}``) ; une zone sans
    # ajout, ou dont l'ajout a passé son « jusqu'à », n'y est pas (filtré dans la requête).
    ajouts_des_zones: dict[int, int] = field(default_factory=dict)


@dataclass
class Instantane:
    etablissement_id: int
    stables: dict[Hashable, Any] = field(default_factory=dict)
    vivant_du_geste: Vivant | None = None

    def nouveau_geste(self) -> None:
        """Un nouvel appel d'outil : l'état vivant sera relu (une requête) à sa première lecture."""
        self.vivant_du_geste = None


def instantane_de(connexion: Any) -> Instantane | None:
    return getattr(connexion, "instantane", None)


async def stable(connexion: Any, cle: Hashable, lire: Callable[[], Awaitable[T]]) -> T:
    """La lecture stable ``cle`` : gardée par l'instantané de la connexion s'il y en a un (lue une fois pour l'appel), sinon lue à la base."""
    inst = instantane_de(connexion)
    if inst is None:
        return await lire()
    if cle not in inst.stables:
        inst.stables[cle] = await lire()
    return inst.stables[cle]


def oublier(connexion: Any, cle: Hashable) -> None:
    """Une lecture stable à relire (ce que l'appel vient d'écrire lui-même, par exemple la fiche de son client après l'enregistrement)."""
    inst = instantane_de(connexion)
    if inst is not None:
        inst.stables.pop(cle, None)


REQUETE_DU_VIVANT = (
    "SELECT (SELECT s FROM mark.site s WHERE s.id = $1) AS site, "
    "(SELECT coalesce(array_agg(t ORDER BY t.type), '{}') FROM mark.resto_reglage_type t WHERE t.site_id = $1) AS types, "
    "(SELECT coalesce(array_agg(f ORDER BY f.du), '{}') FROM mark.fermeture f WHERE f.site_id = $1 AND f.au > $2) AS fermetures, "
    "(SELECT c FROM mark.resto_etat_caisse c WHERE c.site_id = $1) AS caisse, "
    "(SELECT array_agg(ARRAY[z.id, z.minutes_ajoutees] ORDER BY z.id) FROM mark.resto_zone z "
    "WHERE z.site_id = $1 AND z.minutes_ajoutees > 0 AND (z.ajout_jusqu_a IS NULL OR z.ajout_jusqu_a > $2)) AS ajouts_des_zones"
)


async def vivant(connexion: Any, etablissement_id: int, moment: Any) -> Vivant:
    """L'état vivant de l'établissement, en UNE requête ; gardé le temps du geste quand l'instantané est posé."""
    inst = instantane_de(connexion)
    if inst is not None and inst.vivant_du_geste is not None:
        return inst.vivant_du_geste
    r = await connexion.fetchrow(REQUETE_DU_VIVANT, etablissement_id, moment)
    lu = Vivant(r["site"], {t["type"]: t for t in r["types"] or ()}, list(r["fermetures"] or ()), r["caisse"],
                {int(z[0]): int(z[1]) for z in r["ajouts_des_zones"] or ()})
    if inst is not None:
        inst.vivant_du_geste = lu
    return lu
